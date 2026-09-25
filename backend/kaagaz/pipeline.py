"""Process one uploaded document: the worker's job handler.

The steps, in order, for one (customer, document):

1. Look up this customer's record. A job naming another customer's document
   stops here, before any file is read.
2. Scan the file (ScanGate). Nothing below runs unless it is clean, and the
   bytes used below are exactly the bytes that were scanned.
3. Check the scanned bytes still match the fingerprint taken at upload.
4. Read them through the reader socket. A type with no reader yet (scans and
   photos in Sprint 1) is marked "needs a reader" and the job ends normally.
5. Mask identity numbers in every span, text and raw value, before anything
   is kept (CLAUDE.md never-do 3).
6. Split the text into pieces, one per row, and save them. Mark it ready.

Running the same job twice is safe: pieces are replaced, never appended, so a
redelivered job cannot create duplicate pieces (queues deliver at least once).

PROVISIONAL: file preparation (#17) and page pictures (#18) belong between
steps 3 and 4. They wait for approved libraries. The masking rule is
Vrushit's (PRD question 1); there is no default masker, so the pipeline cannot
be built without one.
"""

import hashlib
from typing import Protocol

from kaagaz.chunking.rows import Piece, pieces_from_rows
from kaagaz.ingestion.ports import DocumentRepository, Job
from kaagaz.jobs.worker import Heartbeat, JobFailed
from kaagaz.reading.socket import NoReader, ReaderSocket
from kaagaz.reading.spans import ReadError, Span
from kaagaz.scanning.gate import DocumentStatus, ScanGate, StatusStore, require_clean


class PieceStore(Protocol):
    def replace(self, customer_id: str, document_id: str, pieces: list[Piece]) -> None:
        """Replace all of this document's pieces with ``pieces``."""
        ...


class IdentityMasker(Protocol):
    def mask(self, text: str) -> str:
        """Return ``text`` with every full Aadhaar or PAN number masked."""
        ...


class DocumentProcessor:
    def __init__(
        self,
        gate: ScanGate,
        statuses: StatusStore,
        documents: DocumentRepository,
        socket: ReaderSocket,
        masker: IdentityMasker,
        pieces: PieceStore,
    ) -> None:
        self._gate = gate
        self._statuses = statuses
        self._documents = documents
        self._socket = socket
        self._masker = masker
        self._pieces = pieces

    def __call__(self, job: Job, heartbeat: Heartbeat) -> None:
        record = self._documents.get(job.customer_id, job.document_id)
        if record is None:
            raise JobFailed("document_missing", retryable=False)

        data = self._gate.check(job)
        if hashlib.sha256(data).hexdigest() != record.sha256:
            raise JobFailed("content_changed", retryable=False)
        heartbeat()

        failure_code = None
        try:
            spans = self._socket.read(record.detected_type, data)
        except NoReader:
            self._statuses.set_status(job.customer_id, job.document_id, DocumentStatus.NEEDS_READER)
            return
        except ReadError as error:
            failure_code = error.code
        if failure_code is not None:
            # Raised outside the except block, so no parser error (which can
            # quote document content) is chained onto it.
            raise JobFailed(failure_code, retryable=False)
        heartbeat()

        masked = [self._mask(span) for span in spans]
        pieces = pieces_from_rows(job.customer_id, job.document_id, masked)
        require_clean(self._statuses, job)  # still clean just before writing
        self._pieces.replace(job.customer_id, job.document_id, pieces)
        self._statuses.set_status(job.customer_id, job.document_id, DocumentStatus.READY)

    def _mask(self, span: Span) -> Span:
        return Span(self._masker.mask(span.text), self._masker.mask(span.raw), span.location)
