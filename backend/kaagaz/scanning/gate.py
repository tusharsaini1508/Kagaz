"""The virus scan gate, the first step of every job.

Deny by default: only an explicit ``Verdict.CLEAN`` lets a file through.

* REJECTED is final: a rejected document is refused at once, never rescanned
  (a rescan with different signatures must not be able to clear it).

* CLEAN: the document is marked clean and later steps may open it.
* INFECTED or UNSCANNABLE (for example encrypted, or too big for the
  scanner), or any value that is not a Verdict: the file is quarantined, the
  document is marked rejected, and the job fails for good.
* The scanner is down or times out (ScannerError): the job fails but may be
  retried. The document stays unscanned, so no later step will open it.

``check`` returns the exact bytes it scanned. Callers read those bytes and
never fetch the file again, so what is read is always what was scanned.
Later steps call ``require_clean`` before writing results, so a file that was
never scanned, or failed the scan, cannot be used by mistake.

Adapter contract: status writes must be conditional in the real store (never
move out of REJECTED), because two deliveries of one job can overlap.

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
    """PROVISIONAL: the stored status model is database design (#1)."""

    # Not scanned yet. Upload does not write statuses yet, so a new document
    # has none (None), which the gate treats the same. Ask Vrushit (#1).
    RECEIVED = "received"
    CLEAN = "clean"  # passed the scan
    REJECTED = "rejected"  # failed the scan, quarantined
    NEEDS_READER = "needs_reader"  # clean, but no reader for its type yet (set by the pipeline)
    READY = "ready"  # read and split into pieces (set by the pipeline)


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


# Codes that mean the file failed the scan (now or earlier). Anything made
# from such a file must be removed.
REJECTION_CODES = frozenset({"virus_found", "unscannable", "rejected"})

# What the customer sees for each rejection. No scanner names or details.
# Read by the file list screen (#22) once it exists.
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

    def check(self, job: Job) -> bytes:
        """Scan the job's file and return the scanned bytes, only if clean."""
        customer_id, document_id = job.customer_id, job.document_id
        if self._statuses.get_status(customer_id, document_id) is DocumentStatus.REJECTED:
            raise JobFailed("rejected", retryable=False)
        # Errors are raised outside the except blocks, so an adapter's error
        # (which could hold scanner output or a path) is never chained on.
        data = _get_or_none(self._storage, customer_id, document_id)
        if data is None:
            # Includes a job naming another customer's document: nothing read.
            raise JobFailed("document_missing", retryable=False)

        verdict = _scan(self._scanner, data)
        if verdict is _SCANNER_FAILED:
            raise JobFailed("scanner_unavailable", retryable=True)

        if verdict is Verdict.CLEAN:
            self._statuses.set_status(customer_id, document_id, DocumentStatus.CLEAN)
            return data

        code = "virus_found" if verdict is Verdict.INFECTED else "unscannable"
        # Refuse first: if moving the file to quarantine fails, it is already
        # marked rejected and no step will use it.
        self._statuses.set_status(customer_id, document_id, DocumentStatus.REJECTED)
        self._quarantine.quarantine(customer_id, document_id)
        raise JobFailed(code, retryable=False)


def _get_or_none(storage: BlobStorage, customer_id: str, document_id: str) -> bytes | None:
    try:
        return storage.get(customer_id, document_id)
    except BlobNotFound:
        return None


# Marks "the scanner gave no answer". A dedicated object, not None, so a
# scanner that wrongly returns None is still treated as unscannable.
_SCANNER_FAILED = object()


def _scan(scanner: Scanner, data: bytes) -> object:
    """The scanner's answer, or _SCANNER_FAILED if it could not give one."""
    try:
        return scanner.scan(data)
    except ScannerError:
        return _SCANNER_FAILED


def require_clean(statuses: StatusStore, job: Job) -> None:
    """Refuse to go on unless this customer's document passed the scan."""
    if statuses.get_status(job.customer_id, job.document_id) is not DocumentStatus.CLEAN:
        raise JobFailed("not_scanned", retryable=False)
