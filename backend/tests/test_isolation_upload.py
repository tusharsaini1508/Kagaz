"""Customer isolation for upload (#23). Marked ``isolation`` by conftest.py."""

import io
import unittest

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


if __name__ == "__main__":
    unittest.main()
