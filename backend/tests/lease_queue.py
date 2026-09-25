"""An in-memory queue with leases, following kaagaz.jobs.ports.WorkQueue.

Test-only. It behaves like SQS with a redrive policy, so the worker can be
tested without a real queue and without sleeping: time comes from FakeClock.

Data structures and costs (n jobs in the queue):

* ``_entries``: dict job id -> entry. O(1) lookup for ack, extend and bury.
* ``_ready``: deque of job ids waiting in line. O(1) append and pop.
* ``_leased``: heap of (expires_at, seq, job_id, token) for jobs handed out,
  ordered by expiry, so finding expired leases costs O(log n) per lease.
  Entries are never removed from the middle of the heap; a heap item is simply
  ignored if its token or expiry no longer matches the job ("lazy deletion").
* ``failed``: dict job id -> FailedJob, the failure bin.
"""

import heapq
import itertools
from collections import deque
from dataclasses import dataclass

from kaagaz.ingestion.ports import Job
from kaagaz.jobs.ports import Delivery, LeaseLost


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@dataclass(slots=True)
class _Entry:
    job: Job
    attempts: int = 0
    token: int | None = None  # set while leased
    expires_at: float = 0.0


@dataclass(frozen=True, slots=True)
class FailedJob:
    job: Job
    attempts: int
    code: str


class LeaseQueue:
    def __init__(self, clock: FakeClock, *, lease_seconds: float, max_attempts: int) -> None:
        if lease_seconds <= 0 or max_attempts < 1:
            raise ValueError("lease_seconds must be positive and max_attempts at least 1")
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._entries: dict[int, _Entry] = {}
        self._ready: deque[int] = deque()
        self._leased: list[tuple[float, int, int, int]] = []
        self._seq = itertools.count()
        self._tokens = itertools.count(1)
        self._ids = itertools.count(1)
        self.failed: dict[int, FailedJob] = {}

    # -- producer side ----------------------------------------------------

    def enqueue(self, job: Job) -> None:
        job_id = next(self._ids)
        self._entries[job_id] = _Entry(job)
        self._ready.append(job_id)

    # -- WorkQueue --------------------------------------------------------

    def receive(self) -> Delivery | None:
        self._reclaim_expired()
        if not self._ready:
            return None
        job_id = self._ready.popleft()
        entry = self._entries[job_id]
        entry.attempts += 1
        entry.token = next(self._tokens)
        self._lease(job_id, entry)
        return Delivery(job=entry.job, receipt=f"{job_id}:{entry.token}", attempt=entry.attempts)

    def ack(self, receipt: str) -> None:
        job_id, _ = self._check(receipt)
        del self._entries[job_id]

    def extend(self, receipt: str) -> None:
        job_id, entry = self._check(receipt)
        self._lease(job_id, entry)

    def bury(self, receipt: str, code: str) -> None:
        job_id, entry = self._check(receipt)
        self.failed[job_id] = FailedJob(entry.job, entry.attempts, code)
        del self._entries[job_id]

    # -- helpers for tests ------------------------------------------------

    def pending(self) -> int:
        """Jobs not yet done or failed (waiting or leased)."""
        return len(self._entries)

    # -- internals --------------------------------------------------------

    def _lease(self, job_id: int, entry: _Entry) -> None:
        entry.expires_at = self._clock.now() + self._lease_seconds
        assert entry.token is not None
        heapq.heappush(self._leased, (entry.expires_at, next(self._seq), job_id, entry.token))

    def _check(self, receipt: str) -> tuple[int, _Entry]:
        job_id_text, token_text = receipt.split(":")
        job_id, token = int(job_id_text), int(token_text)
        entry = self._entries.get(job_id)
        if entry is None or entry.token != token or self._clock.now() >= entry.expires_at:
            raise LeaseLost(receipt)
        return job_id, entry

    def _reclaim_expired(self) -> None:
        """Move every expired lease back into line, or into the failure bin."""
        now = self._clock.now()
        while self._leased and self._leased[0][0] <= now:
            expires_at, _, job_id, token = heapq.heappop(self._leased)
            entry = self._entries.get(job_id)
            if entry is None or entry.token != token or entry.expires_at != expires_at:
                continue  # stale heap item: acked, buried or extended since
            entry.token = None
            if entry.attempts >= self._max_attempts:
                self.failed[job_id] = FailedJob(entry.job, entry.attempts, "attempts_exhausted")
                del self._entries[job_id]
            else:
                self._ready.append(job_id)  # back of the line
