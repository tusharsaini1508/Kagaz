"""In-memory stand-ins for the database, file storage and queue.

Test-only. They follow the port contracts in kaagaz.ingestion.ports, keyed by
customer first, so a cross-customer test can actually fail. They are never
used by product code.
"""

import threading
from typing import Any, BinaryIO

from kaagaz.ingestion.errors import BackendUnavailable
from kaagaz.ingestion.ports import BlobNotFound, DocumentRecord, Job
from kaagaz.scanning.gate import DocumentStatus, ScannerError


class MemoryRepository:
    """Documents keyed by (customer_id, sha256): O(1) average lookup and insert.

    One lock makes check-and-insert atomic, like a UNIQUE (customer_id, sha256)
    constraint would in the real database.
    """

    def __init__(self) -> None:
        self._by_fingerprint: dict[tuple[str, str], DocumentRecord] = {}
        self._lock = threading.Lock()
        self.fail_add = False

    def find_by_fingerprint(self, customer_id: str, sha256: str) -> DocumentRecord | None:
        with self._lock:
            return self._by_fingerprint.get((customer_id, sha256))

    def add_if_absent(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
        if self.fail_add:
            raise BackendUnavailable("database down")
        key = (record.customer_id, record.sha256)
        with self._lock:
            existing = self._by_fingerprint.get(key)
            if existing is not None:
                return existing, False
            self._by_fingerprint[key] = record
            return record, True

    def remove(self, record: DocumentRecord) -> None:
        key = (record.customer_id, record.sha256)
        with self._lock:
            stored = self._by_fingerprint.get(key)
            if stored is not None and stored.document_id == record.document_id:
                del self._by_fingerprint[key]

    def records_for(self, customer_id: str) -> list[DocumentRecord]:
        with self._lock:
            return [r for (c, _), r in self._by_fingerprint.items() if c == customer_id]


class MemoryStorage:
    """Files keyed by (customer_id, document_id). No key strings are built, so
    no storage naming rule (#11) is invented."""

    def __init__(self) -> None:
        self._blobs: dict[tuple[str, str], bytes] = {}
        self.quarantined: dict[tuple[str, str], bytes] = {}
        self._lock = threading.Lock()
        self.fail_put = False

    def put(self, customer_id: str, document_id: str, data: BinaryIO) -> None:
        if self.fail_put:
            raise BackendUnavailable("storage down")
        content = data.read()
        with self._lock:
            self._blobs[(customer_id, document_id)] = content

    def get(self, customer_id: str, document_id: str) -> bytes:
        with self._lock:
            try:
                return self._blobs[(customer_id, document_id)]
            except KeyError:
                raise BlobNotFound(document_id) from None

    def delete(self, customer_id: str, document_id: str) -> None:
        with self._lock:
            self._blobs.pop((customer_id, document_id), None)

    def count(self) -> int:
        with self._lock:
            return len(self._blobs)

    # Quarantine port (kaagaz.scanning.gate.Quarantine): the file moves to a
    # separate dict that get() never reads.
    def quarantine(self, customer_id: str, document_id: str) -> None:
        with self._lock:
            content = self._blobs.pop((customer_id, document_id), None)
            if content is not None:
                self.quarantined[(customer_id, document_id)] = content


class MemoryStatuses:
    """Document status keyed by (customer_id, document_id)."""

    def __init__(self) -> None:
        self._statuses: dict[tuple[str, str], DocumentStatus] = {}

    def get_status(self, customer_id: str, document_id: str) -> DocumentStatus | None:
        return self._statuses.get((customer_id, document_id))

    def set_status(self, customer_id: str, document_id: str, status: DocumentStatus) -> None:
        self._statuses[(customer_id, document_id)] = status


class FakeScanner:
    """Returns a preset verdict, or raises ScannerError. Records what it saw."""

    def __init__(self, verdict: object = None, *, error: bool = False) -> None:
        self._verdict = verdict
        self._error = error
        self.scanned: list[bytes] = []

    def scan(self, data: bytes) -> Any:
        self.scanned.append(data)
        if self._error:
            raise ScannerError("scanner down")
        return self._verdict


class MemoryQueue:
    """Records enqueued jobs in order."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.fail_enqueue = False

    def enqueue(self, job: Job) -> None:
        if self.fail_enqueue:
            raise BackendUnavailable("queue down")
        self.jobs.append(job)
