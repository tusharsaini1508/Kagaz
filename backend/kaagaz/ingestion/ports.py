"""What the upload service needs from the database, file storage and queue.

These are interfaces only. The real ones (PostgreSQL with the customer
separation rule from #2, S3 with the naming rule from #11, SQS) are not
decided yet, so the service is written against these contracts and tested
with in-memory fakes that live under tests/.

Every method takes ``customer_id`` first. There is no method that reads or
lists across customers (CLAUDE.md never-do 1).

PROVISIONAL: the record fields are a placeholder until the database design
(#1) is written.
"""

from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """One stored file. There is deliberately no file name field: a name can
    contain a PAN or Aadhaar number (PRD question 1)."""

    customer_id: str
    document_id: str
    sha256: str
    size: int
    detected_type: str


@dataclass(frozen=True, slots=True)
class Job:
    """A request to process one document.

    It carries the customer so the worker can set the current customer before
    its first query, and carries ids only, never the file or its name.
    """

    customer_id: str
    document_id: str


class BlobNotFound(Exception):
    """No file with this id exists for this customer."""


class DocumentRepository(Protocol):
    def find_by_fingerprint(self, customer_id: str, sha256: str) -> DocumentRecord | None:
        """This customer's document with this fingerprint, if any."""
        ...

    def add_if_absent(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
        """Insert unless this customer already has this fingerprint.

        Must be atomic per (customer_id, sha256), so two identical uploads at
        the same moment cannot both be inserted. Returns the stored record and
        True if it was inserted, or the existing record and False.
        """
        ...

    def remove(self, record: DocumentRecord) -> None:
        """Undo an insert. Removes only if the stored document id matches."""
        ...


class BlobStorage(Protocol):
    """File storage. The adapter owns how keys are named (#11)."""

    def put(self, customer_id: str, document_id: str, data: BinaryIO) -> None: ...

    def get(self, customer_id: str, document_id: str) -> bytes:
        """The file's bytes. Raises BlobNotFound for another customer's id."""
        ...

    def delete(self, customer_id: str, document_id: str) -> None: ...


class JobQueue(Protocol):
    def enqueue(self, job: Job) -> None: ...
