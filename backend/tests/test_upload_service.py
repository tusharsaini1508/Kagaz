import dataclasses
import io
import threading
import unittest
from typing import Any, cast

from kaagaz.ingestion import sniff
from kaagaz.ingestion.errors import BackendUnavailable, RejectCode, UploadRejected
from kaagaz.ingestion.policy import UploadPolicy
from kaagaz.ingestion.ports import DocumentRecord, Job
from kaagaz.ingestion.service import UploadService
from tests.fakes import MemoryQueue, MemoryRepository, MemoryStorage
from tests.support import PDF_BYTES, TEST_POLICY, TEXT_BYTES, make_service

CUSTOMER = "cust-a"


class AcceptTest(unittest.TestCase):
    def test_new_file_is_stored_recorded_and_queued_once(self) -> None:
        service, repo, storage, queue = make_service()
        result = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))

        self.assertFalse(result.duplicate)
        self.assertEqual(storage.get(CUSTOMER, result.document_id), PDF_BYTES)
        self.assertEqual(len(repo.records_for(CUSTOMER)), 1)
        self.assertEqual(queue.jobs, [Job(CUSTOMER, result.document_id)])

    def test_record_holds_fingerprint_size_and_detected_type(self) -> None:
        service, repo, _, _ = make_service()
        service.accept(CUSTOMER, io.BytesIO(TEXT_BYTES))
        (record,) = repo.records_for(CUSTOMER)
        self.assertEqual(record.size, len(TEXT_BYTES))
        self.assertEqual(record.detected_type, sniff.TEXT)
        self.assertEqual(len(record.sha256), 64)

    def test_record_has_no_file_name_field(self) -> None:
        names = {f.name for f in dataclasses.fields(DocumentRecord)}
        self.assertEqual(names, {"customer_id", "document_id", "sha256", "size", "detected_type"})

    def test_missing_customer_is_refused(self) -> None:
        service, _, storage, _ = make_service()
        for bad in ("", None):
            with self.assertRaises(ValueError):
                service.accept(cast(str, bad), io.BytesIO(PDF_BYTES))
        self.assertEqual(storage.count(), 0)


