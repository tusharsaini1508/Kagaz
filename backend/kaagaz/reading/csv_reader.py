"""Read a CSV file directly, without any AI (issue #19).

Every non-empty cell becomes one Span with its row and column, so the file's
row and column structure is kept.

* The file must be UTF-8 (a byte order mark is allowed). Any other encoding
  fails with ``not_utf8``: guessing an encoding would silently change text.
* Control characters other than tab, line feed, form feed and carriage return
  fail with ``not_text``. The type check only saw the first 4 KiB, so this is
  checked again over the whole file.
* Only commas separate fields. The delimiter is never guessed.
* A quoted field may span several lines; its row is the record number, not
  the line number, so positions stay right.
* Every field counts toward ``max_cells``, empty ones too, so a line of a
  million commas is refused instead of filling memory.
* Errors are raised outside the ``except`` block, so the original error
  (which can hold the file's bytes or quote a cell) is never chained on.

Time is O(n) in the file size. Memory is O(n) because the whole file is
decoded at once; it is bounded by the upload size limit.
"""

import csv
import io
import re
from collections.abc import Iterator

from kaagaz.reading.spans import CellLocation, ReadError, Span

# Same rule as the upload type check (ingestion/sniff.py).
_FORBIDDEN_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


class CsvReader:
    def __init__(self, *, max_cells: int) -> None:
        # No default: limits are Vrushit's decision (PRD section 6).
        if max_cells < 1:
            raise ValueError("max_cells must be at least 1")
        self._max_cells = max_cells

    def read(self, data: bytes) -> Iterator[Span]:
        text = _decode_utf8(data)
        if text is None:
            raise ReadError("not_utf8")
        if _FORBIDDEN_CONTROL.search(text):
            raise ReadError("not_text")

        # newline="" lets the csv module see line endings inside quotes.
        records = csv.reader(io.StringIO(text, newline=""), strict=True)
        fields = 0
        malformed = False
        try:
            for row_number, record in enumerate(records, start=1):
                fields += len(record)
                if fields > self._max_cells:
                    break
                for column_number, raw in enumerate(record, start=1):
                    cleaned = raw.strip()
                    if cleaned:  # nothing to point at in an empty cell
                        yield Span(
                            text=cleaned,
                            raw=raw,
                            location=CellLocation(sheet=1, row=row_number, column=column_number),
                        )
        except csv.Error:
            malformed = True
        if malformed:
            raise ReadError("malformed_csv")
        if fields > self._max_cells:
            raise ReadError("too_many_cells")


def _decode_utf8(data: bytes) -> str | None:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
