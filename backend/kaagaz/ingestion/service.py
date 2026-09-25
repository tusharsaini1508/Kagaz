"""Accept one upload for one customer (issue #14).

The steps, in order:

1. Read the stream once: fingerprint, size check, spooled copy (spool.py).
2. Refuse empty files and types that are not allowed (sniff.py).
3. If this customer already has this fingerprint, reply "duplicate" and stop.
4. Store the file, record it, queue a job.

The customer id is an argument. It must come from the server side (how the
server knows the customer is PRD question 3), never from the request body or
the file. The service never sees the file name.

Invariant: a record exists only if its file is stored and its job is queued.
Each partial failure is undone in reverse order:

* storing fails: nothing was recorded, the error propagates.
* recording fails: the stored file is deleted, the error propagates.
* lost a race (another identical upload was recorded first): our stored file
  is deleted and the winner's document is returned as a duplicate.
* queueing fails: the record and the file are removed, so the customer can
  simply upload again. Without this undo, the retry would be reported as a
  duplicate of a document that is never processed.

Every undo step runs even if an earlier one fails, and the original error is
always the one raised; a failed undo step is added to it as a note.

Known leftovers, when the undo itself cannot reach the backend: a record with
no job, or a stored file with no record. Finding and fixing those later (an
outbox, or re-queueing records that never ran) is database and queue design,
so it is PROVISIONAL and Vrushit's (#1, #16). Also rare: a race loser is told
"duplicate" of a winner that then fails to queue and is rolled back.

PROVISIONAL: document ids are random UUID4 here; the id format belongs to the
database design (#1).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

from kaagaz.ingestion.errors import BackendUnavailable, RejectCode, UploadRejected
from kaagaz.ingestion.policy import UploadPolicy
from kaagaz.ingestion.ports import (
    BlobStorage,
    DocumentRecord,
    DocumentRepository,
    Job,
    JobQueue,
)
from kaagaz.ingestion.sniff import detect_type
from kaagaz.ingestion.spool import read_limited


@dataclass(frozen=True, slots=True)
class UploadResult:
    document_id: str
    duplicate: bool


def _new_document_id() -> str:
    # Random, so ids reveal nothing about the file and cannot be guessed.
    return str(uuid.uuid4())


class UploadService:
    def __init__(
        self,
        policy: UploadPolicy,
        repository: DocumentRepository,
        storage: BlobStorage,
        queue: JobQueue,
        new_id: Callable[[], str] = _new_document_id,
    ) -> None:
        self._policy = policy
        self._repository = repository
        self._storage = storage
        self._queue = queue
        self._new_id = new_id

    def accept(self, customer_id: str, stream: BinaryIO) -> UploadResult:
        if not isinstance(customer_id, str) or not customer_id:
            raise ValueError("customer_id is required")

        with read_limited(stream, self._policy.max_bytes) as spooled:
            if spooled.size == 0:
                raise UploadRejected(RejectCode.EMPTY_FILE)
            detected = detect_type(spooled.head)
            if detected is None or detected not in self._policy.allowed_types:
                raise UploadRejected(RejectCode.UNSUPPORTED_TYPE)

            # Fast path: a duplicate never touches storage. The lookup is for
            # this customer only, so it cannot reveal other customers' files.
            existing = self._repository.find_by_fingerprint(customer_id, spooled.sha256)
            if existing is not None:
                return UploadResult(existing.document_id, duplicate=True)

            record = DocumentRecord(
                customer_id=customer_id,
                document_id=self._new_id(),
                sha256=spooled.sha256,
                size=spooled.size,
                detected_type=detected,
            )
            # Store the exact bytes that were hashed.
            self._storage.put(customer_id, record.document_id, spooled.file)

        def delete_file() -> None:
            self._storage.delete(customer_id, record.document_id)

        def remove_record() -> None:
            self._repository.remove(record)

        try:
            stored, created = self._repository.add_if_absent(record)
        except BackendUnavailable as error:
            _undo(error, delete_file)
            raise

        if not created:
            self._storage.delete(customer_id, record.document_id)
            return UploadResult(stored.document_id, duplicate=True)

        try:
            self._queue.enqueue(Job(customer_id=customer_id, document_id=record.document_id))
        except BackendUnavailable as error:
            _undo(error, remove_record, delete_file)
            raise

        return UploadResult(record.document_id, duplicate=False)


def _undo(error: BackendUnavailable, *steps: Callable[[], None]) -> None:
    """Run every undo step, even if one fails, without hiding ``error``.

    A step that fails is recorded on ``error`` by name only, never with data.
    Only BackendUnavailable is caught; any other exception is a bug and
    propagates.
    """
    for step in steps:
        try:
            step()
        except BackendUnavailable:
            error.add_note(f"undo step failed: {step.__name__}")
