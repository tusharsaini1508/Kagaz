"""In-memory stand-ins for the database, file storage and queue.

Test-only. They follow the port contracts in kaagaz.ingestion.ports, keyed by
customer first, so a cross-customer test can actually fail. They are never
used by product code.
"""

import threading
from typing import Any, BinaryIO

from kaagaz.chunking.rows import Piece
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
        self._by_id: dict[tuple[str, str], DocumentRecord] = {}
        self._lock = threading.Lock()
        self.fail_add = False
        self.fail_remove = False

    def get(self, customer_id: str, document_id: str) -> DocumentRecord | None:
        with self._lock:
            return self._by_id.get((customer_id, document_id))

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
            self._by_id[(record.customer_id, record.document_id)] = record
            return record, True

    def remove(self, record: DocumentRecord) -> None:
        if self.fail_remove:
            raise BackendUnavailable("database down")
        key = (record.customer_id, record.sha256)
        with self._lock:
            stored = self._by_fingerprint.get(key)
            if stored is not None and stored.document_id == record.document_id:
                del self._by_fingerprint[key]
                del self._by_id[(record.customer_id, record.document_id)]

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
        self.fail_delete = False
        self.last_put_stream: BinaryIO | None = None

    def put(self, customer_id: str, document_id: str, data: BinaryIO) -> None:
        self.last_put_stream = data
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
        if self.fail_delete:
            raise BackendUnavailable("storage down")
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


class MemoryPieces:
    """Pieces keyed by (customer_id, document_id). replace() swaps the whole
    list, so running a job twice never duplicates pieces."""

    def __init__(self) -> None:
        self._pieces: dict[tuple[str, str], list[Piece]] = {}

    def replace(self, customer_id: str, document_id: str, pieces: list[Piece]) -> None:
        self._pieces[(customer_id, document_id)] = list(pieces)

    def for_document(self, customer_id: str, document_id: str) -> list[Piece]:
        return list(self._pieces.get((customer_id, document_id), []))


class FakeMasker:
    """Stands in for the real masking rule (PRD question 1, Vrushit's).

    Masks the made-up marker word ``SECRET`` so tests can prove masking runs
    on every value before it is stored. It knows nothing about real Aadhaar
    or PAN formats, and must never be used outside tests.
    """

    MARKER = "SECRET"

    def mask(self, text: str) -> str:
        return text.replace(self.MARKER, "*" * len(self.MARKER))
