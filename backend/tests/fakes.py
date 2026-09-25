"""In-memory stand-ins for the database, file storage and queue.

Test-only. They follow the port contracts in kaagaz.ingestion.ports, keyed by
customer first, so a cross-customer test can actually fail. They are never
used by product code.
"""

import threading
from typing import BinaryIO

from kaagaz.ingestion.errors import BackendUnavailable
from kaagaz.ingestion.ports import BlobNotFound, DocumentRecord, Job


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


class MemoryQueue:
    """Records enqueued jobs in order."""

    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.fail_enqueue = False

    def enqueue(self, job: Job) -> None:
        if self.fail_enqueue:
            raise BackendUnavailable("queue down")
        self.jobs.append(job)
