import io
import unittest

from kaagaz.ingestion.errors import BackendUnavailable
from kaagaz.ingestion.ports import BlobNotFound, Job
from kaagaz.jobs.worker import JobFailed, Worker
from kaagaz.scanning.gate import (
    CUSTOMER_MESSAGES,
    DocumentStatus,
    ScanGate,
    Verdict,
    require_clean,
)
from tests.fakes import FakeScanner, MemoryStatuses, MemoryStorage
from tests.lease_queue import FakeClock, LeaseQueue

CUSTOMER, DOC = "cust-a", "doc-1"
JOB = Job(CUSTOMER, DOC)
CONTENT = b"%PDF-1.7 made up"


def make_gate(scanner: FakeScanner) -> tuple[ScanGate, MemoryStorage, MemoryStatuses]:
    storage, statuses = MemoryStorage(), MemoryStatuses()
    storage.put(CUSTOMER, DOC, io.BytesIO(CONTENT))
    statuses.set_status(CUSTOMER, DOC, DocumentStatus.RECEIVED)
    return ScanGate(storage, scanner, storage, statuses), storage, statuses


class ScanGateTest(unittest.TestCase):
    def test_clean_file_is_marked_clean_and_stays_readable(self) -> None:
        scanner = FakeScanner(Verdict.CLEAN)
        gate, storage, statuses = make_gate(scanner)
        self.assertEqual(gate.check(JOB), CONTENT)  # the exact bytes scanned
        self.assertEqual(scanner.scanned, [CONTENT])
        self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.CLEAN)
        self.assertEqual(storage.get(CUSTOMER, DOC), CONTENT)

    def test_infected_file_is_quarantined_rejected_and_not_retried(self) -> None:
        gate, storage, statuses = make_gate(FakeScanner(Verdict.INFECTED))
        with self.assertRaises(JobFailed) as ctx:
            gate.check(JOB)
        self.assertEqual((ctx.exception.code, ctx.exception.retryable), ("virus_found", False))
        self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.REJECTED)
        with self.assertRaises(BlobNotFound):
            storage.get(CUSTOMER, DOC)
        self.assertEqual(storage.quarantined[(CUSTOMER, DOC)], CONTENT)

    def test_unscannable_file_is_treated_like_an_infected_one(self) -> None:
        gate, storage, statuses = make_gate(FakeScanner(Verdict.UNSCANNABLE))
        with self.assertRaises(JobFailed) as ctx:
            gate.check(JOB)
        self.assertEqual((ctx.exception.code, ctx.exception.retryable), ("unscannable", False))
        self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.REJECTED)
        self.assertEqual(storage.count(), 0)

    def test_anything_but_an_explicit_clean_verdict_is_refused(self) -> None:
        for odd in (None, True, "clean", 0):
            with self.subTest(verdict=odd):
                gate, _, statuses = make_gate(FakeScanner(odd))
                with self.assertRaises(JobFailed) as ctx:
                    gate.check(JOB)
                self.assertEqual(ctx.exception.code, "unscannable")
                self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.REJECTED)

    def test_scanner_down_retries_without_letting_the_file_through(self) -> None:
        gate, storage, statuses = make_gate(FakeScanner(error=True))
        with self.assertRaises(JobFailed) as ctx:
            gate.check(JOB)
        self.assertEqual((ctx.exception.code, ctx.exception.retryable), ("scanner_unavailable", True))
        self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.RECEIVED)
        self.assertEqual(storage.get(CUSTOMER, DOC), CONTENT)  # not quarantined yet

    def test_missing_file_fails_for_good(self) -> None:
        gate, _, _ = make_gate(FakeScanner(Verdict.CLEAN))
        with self.assertRaises(JobFailed) as ctx:
            gate.check(Job(CUSTOMER, "no-such-doc"))
        self.assertEqual((ctx.exception.code, ctx.exception.retryable), ("document_missing", False))

    def test_rejected_document_is_refused_without_being_read_or_rescanned(self) -> None:
        scanner = FakeScanner(Verdict.CLEAN)
        gate, _, statuses = make_gate(scanner)
        statuses.set_status(CUSTOMER, DOC, DocumentStatus.REJECTED)
        with self.assertRaises(JobFailed) as ctx:
            gate.check(JOB)
        self.assertEqual((ctx.exception.code, ctx.exception.retryable), ("rejected", False))
        self.assertEqual(scanner.scanned, [])
        self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.REJECTED)

    def test_status_is_rejected_even_if_moving_to_quarantine_fails(self) -> None:
        class BrokenQuarantine:
            def quarantine(self, customer_id: str, document_id: str) -> None:
                raise BackendUnavailable("storage down")

        storage, statuses = MemoryStorage(), MemoryStatuses()
        storage.put(CUSTOMER, DOC, io.BytesIO(CONTENT))
        gate = ScanGate(storage, FakeScanner(Verdict.INFECTED), BrokenQuarantine(), statuses)
        with self.assertRaises(BackendUnavailable):
            gate.check(JOB)
        self.assertIs(statuses.get_status(CUSTOMER, DOC), DocumentStatus.REJECTED)

    def test_every_rejection_code_has_a_plain_customer_message(self) -> None:
        self.assertEqual(set(CUSTOMER_MESSAGES), {"virus_found", "unscannable"})
        for message in CUSTOMER_MESSAGES.values():
            self.assertTrue(message.endswith("."))


class RequireCleanTest(unittest.TestCase):
    def test_only_clean_documents_pass(self) -> None:
        for status in (None, DocumentStatus.RECEIVED, DocumentStatus.REJECTED):
            with self.subTest(status=status):
                statuses = MemoryStatuses()  # fresh: REJECTED is final in the store
                if status is not None:
                    statuses.set_status(CUSTOMER, DOC, status)
                with self.assertRaises(JobFailed) as ctx:
                    require_clean(statuses, JOB)
                self.assertEqual(ctx.exception.code, "not_scanned")
        clean = MemoryStatuses()
        clean.set_status(CUSTOMER, DOC, DocumentStatus.CLEAN)
        require_clean(clean, JOB)  # does not raise


class GateInWorkerTest(unittest.TestCase):
    def test_infected_job_goes_to_the_failure_bin_after_one_attempt(self) -> None:
        clock = FakeClock()
        queue = LeaseQueue(clock, lease_seconds=30, max_attempts=3)
        queue.enqueue(JOB)
        gate, _, _ = make_gate(FakeScanner(Verdict.INFECTED))
        worker = Worker(queue, lambda job, beat: gate.check(job))

        worker.run_once()
        clock.advance(300)
        self.assertFalse(worker.run_once())
        (failed,) = queue.failed.values()
        self.assertEqual((failed.code, failed.attempts), ("virus_found", 1))


if __name__ == "__main__":
    unittest.main()
