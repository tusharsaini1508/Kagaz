"""Read an upload once: fingerprint it, measure it and keep a copy.

One pass over the stream does three jobs at the same time:

* hashes the bytes with SHA-256, which is the file's fingerprint,
* counts the bytes and stops as soon as the file is over the limit,
* copies the bytes into a spooled temporary file, which lives in memory
  while small and moves to disk when large.

Time is O(n) in the bytes read, and never more than ``max_bytes + 1`` bytes
are read, so an oversized upload costs at most one byte past the limit.
Extra memory is O(chunk_size + spool_memory_bytes) whatever the file size.
"""

import hashlib
import tempfile
from dataclasses import dataclass
from types import TracebackType
from typing import IO, BinaryIO

from kaagaz.ingestion.errors import RejectCode, UploadRejected

# The first bytes of the file, kept for type detection. 4 KiB covers every
# magic number in sniff.py and gives the text check a fair sample.
HEAD_SIZE = 4096


@dataclass(slots=True)
class Spooled:
    """The upload after one read. Close it (or use ``with``) when done."""

    file: IO[bytes]
    size: int
    sha256: str
    head: bytes

    def close(self) -> None:
        self.file.close()

    def __enter__(self) -> "Spooled":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def read_limited(
    stream: BinaryIO,
    max_bytes: int,
    *,
    chunk_size: int = 64 * 1024,
    spool_memory_bytes: int = 1024 * 1024,
) -> Spooled:
    """Read ``stream`` to the end, or refuse it once it passes ``max_bytes``.

    Raises UploadRejected(TOO_LARGE) and discards the copy if the stream has
    more than ``max_bytes`` bytes. The returned file is rewound to the start.
    """
    if max_bytes <= 0 or chunk_size <= 0:
        raise ValueError("max_bytes and chunk_size must be positive")

    spool = tempfile.SpooledTemporaryFile(max_size=spool_memory_bytes)
    hasher = hashlib.sha256()
    head = bytearray()
    size = 0
    try:
        while True:
            # Ask for one byte more than the limit allows, never more. If that
            # byte arrives, the file is too large and we stop reading.
            want = min(chunk_size, max_bytes + 1 - size)
            chunk = stream.read(want)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise UploadRejected(RejectCode.TOO_LARGE)
            hasher.update(chunk)
            spool.write(chunk)
            if len(head) < HEAD_SIZE:
                head += chunk[: HEAD_SIZE - len(head)]
    except BaseException:
        spool.close()
        raise

    spool.seek(0)
    return Spooled(file=spool, size=size, sha256=hasher.hexdigest(), head=bytes(head))
