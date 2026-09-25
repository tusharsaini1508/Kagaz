"""Customer isolation for the scan gate (#23). Marked ``isolation`` by conftest.py."""

import io
import unittest

from kaagaz.ingestion.ports import Job
from kaagaz.jobs.worker import JobFailed
from kaagaz.scanning.gate import DocumentStatus, ScanGate, Verdict, require_clean
from tests.fakes import FakeScanner, MemoryStatuses, MemoryStorage

A, B, DOC = "cust-a", "cust-b", "doc-1"


class IsolationScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.storage, self.statuses = MemoryStorage(), MemoryStatuses()
        self.storage.put(A, DOC, io.BytesIO(b"%PDF-1.7 made up"))
        self.statuses.set_status(A, DOC, DocumentStatus.RECEIVED)
        self.scanner = FakeScanner(Verdict.INFECTED)
        self.gate = ScanGate(self.storage, self.scanner, self.storage, self.statuses)

    def test_job_naming_another_customers_document_reads_nothing(self) -> None:
        with self.assertRaises(JobFailed) as ctx:
            self.gate.check(Job(B, DOC))
        self.assertEqual(ctx.exception.code, "document_missing")
        self.assertEqual(self.scanner.scanned, [])
        self.assertIs(self.statuses.get_status(A, DOC), DocumentStatus.RECEIVED)
        self.assertEqual(self.storage.count(), 1)  # A's file was not quarantined

    def test_quarantine_stays_with_the_same_customer(self) -> None:
        with self.assertRaises(JobFailed):
            self.gate.check(Job(A, DOC))
        self.assertEqual(list(self.storage.quarantined), [(A, DOC)])

    def test_clean_status_of_one_customer_does_not_clear_another(self) -> None:
        self.statuses.set_status(A, DOC, DocumentStatus.CLEAN)
        with self.assertRaises(JobFailed):
            require_clean(self.statuses, Job(B, DOC))


if __name__ == "__main__":
    unittest.main()