class DuplicateTest(unittest.TestCase):
    def test_same_file_twice_is_stored_once_and_says_duplicate(self) -> None:
        service, repo, storage, queue = make_service()
        first = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        second = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))

        self.assertTrue(second.duplicate)
        self.assertEqual(second.document_id, first.document_id)
        self.assertEqual(storage.count(), 1)
        self.assertEqual(len(repo.records_for(CUSTOMER)), 1)
        self.assertEqual(len(queue.jobs), 1)

    def test_files_one_byte_apart_are_not_duplicates(self) -> None:
        # The name is never an input, so "similar names" (#25) can only mean
        # nearly identical bytes. Different bytes are different documents.
        service, _, storage, _ = make_service()
        a = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        b = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES + b"1"))
        self.assertFalse(b.duplicate)
        self.assertNotEqual(a.document_id, b.document_id)
        self.assertEqual(storage.count(), 2)

    def test_lost_race_deletes_own_file_and_returns_the_winner(self) -> None:
        winner = DocumentRecord(CUSTOMER, "winner", "sha", 1, sniff.PDF)

        class RacingRepository(MemoryRepository):
            # Simulates another upload inserting between our check and insert.
            def find_by_fingerprint(self, customer_id: str, sha256: str) -> None:
                return None

            def add_if_absent(self, record: DocumentRecord) -> tuple[DocumentRecord, bool]:
                return winner, False

        storage, queue = MemoryStorage(), MemoryQueue()
        service = UploadService(TEST_POLICY, RacingRepository(), storage, queue)
        result = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))

        self.assertEqual(result.document_id, "winner")
        self.assertTrue(result.duplicate)
        self.assertEqual(storage.count(), 0)
        self.assertEqual(queue.jobs, [])

    def test_concurrent_identical_uploads_give_one_document(self) -> None:
        service, repo, storage, queue = make_service()
        threads_count = 8
        barrier = threading.Barrier(threads_count)
        results = []

        def upload() -> None:
            barrier.wait()
            results.append(service.accept(CUSTOMER, io.BytesIO(PDF_BYTES)))

        threads = [threading.Thread(target=upload) for _ in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        self.assertFalse(any(t.is_alive() for t in threads))

        self.assertEqual(len(repo.records_for(CUSTOMER)), 1)
        self.assertEqual(storage.count(), 1)
        self.assertEqual(len(queue.jobs), 1)
        self.assertEqual(sum(not r.duplicate for r in results), 1)
        self.assertEqual({r.document_id for r in results}, {queue.jobs[0].document_id})


class RejectTest(unittest.TestCase):
    def assert_rejected(self, data: bytes, code: RejectCode, policy: UploadPolicy = TEST_POLICY) -> None:
        """The upload is refused with ``code`` and nothing is stored, recorded or queued."""
        service, repo, storage, queue = make_service(policy)
        with self.assertRaises(UploadRejected) as ctx:
            service.accept(CUSTOMER, io.BytesIO(data))
        self.assertIs(ctx.exception.code, code)
        self.assertEqual(repo.records_for(CUSTOMER), [])
        self.assertEqual(storage.count(), 0)
        self.assertEqual(queue.jobs, [])

    def test_empty_file(self) -> None:
        self.assert_rejected(b"", RejectCode.EMPTY_FILE)

    def test_oversized_file(self) -> None:
        self.assert_rejected(b"%PDF-" + b"0" * TEST_POLICY.max_bytes, RejectCode.TOO_LARGE)

    def test_unrecognised_type(self) -> None:
        self.assert_rejected(b"\x7fELF\x02\x01\x01\x00rest", RejectCode.UNSUPPORTED_TYPE)

    def test_recognised_type_that_is_not_allowed(self) -> None:
        text_only = UploadPolicy(max_bytes=1024, allowed_types=frozenset({sniff.TEXT}))
        self.assert_rejected(PDF_BYTES, RejectCode.UNSUPPORTED_TYPE, text_only)

    def test_rejection_message_is_only_the_code(self) -> None:
        service, _, _, _ = make_service()
        with self.assertRaises(UploadRejected) as ctx:
            service.accept(CUSTOMER, io.BytesIO(b"\x7fELF secret-content"))
        self.assertEqual(str(ctx.exception), "unsupported_type")


class PartialFailureTest(unittest.TestCase):
    def test_storage_failure_leaves_no_record_and_no_job(self) -> None:
        service, repo, storage, queue = make_service()
        storage.fail_put = True
        with self.assertRaises(BackendUnavailable):
            service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        self.assertEqual(repo.records_for(CUSTOMER), [])
        self.assertEqual(queue.jobs, [])

    def test_database_failure_deletes_the_stored_file(self) -> None:
        service, repo, storage, queue = make_service()
        repo.fail_add = True
        with self.assertRaises(BackendUnavailable):
            service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        self.assertEqual(storage.count(), 0)
        self.assertEqual(queue.jobs, [])

    def test_queue_failure_undoes_everything_and_a_retry_works(self) -> None:
        service, repo, storage, queue = make_service()
        queue.fail_enqueue = True
        with self.assertRaises(BackendUnavailable):
            service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        self.assertEqual(repo.records_for(CUSTOMER), [])
        self.assertEqual(storage.count(), 0)

        queue.fail_enqueue = False
        retry = service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        self.assertFalse(retry.duplicate)
        self.assertEqual(len(queue.jobs), 1)


class FailedUndoTest(unittest.TestCase):
    def test_file_is_kept_while_its_record_could_not_be_removed(self) -> None:
        service, repo, storage, queue = make_service()
        queue.fail_enqueue = True
        repo.fail_remove = True
        with self.assertRaises(BackendUnavailable) as ctx:
            service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        self.assertEqual(str(ctx.exception), "queue down")  # the original error
        self.assertEqual(ctx.exception.__notes__, ["undo step failed: remove_record"])
        # Documented leftover: record and file kept together, no job. Never a
        # record pointing at a deleted file.
        (record,) = repo.records_for(CUSTOMER)
        self.assertEqual(storage.get(CUSTOMER, record.document_id), PDF_BYTES)
        self.assertEqual(queue.jobs, [])

    def test_database_failure_keeps_its_own_error_when_deleting_the_file_fails(self) -> None:
        service, repo, storage, queue = make_service()
        repo.fail_add = True
        storage.fail_delete = True
        with self.assertRaises(BackendUnavailable) as ctx:
            service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        self.assertEqual(str(ctx.exception), "database down")
        self.assertIn("undo step failed: delete_file", ctx.exception.__notes__)
        self.assertEqual(queue.jobs, [])

    def test_spooled_copy_is_closed_when_storing_fails(self) -> None:
        service, _, storage, _ = make_service()
        storage.fail_put = True
        with self.assertRaises(BackendUnavailable):
            service.accept(CUSTOMER, io.BytesIO(PDF_BYTES))
        assert storage.last_put_stream is not None
        self.assertTrue(storage.last_put_stream.closed)


class PolicyTest(unittest.TestCase):
    def test_policy_refuses_bad_values(self) -> None:
        cases: tuple[dict[str, Any], ...] = (
            {"max_bytes": 0, "allowed_types": frozenset({sniff.PDF})},
            {"max_bytes": 10, "allowed_types": frozenset()},
            {"max_bytes": 10, "allowed_types": frozenset({"exe"})},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                UploadPolicy(**kwargs)


if __name__ == "__main__":
    unittest.main()
