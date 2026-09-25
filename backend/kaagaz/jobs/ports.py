"""What the worker needs from the queue.

The contract is the lease model SQS uses:

* ``receive`` hands out one job and hides it for a lease period. The job's
  attempt number goes up on every delivery, crashes included.
* ``ack`` removes the job for good once it is done.
* ``extend`` renews the lease, so a long job is not handed out again while it
  is still running.
* ``bury`` sends the job to the failure bin at once (a failure retrying
  cannot fix).
* A job whose lease runs out is handed out again. After the maximum number of
  attempts, the queue moves it to the failure bin itself.

Every delivery has its own receipt. ``ack``, ``extend`` and ``bury`` with an
old receipt raise LeaseLost, so a slow worker cannot finish a job that has
already been handed to someone else.

The lease length and the maximum attempts are queue settings, which are
Vrushit's (PRD section 6), so this file sets no values.
"""

from dataclasses import dataclass
from typing import Protocol

from kaagaz.ingestion.ports import Job


@dataclass(frozen=True, slots=True)
class Delivery:
    job: Job
    receipt: str
    attempt: int  # 1 on the first delivery


class LeaseLost(Exception):
    """The receipt is stale: the lease ran out or the job was handed out again."""


class WorkQueue(Protocol):
    def receive(self) -> Delivery | None: ...

    def ack(self, receipt: str) -> None: ...

    def extend(self, receipt: str) -> None: ...

    def bury(self, receipt: str, code: str) -> None: ...
