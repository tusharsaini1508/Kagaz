"""Process one uploaded document: the worker's job handler.

The steps, in order, for one (customer, document):

1. Scan it (ScanGate). Nothing below runs unless it is clean.
2. Check again that it is marked clean, then look up its record for this
   customer only.
3. Read it through the reader socket. A type with no reader yet (scans and
   photos in Sprint 1) is marked "needs a reader" and the job ends normally.
4. Split the text into pieces, one per row, and save them.
5. Mark the document ready.

Running the same job twice is safe: pieces are replaced, never appended, so a
redelivered job cannot create duplicate pieces (queues deliver at least once).

PROVISIONAL: file preparation (#17) and page pictures (#18) belong between
steps 2 and 3. They wait for approved libraries.
"""

from typing import Protocol

from kaagaz.chunking.rows import Piece, pieces_from_rows
from kaagaz.ingestion.ports import BlobStorage, DocumentRepository, Job
from kaagaz.jobs.worker import Heartbeat, JobFailed
from kaagaz.reading.socket import NoReader, ReaderSocket
from kaagaz.reading.spans import ReadError
from kaagaz.scanning.gate import DocumentStatus, ScanGate, StatusStore, require_clean


class PieceStore(Protocol):
    def replace(self, customer_id: str, document_id: str, pieces: list[Piece]) -> None:
        """Replace all of this document's pieces with ``pieces``."""
        ...


class DocumentProcessor:
    def __init__(
        self,
        gate: ScanGate,
        statuses: StatusStore,
        documents: DocumentRepository,
        storage: BlobStorage,
        socket: ReaderSocket,
        pieces: PieceStore,
    ) -> None:
        self._gate = gate
        self._statuses = statuses
        self._documents = documents
        self._storage = storage
        self._socket = socket
        self._pieces = pieces

    def __call__(self, job: Job, heartbeat: Heartbeat) -> None:
        self._gate.check(job)
        require_clean(self._statuses, job)
        heartbeat()

        record = self._documents.get(job.customer_id, job.document_id)
        if record is None:
            raise JobFailed("document_missing", retryable=False)
        data = self._storage.get(job.customer_id, job.document_id)

        try:
            spans = self._socket.read(record.detected_type, data)
        except NoReader:
            self._statuses.set_status(job.customer_id, job.document_id, DocumentStatus.NEEDS_READER)
            return
        except ReadError as error:
            raise JobFailed(error.code, retryable=False) from None
        heartbeat()

        pieces = pieces_from_rows(job.customer_id, job.document_id, spans)
        self._pieces.replace(job.customer_id, job.document_id, pieces)
        self._statuses.set_status(job.customer_id, job.document_id, DocumentStatus.READY)
