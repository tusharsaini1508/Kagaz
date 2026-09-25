"""The virus scan gate, the first step of every job.

Deny by default: only an explicit ``Verdict.CLEAN`` lets a file through.

* CLEAN: the document is marked clean and later steps may open it.
* INFECTED or UNSCANNABLE (for example encrypted, or too big for the
  scanner), or any value that is not a Verdict: the file is quarantined, the
  document is marked rejected, and the job fails for good.
* The scanner is down or times out (ScannerError): the job fails but may be
  retried. The document stays unscanned, so no later step will open it.

Later steps call ``require_clean`` before touching a file, so a file that was
never scanned, or failed the scan, cannot be opened by mistake.

PROVISIONAL: which scanner, where the scan runs and where quarantined files
go are open questions (PRD question 4). The scanner and quarantine are ports
so those answers land in their adapters. There is no default scanner, so a
worker cannot be built that skips the scan.
"""

from enum import Enum
from typing import Protocol

from kaagaz.ingestion.ports import BlobNotFound, BlobStorage, Job
from kaagaz.jobs.worker import JobFailed


class Verdict(Enum):
    CLEAN = "clean"
    INFECTED = "infected"
    UNSCANNABLE = "unscannable"


class DocumentStatus(Enum):
    RECEIVED = "received"
    CLEAN = "clean"
    REJECTED = "rejected"


class ScannerError(Exception):
    """The scanner could not give a verdict (down, timed out)."""


class Scanner(Protocol):
    def scan(self, data: bytes) -> Verdict: ...


class Quarantine(Protocol):
    def quarantine(self, customer_id: str, document_id: str) -> None:
        """Move the file where normal reads (BlobStorage.get) cannot reach it."""
        ...


class StatusStore(Protocol):
    def get_status(self, customer_id: str, document_id: str) -> DocumentStatus | None: ...

    def set_status(self, customer_id: str, document_id: str, status: DocumentStatus) -> None: ...


# What the customer sees for each rejection. No scanner names or details.
CUSTOMER_MESSAGES = {
    "virus_found": "This file failed the virus check and was not processed.",
    "unscannable": "This file could not be checked for viruses, so it was not processed.",
}


class ScanGate:
    def __init__(
        self,
        storage: BlobStorage,
        scanner: Scanner,
        quarantine: Quarantine,
        statuses: StatusStore,
    ) -> None:
        self._storage = storage
        self._scanner = scanner
        self._quarantine = quarantine
        self._statuses = statuses

    def check(self, job: Job) -> None:
        """Scan the job's file. Returns only if it is clean."""
        customer_id, document_id = job.customer_id, job.document_id
        try:
            data = self._storage.get(customer_id, document_id)
        except BlobNotFound:
            # Includes a job naming another customer's document: nothing read.
            raise JobFailed("document_missing", retryable=False) from None

        try:
            verdict = self._scanner.scan(data)
        except ScannerError:
            raise JobFailed("scanner_unavailable", retryable=True) from None

        if verdict is Verdict.CLEAN:
            self._statuses.set_status(customer_id, document_id, DocumentStatus.CLEAN)
            return

        code = "virus_found" if verdict is Verdict.INFECTED else "unscannable"
        self._quarantine.quarantine(customer_id, document_id)
        self._statuses.set_status(customer_id, document_id, DocumentStatus.REJECTED)
        raise JobFailed(code, retryable=False)


def require_clean(statuses: StatusStore, job: Job) -> None:
    """Refuse to go on unless this customer's document passed the scan."""
    if statuses.get_status(job.customer_id, job.document_id) is not DocumentStatus.CLEAN:
        raise JobFailed("not_scanned", retryable=False)
