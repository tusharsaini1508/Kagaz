"""Contract tests for the ports, run against the in-memory fakes today.

They pin the behaviour every real adapter must have (PostgreSQL, S3) and
should be re-run against those adapters when they exist. They test the
fakes, not product code, so they are deliberately not in a
``test_isolation_*`` module: CI's isolation run is for product behaviour.
"""

import io
import unittest

from kaagaz.ingestion.ports import BlobNotFound
from tests.support import PDF_BYTES, make_service

A, B = "cust-a", "cust-b"


class PortContractTest(unittest.TestCase):
    def test_fingerprint_lookup_is_scoped_to_the_customer(self) -> None:
        service, repo, _, _ = make_service()
        service.accept(A, io.BytesIO(PDF_BYTES))
        (record,) = repo.records_for(A)
        self.assertIsNone(repo.find_by_fingerprint(B, record.sha256))

    def test_other_customer_cannot_read_the_file(self) -> None:
        service, _, storage, _ = make_service()
        a = service.accept(A, io.BytesIO(PDF_BYTES))
        with self.assertRaises(BlobNotFound):
            storage.get(B, a.document_id)

    def test_delete_with_wrong_customer_leaves_the_file(self) -> None:
        service, _, storage, _ = make_service()
        a = service.accept(A, io.BytesIO(PDF_BYTES))
        storage.delete(B, a.document_id)
        self.assertEqual(storage.get(A, a.document_id), PDF_BYTES)



if __name__ == "__main__":
    unittest.main()
