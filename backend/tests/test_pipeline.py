"""The whole Sprint 1 flow with fakes: upload -> queue -> worker -> pieces.

These tests prove the steps are wired in the right order. They do not prove
the real database, storage, queue or scanner work: those do not exist yet.
"""

import io
import unittest
from dataclasses import dataclass

from kaagaz.ingestion import sniff
from kaagaz.ingestion.ports import Job
from kaagaz.ingestion.service import UploadService
from kaagaz.jobs.worker import JobFailed, Worker
from kaagaz.masking.identity import IndianIdMasker
from kaagaz.pipeline import DocumentProcessor, IdentityMasker
from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.socket import ReaderSocket
from kaagaz.scanning.gate import DocumentStatus, ScanGate, Verdict
from tests.fakes import (
    FakeMasker,
    FakeScanner,
    MemoryPieces,
    MemoryRepository,
    MemoryStatuses,
    MemoryStorage,
)
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
    scanner: FakeScanner
    repo: MemoryRepository
    gate: ScanGate


def build(verdict: Verdict = Verdict.CLEAN, masker: IdentityMasker | None = None) -> System:
    clock = FakeClock()
    queue = LeaseQueue(clock, lease_seconds=30, max_attempts=3)
    repo, storage, statuses, pieces = MemoryRepository(), MemoryStorage(), MemoryStatuses(), MemoryPieces()
    upload = UploadService(TEST_POLICY, repo, storage, queue, new_id=SeqIds())
    scanner = FakeScanner(verdict)
    gate = ScanGate(storage, scanner, storage, statuses)
    socket = ReaderSocket({sniff.TEXT: CsvReader(max_cells=10_000)})
    processor = DocumentProcessor(gate, statuses, repo, socket, masker or FakeMasker(), pieces)
    return System(
        upload, Worker(queue, processor), processor, queue, clock, statuses, pieces, storage, scanner, repo, gate
    )


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

    def test_identity_numbers_are_masked_in_pieces_before_they_are_saved(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(b"name,id\nAsha,SECRET\n")).document_id
        system.worker.run_once()
        texts = [p.text for p in system.pieces.for_document(CUSTOMER, doc)]
        self.assertEqual(texts, ["A: name | B: id", "A: Asha | B: ******"])
        self.assertFalse(any(FakeMasker.MARKER in t for t in texts))

    def test_real_masker_keeps_pan_and_aadhaar_out_of_stored_pieces(self) -> None:
        system = build(masker=IndianIdMasker())
        fake = b"name,pan,aadhaar\nAsha,ABCDE1234F,2345 6789 0123\n"  # FAKE numbers
        doc = system.upload.accept(CUSTOMER, io.BytesIO(fake)).document_id
        system.worker.run_once()
        stored = " ".join(p.text for p in system.pieces.for_document(CUSTOMER, doc))
        self.assertNotIn("ABCDE1234F", stored)
        self.assertNotIn("2345 6789", stored)
        self.assertIn("XXXXXX234F", stored)

    def test_file_changed_after_upload_is_refused(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id
        system.storage.put(CUSTOMER, doc, io.BytesIO(b"swapped,content\n"))
        system.worker.run_once()
        self.assertEqual([f.code for f in system.queue.failed.values()], ["content_changed"])
        self.assertEqual(system.pieces.for_document(CUSTOMER, doc), [])

    def test_file_without_a_record_is_never_read_or_scanned(self) -> None:
        system = build()
        system.storage.put(CUSTOMER, "orphan", io.BytesIO(CSV))  # a file, no record
        with self.assertRaises(JobFailed) as ctx:
            system.processor(Job(CUSTOMER, "orphan"), lambda: None)
        self.assertEqual(ctx.exception.code, "document_missing")
        self.assertEqual(system.scanner.scanned, [])

    def test_document_rejected_during_processing_writes_no_pieces(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id

        class RejectingMasker(FakeMasker):
            # Simulates an overlapping delivery rejecting the file mid-run.
            def mask(self, text: str) -> str:
                system.statuses.set_status(CUSTOMER, doc, DocumentStatus.REJECTED)
                return super().mask(text)

        processor = DocumentProcessor(
            system.gate, system.statuses, system.repo,
            ReaderSocket({sniff.TEXT: CsvReader(max_cells=100)}), RejectingMasker(), system.pieces,
        )
        with self.assertRaises(JobFailed) as ctx:
            processor(Job(CUSTOMER, doc), lambda: None)
        self.assertEqual(ctx.exception.code, "not_scanned")
        self.assertEqual(system.pieces.for_document(CUSTOMER, doc), [])

    def test_a_later_rejection_removes_pieces_from_an_earlier_clean_run(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id
        system.worker.run_once()
        self.assertEqual(len(system.pieces.for_document(CUSTOMER, doc)), 3)

        system.scanner.verdict = Verdict.INFECTED  # new signatures on a rerun
        with self.assertRaises(JobFailed):
            system.processor(Job(CUSTOMER, doc), lambda: None)
        self.assertEqual(system.pieces.for_document(CUSTOMER, doc), [])

    def test_rejected_document_is_never_rescanned_or_read(self) -> None:
        system = build()
        doc = system.upload.accept(CUSTOMER, io.BytesIO(CSV)).document_id
        system.statuses.set_status(CUSTOMER, doc, DocumentStatus.REJECTED)
        system.worker.run_once()
        self.assertEqual([f.code for f in system.queue.failed.values()], ["rejected"])
        self.assertEqual(system.pieces.for_document(CUSTOMER, doc), [])


if __name__ == "__main__":
    unittest.main()
