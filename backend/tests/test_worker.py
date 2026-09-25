import unittest

from kaagaz.ingestion.ports import Job
from kaagaz.jobs.ports import LeaseLost
from kaagaz.jobs.worker import Heartbeat, JobFailed, Worker
from tests.lease_queue import FakeClock, LeaseQueue

LEASE = 30.0
GOOD, POISON, OTHER = Job("cust-a", "good"), Job("cust-a", "poison"), Job("cust-a", "other")


def make_queue(max_attempts: int = 3) -> tuple[FakeClock, LeaseQueue]:
    clock = FakeClock()
    return clock, LeaseQueue(clock, lease_seconds=LEASE, max_attempts=max_attempts)


class LeaseQueueTest(unittest.TestCase):
    def test_jobs_come_out_in_order(self) -> None:
        _, queue = make_queue()
        queue.enqueue(GOOD)
        queue.enqueue(OTHER)
        first, second = queue.receive(), queue.receive()
        assert first is not None and second is not None
        self.assertEqual([first.job, second.job], [GOOD, OTHER])

    def test_leased_job_is_hidden_until_the_lease_runs_out(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(GOOD)
        first = queue.receive()
        clock.advance(LEASE - 0.001)
        self.assertIsNone(queue.receive())
        clock.advance(0.001)  # expiry is "now >= deadline"
        again = queue.receive()
        assert first is not None and again is not None
        self.assertEqual((first.attempt, again.attempt), (1, 2))

    def test_stale_receipt_is_refused(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(GOOD)
        slow = queue.receive()
        clock.advance(LEASE)
        fresh = queue.receive()
        assert slow is not None and fresh is not None
        with self.assertRaises(LeaseLost):
            queue.ack(slow.receipt)
        queue.ack(fresh.receipt)  # the current holder can still finish it
        self.assertEqual(queue.pending(), 0)

    def test_settings_are_validated(self) -> None:
        for kwargs in ({"lease_seconds": 0, "max_attempts": 3}, {"lease_seconds": 1, "max_attempts": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                LeaseQueue(FakeClock(), **kwargs)


class WorkerTest(unittest.TestCase):
    def test_successful_job_is_acked_once(self) -> None:
        _, queue = make_queue()
        queue.enqueue(GOOD)
        seen: list[Job] = []
        worker = Worker(queue, lambda job, beat: seen.append(job))

        self.assertTrue(worker.run_once())
        self.assertFalse(worker.run_once())
        self.assertEqual(seen, [GOOD])
        self.assertEqual(queue.pending(), 0)

    def test_empty_queue_returns_false(self) -> None:
        _, queue = make_queue()
        self.assertFalse(Worker(queue, lambda job, beat: None).run_once())

    def test_retryable_failure_retries_up_to_the_limit_then_goes_to_the_bin(self) -> None:
        clock, queue = make_queue(max_attempts=3)
        queue.enqueue(POISON)
        calls = []

        def handler(job: Job, beat: Heartbeat) -> None:
            calls.append(job)
            raise JobFailed("backend_down", retryable=True)

        worker = Worker(queue, handler)
        for _ in range(3):
            self.assertTrue(worker.run_once())
            clock.advance(LEASE)
        self.assertFalse(worker.run_once())  # moved to the bin, nothing left

        self.assertEqual(len(calls), 3)
        (failed,) = queue.failed.values()
        self.assertEqual((failed.job, failed.attempts, failed.code), (POISON, 3, "attempts_exhausted"))

    def test_success_on_the_last_attempt_is_not_binned(self) -> None:
        clock, queue = make_queue(max_attempts=2)
        queue.enqueue(GOOD)
        attempts = []

        def handler(job: Job, beat: Heartbeat) -> None:
            attempts.append(job)
            if len(attempts) == 1:
                raise JobFailed("backend_down", retryable=True)

        worker = Worker(queue, handler)
        worker.run_once()
        clock.advance(LEASE)
        worker.run_once()
        self.assertEqual(queue.failed, {})
        self.assertEqual(queue.pending(), 0)

    def test_permanent_failure_is_buried_at_once_and_not_retried(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(POISON)
        calls = []

        def handler(job: Job, beat: Heartbeat) -> None:
            calls.append(job)
            raise JobFailed("virus_found", retryable=False)

        worker = Worker(queue, handler)
        worker.run_once()
        clock.advance(LEASE * 10)
        self.assertFalse(worker.run_once())
        self.assertEqual(len(calls), 1)
        (failed,) = queue.failed.values()
        self.assertEqual((failed.code, failed.attempts), ("virus_found", 1))

    def test_poison_job_does_not_block_the_jobs_behind_it(self) -> None:
        clock, queue = make_queue(max_attempts=3)
        queue.enqueue(POISON)
        queue.enqueue(GOOD)
        done: list[Job] = []

        def handler(job: Job, beat: Heartbeat) -> None:
            if job == POISON:
                raise JobFailed("broken_file", retryable=True)
            done.append(job)

        worker = Worker(queue, handler)
        worker.run_once()  # poison fails
        worker.run_once()  # good runs next, without waiting for the poison
        self.assertEqual(done, [GOOD])

        for _ in range(3):
            clock.advance(LEASE)
            worker.run_once()
        self.assertEqual([f.job for f in queue.failed.values()], [POISON])

    def test_long_job_renews_its_lease_and_is_not_handed_out_twice(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(GOOD)
        seen_by_other_worker = []

        def slow_handler(job: Job, beat: Heartbeat) -> None:
            for _ in range(4):  # runs for 4 x 20s, longer than one lease
                clock.advance(20)
                beat()
                other = queue.receive()
                if other is not None:
                    seen_by_other_worker.append(other)

        Worker(queue, slow_handler).run_once()
        self.assertEqual(seen_by_other_worker, [])
        self.assertEqual(queue.pending(), 0)

    def test_heartbeat_after_the_lease_is_lost_does_not_crash_the_worker(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(GOOD)

        def too_slow(job: Job, beat: Heartbeat) -> None:
            clock.advance(LEASE + 1)
            beat()  # the lease is gone: LeaseLost inside the handler

        self.assertTrue(Worker(queue, too_slow).run_once())
        again = queue.receive()  # the job is still there for the next delivery
        assert again is not None
        self.assertEqual(again.attempt, 2)

    def test_ack_after_the_lease_is_lost_leaves_the_job_for_the_new_holder(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(GOOD)

        def slow_but_no_heartbeat(job: Job, beat: Heartbeat) -> None:
            clock.advance(LEASE + 1)

        self.assertTrue(Worker(queue, slow_but_no_heartbeat).run_once())
        self.assertEqual(queue.pending(), 1)
        self.assertEqual(queue.failed, {})

    def test_bury_after_the_lease_is_lost_does_not_crash_the_worker(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(POISON)

        def slow_permanent_failure(job: Job, beat: Heartbeat) -> None:
            clock.advance(LEASE + 1)
            raise JobFailed("broken_file", retryable=False)

        self.assertTrue(Worker(queue, slow_permanent_failure).run_once())
        self.assertEqual(queue.failed, {})  # the next delivery decides
        self.assertEqual(queue.pending(), 1)

    def test_unexpected_error_propagates_and_the_job_comes_back(self) -> None:
        clock, queue = make_queue()
        queue.enqueue(GOOD)

        def buggy(job: Job, beat: Heartbeat) -> None:
            raise RuntimeError("bug")

        with self.assertRaises(RuntimeError):
            Worker(queue, buggy).run_once()
        clock.advance(LEASE)
        again = queue.receive()
        assert again is not None
        self.assertEqual((again.job, again.attempt), (GOOD, 2))


if __name__ == "__main__":
    unittest.main()
