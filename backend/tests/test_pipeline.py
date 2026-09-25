"""The whole Sprint 1 flow with fakes: upload -> queue -> worker -> pieces.

These tests prove the steps are wired in the right order. They do not prove
the real database, storage, queue or scanner work: those do not exist yet.
"""

import io
import unittest
from dataclasses import dataclass

from kaagaz.ingestion import sniff
from kaagaz.ingestion.service import UploadService
from kaagaz.jobs.worker import Worker
from kaagaz.pipeline import DocumentProcessor
from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.socket import ReaderSocket
from kaagaz.scanning.gate import DocumentStatus, ScanGate, Verdict
from tests.fakes import FakeScanner, MemoryPieces, MemoryRepository, MemoryStatuses, MemoryStorage
from tests.lease_queue import FakeClock, LeaseQueue
from tests.support import PDF_BYTES, TEST_POLICY, SeqIds

CUSTOMER = "cust-a"
CSV = b"invoice,amount\nINV-1,100\nINV-2,250\n"


@dataclass
class System:
    upload: UploadService
    worker: Worker
    processor: DocumentProcessor
    queue: LeaseQueue
    clock: FakeClock
    statuses: MemoryStatuses
    pieces: MemoryPieces
    storage: MemoryStorage


def build(verdict: Verdict = Verdict.CLEAN) -> System:
    clock = FakeClock()
    queue = LeaseQueue(clock, lease_seconds=30, max_attempts=3)
    repo, storage, statuses, pieces = MemoryRepository(), MemoryStorage(), MemoryStatuses(), MemoryPieces()
    upload = UploadService(TEST_POLICY, repo, storage, queue, new_id=SeqIds())
    gate = ScanGate(storage, FakeScanner(verdict), storage, statuses)
    socket = ReaderSocket({sniff.TEXT: CsvReader(max_cells=10_000)})
    processor = DocumentProcessor(gate, statuses, repo, storage, socket, pieces)
    return System(upload, Worker(queue, processor), processor, queue, clock, statuses, pieces, storage)


class PipelineTest(unittest.TestCase):
    def test_clean_csv_becomes_one_piece_per_row_and_is_ready(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id

        self.assertTrue(system.worker.run_once())
        pieces = system.pieces.for_document(CUSTOMER, doc)
        self.assertEqual([p.text for p in pieces], [
            "A: invoice | B: amount",
            "A: INV-1 | B: 100",
            "A: INV-2 | B: 250",
        ])
        self.assertIs(system.statuses.get_status(CUSTOMER, doc), DocumentStatus.READY)
        self.assertEqual(system.queue.pending(), 0)

    def test_pdf_is_marked_needs_a_reader_and_the_job_ends_normally(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(PDF_BYTES)).document_id
        system.worker.run_once()
        self.assertIs(system.statuses.get_status(CUSTOMER, doc), DocumentStatus.NEEDS_READER)
        self.assertEqual(system.pieces.for_document(CUSTOMER, doc), [])
        self.assertEqual(system.queue.failed, {})

    def test_infected_file_is_never_read(self) -> None:
        system = build(Verdict.INFECTED)
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id
        system.worker.run_once()
        self.assertEqual(system.pieces.for_document(CUSTOMER, doc), [])
        self.assertIs(system.statuses.get_status(CUSTOMER, doc), DocumentStatus.REJECTED)
        self.assertEqual([f.code for f in system.queue.failed.values()], ["virus_found"])

    def test_broken_csv_fails_cleanly_and_the_next_file_still_runs(self) -> None:
        system = build()
        broken = system.upload.accept(CUSTOMER, io.BytesIO(b'a,"never closed\n')).document_id
        good = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id

        system.worker.run_once()
        system.worker.run_once()
        self.assertEqual([f.code for f in system.queue.failed.values()], ["malformed_csv"])
        self.assertEqual(system.pieces.for_document(CUSTOMER, broken), [])
        self.assertEqual(len(system.pieces.for_document(CUSTOMER, good)), 3)

    def test_running_the_same_job_twice_does_not_duplicate_pieces(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id
        delivery = system.queue.receive()
        assert delivery is not None
        system.processor(delivery.job, lambda: None)
        system.processor(delivery.job, lambda: None)  # a redelivery
        self.assertEqual(len(system.pieces.for_document(CUSTOMER, doc)), 3)


if __name__ == "__main__":
    unittest.main()
