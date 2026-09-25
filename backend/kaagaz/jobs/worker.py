"""Run jobs from the queue, one at a time.

``run_once`` takes one job, runs the handler and settles the job:

* the handler returns: the job is acked (done).
* the handler raises JobFailed(retryable=False): the job is buried in the
  failure bin with its code, and never retried.
* the handler raises JobFailed(retryable=True): nothing is called; the lease
  runs out and the queue hands the job out again later. The lease length acts
  as a fixed back-off.
* the lease is lost (LeaseLost from a heartbeat, ack or bury): the job has
  already been handed to another delivery, so this worker leaves it alone.
  That is normal, not an error.
* anything else is a bug and propagates. The job is not acked, so the queue
  hands it out again, and after the maximum attempts it lands in the failure
  bin. There is no blanket ``except Exception`` here on purpose.

PROVISIONAL: the retry back-off is the fixed lease length. Exponential
back-off with jitter needs the queue settings, which are Vrushit's.

Why one bad job cannot block the others: while a job is leased it is hidden,
and each ``run_once`` handles exactly one job, so the jobs behind a failing one
are still handed out. (The test queue also puts a returning job at the back of
the line; a standard SQS queue does not promise order, but still hides leased
jobs.)
"""

from collections.abc import Callable

from kaagaz.ingestion.ports import Job
from kaagaz.jobs.ports import LeaseLost, WorkQueue

# Called by a long-running handler to say "still working", which renews the
# lease so the job is not handed to another worker.
Heartbeat = Callable[[], None]
Handler = Callable[[Job, Heartbeat], None]


class JobFailed(Exception):
    """A handler's way to report a failure. ``code`` is short and safe to log."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class Worker:
    def __init__(self, queue: WorkQueue, handler: Handler) -> None:
        self._queue = queue
        self._handler = handler

    def run_once(self) -> bool:
        """Process one job. Returns False when the queue had nothing ready."""
        delivery = self._queue.receive()
        if delivery is None:
            return False

        def heartbeat() -> None:
            self._queue.extend(delivery.receipt)

        try:
            try:
                self._handler(delivery.job, heartbeat)
            except JobFailed as failure:
                if not failure.retryable:
                    self._queue.bury(delivery.receipt, failure.code)
                return True
            self._queue.ack(delivery.receipt)
        except LeaseLost:
            pass  # another delivery owns the job now
        return True
