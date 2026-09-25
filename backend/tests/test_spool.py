import hashlib
import io
import unittest

from kaagaz.ingestion.errors import RejectCode, UploadRejected
from kaagaz.ingestion.spool import HEAD_SIZE, read_limited
from tests.support import CountingStream, EndlessStream


class ReadLimitedTest(unittest.TestCase):
    def test_sha256_of_abc_matches_published_test_vector(self) -> None:
        # FIPS 180-2 test vector for "abc".
        expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        with read_limited(io.BytesIO(b"abc"), max_bytes=10) as spooled:
            self.assertEqual(spooled.sha256, expected)
            self.assertEqual(spooled.size, 3)

    def test_fingerprint_does_not_depend_on_chunk_size(self) -> None:
        data = bytes(range(256)) * 20
        digests = set()
        for chunk_size in (1, 7, 4096, 65536):
            with read_limited(io.BytesIO(data), max_bytes=len(data), chunk_size=chunk_size) as s:
                digests.add((s.sha256, s.size))
        self.assertEqual(digests, {(hashlib.sha256(data).hexdigest(), len(data))})

    def test_copy_is_rewound_and_identical(self) -> None:
        data = b"x" * 5000
        with read_limited(io.BytesIO(data), max_bytes=10_000) as spooled:
            self.assertEqual(spooled.file.read(), data)

    def test_copy_moves_to_disk_above_memory_threshold_and_reads_back(self) -> None:
        data = b"y" * 3000
        with read_limited(io.BytesIO(data), max_bytes=10_000, spool_memory_bytes=100) as spooled:
            self.assertEqual(spooled.file.read(), data)

    def test_head_is_first_bytes_only(self) -> None:
        data = b"h" * (HEAD_SIZE + 500)
        with read_limited(io.BytesIO(data), max_bytes=len(data)) as spooled:
            self.assertEqual(spooled.head, data[:HEAD_SIZE])

    def test_head_is_collected_across_many_small_chunks(self) -> None:
        data = bytes(range(256)) * 20
        with read_limited(io.BytesIO(data), max_bytes=len(data), chunk_size=7) as spooled:
            self.assertEqual(spooled.head, data[:HEAD_SIZE])
            self.assertEqual(spooled.file.read(), data)

    def test_stream_that_returns_fewer_bytes_than_asked_is_read_fully(self) -> None:
        class Trickle(io.RawIOBase):
            def __init__(self, data: bytes) -> None:
                self._inner = io.BytesIO(data)

            def readable(self) -> bool:
                return True

            def read(self, size: int = -1) -> bytes:
                return self._inner.read(min(size, 3) if size > 0 else 3)

        data = b"0123456789" * 50
        with read_limited(Trickle(data), max_bytes=1000) as spooled:
            self.assertEqual(spooled.size, len(data))
            self.assertEqual(spooled.sha256, hashlib.sha256(data).hexdigest())

    def test_stream_returning_none_is_refused_not_treated_as_the_end(self) -> None:
        class NonBlocking(io.RawIOBase):
            def readable(self) -> bool:
                return True

            def read(self, size: int = -1) -> None:
                return None

        with self.assertRaises(ValueError):
            read_limited(NonBlocking(), max_bytes=100)

    def test_stream_returning_more_than_asked_is_refused(self) -> None:
        class Greedy(io.RawIOBase):
            def readable(self) -> bool:
                return True

            def read(self, size: int = -1) -> bytes:
                return b"x" * (size + 10)

        with self.assertRaises(ValueError):
            read_limited(Greedy(), max_bytes=100, chunk_size=8)

    def test_exactly_max_bytes_is_accepted(self) -> None:
        with read_limited(io.BytesIO(b"a" * 100), max_bytes=100) as spooled:
            self.assertEqual(spooled.size, 100)

    def test_one_byte_over_max_is_rejected(self) -> None:
        with self.assertRaises(UploadRejected) as ctx:
            read_limited(io.BytesIO(b"a" * 101), max_bytes=100)
        self.assertIs(ctx.exception.code, RejectCode.TOO_LARGE)

    def test_oversized_stream_is_read_at_most_one_byte_past_the_limit(self) -> None:
        stream = CountingStream(b"a" * 10_000)
        with self.assertRaises(UploadRejected):
            read_limited(stream, max_bytes=100, chunk_size=64)
        self.assertEqual(stream.bytes_read, 101)

    def test_endless_stream_stops_at_the_limit(self) -> None:
        with self.assertRaises(UploadRejected) as ctx:
            read_limited(EndlessStream(), max_bytes=5000)
        self.assertIs(ctx.exception.code, RejectCode.TOO_LARGE)

    def test_empty_stream_gives_size_zero(self) -> None:
        with read_limited(io.BytesIO(b""), max_bytes=10) as spooled:
            self.assertEqual(spooled.size, 0)
            self.assertEqual(spooled.head, b"")

    def test_invalid_limits_are_refused(self) -> None:
        for max_bytes, chunk_size in ((0, 1), (-1, 1), (10, 0)):
            with self.assertRaises(ValueError):
                read_limited(io.BytesIO(b"a"), max_bytes=max_bytes, chunk_size=chunk_size)


if __name__ == "__main__":
    unittest.main()
