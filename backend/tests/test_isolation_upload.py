"""Customer isolation for upload (#23). Marked ``isolation`` by conftest.py."""

import io
import unittest

from kaagaz.ingestion.ports import BlobNotFound
from tests.support import PDF_BYTES, make_service

A, B = "cust-a", "cust-b"


class IsolationUploadTest(unittest.TestCase):
    def test_same_bytes_from_two_customers_are_two_documents(self) -> None:
        service, repo, storage, queue = make_service()
        a = service.accept(A, io.BytesIO(PDF_BYTES))
        b = service.accept(B, io.BytesIO(PDF_BYTES))

        # B is not told that A already holds this file.
        self.assertFalse(b.duplicate)
        self.assertNotEqual(a.document_id, b.document_id)
        self.assertEqual(len(repo.records_for(A)), 1)
        self.assertEqual(len(repo.records_for(B)), 1)
        self.assertEqual(storage.count(), 2)
        self.assertEqual({j.customer_id for j in queue.jobs}, {A, B})

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
