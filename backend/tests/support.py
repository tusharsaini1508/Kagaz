"""Small helpers shared by the tests."""

import io

from kaagaz.ingestion import sniff
from kaagaz.ingestion.policy import UploadPolicy
from kaagaz.ingestion.service import UploadService
from tests.fakes import MemoryQueue, MemoryRepository, MemoryStorage

# A tiny valid-looking PDF header plus padding. Made up; no real document.
PDF_BYTES = b"%PDF-1.7\n" + b"0" * 200
TEXT_BYTES = b"invoice,amount\nINV-1,100\n"

TEST_POLICY = UploadPolicy(
    max_bytes=1024,
    allowed_types=frozenset({sniff.PDF, sniff.PNG, sniff.TEXT, sniff.ZIP}),
)


class CountingStream(io.RawIOBase):
    """A readable stream that counts how many bytes were read from it."""

    def __init__(self, data: bytes) -> None:
        self._inner = io.BytesIO(data)
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        chunk = self._inner.read(size)
        self.bytes_read += len(chunk)
        return chunk


class EndlessStream(io.RawIOBase):
    """Returns bytes forever. Only a size limit can stop reading it."""

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        return b"A" * (size if size > 0 else 1024)


class SeqIds:
    """Deterministic document ids: doc-1, doc-2, ..."""

    def __init__(self) -> None:
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"doc-{self._n}"


def make_service(policy: UploadPolicy = TEST_POLICY):
    """An UploadService wired to fresh fakes. Returns (service, repo, storage, queue)."""
    repo, storage, queue = MemoryRepository(), MemoryStorage(), MemoryQueue()
    service = UploadService(policy, repo, storage, queue, new_id=SeqIds())
    return service, repo, storage, queue
