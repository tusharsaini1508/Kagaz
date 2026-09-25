"""The reader plug socket (issue #21).

One interface every reader implements, and one place that picks the reader
for a file type. Application code only ever calls ``ReaderSocket.read``.

The readers are passed in as a plain mapping from file type to reader, built
where the application is wired together. Adding a reader means writing its
module and adding one entry to that mapping; nothing else changes. There is
no self-registration or plug-in discovery on purpose.

A file type with no reader raises NoReader. In Sprint 1 that is the normal
answer for scans and photos: they are marked "needs a reader" until the scan
reader arrives in Sprint 2. The direct readers (CSV so far) are the stand-in
behind the socket until then.

PROVISIONAL until the reader contract (#3) is written.
"""

from collections.abc import Iterable, Mapping
from typing import Protocol

from kaagaz.reading.spans import CellLocation, ReadError, Span


class Reader(Protocol):
    def read(self, data: bytes) -> Iterable[Span]: ...


class NoReader(Exception):
    """No reader exists for this file type yet ("needs a reader")."""

    def __init__(self, detected_type: str) -> None:
        super().__init__(detected_type)
        self.detected_type = detected_type


class ReaderSocket:
    def __init__(self, readers: Mapping[str, Reader]) -> None:
        self._readers = dict(readers)  # copy: the set of readers is fixed once wired

    def read(self, detected_type: str, data: bytes) -> list[Span]:
        """All spans of the document, or ReadError / NoReader.

        The socket checks every span has a real cell location and non-empty
        text, so no reader can hand back a value that cannot be pointed at.
        A reader that breaks this is a bug in that reader; it fails with
        ``invalid_reader_output`` for good rather than being retried.
        """
        reader = self._readers.get(detected_type)  # O(1) dispatch
        if reader is None:
            raise NoReader(detected_type)
        spans = list(reader.read(data))
        for span in spans:
            if not _is_valid(span):
                raise ReadError("invalid_reader_output")
        return spans


def _is_valid(span: Span) -> bool:
    location = span.location
    return (
        isinstance(location, CellLocation)
        and min(location.sheet, location.row, location.column) >= 1
        and isinstance(span.text, str)
        and bool(span.text)
        and isinstance(span.raw, str)
    )
