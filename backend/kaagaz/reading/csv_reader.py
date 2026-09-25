"""Read a CSV file directly, without any AI (issue #19).

Every non-empty cell becomes one Span with its row and column, so the file's
row and column structure is kept.

* The file must be UTF-8 (a byte order mark is allowed). Any other encoding
  fails with ``not_utf8``: guessing an encoding would silently change text.
* Only commas separate fields. The delimiter is never guessed.
* A quoted field may span several lines; its row is the record number, not
  the line number, so positions stay right.
* Errors are re-raised as a ReadError code with ``from None``, so the
  original message (which can quote cell content) is dropped.

Time is O(n) in the file size. Memory is O(n) because the whole file is
decoded at once; it is bounded by the upload size limit.
"""

import csv
import io
from collections.abc import Iterator

from kaagaz.reading.spans import CellLocation, ReadError, Span


class CsvReader:
    def __init__(self, *, max_cells: int) -> None:
        # No default: limits are Vrushit's decision (PRD section 6).
        if max_cells < 1:
            raise ValueError("max_cells must be at least 1")
        self._max_cells = max_cells

    def read(self, data: bytes) -> Iterator[Span]:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ReadError("not_utf8") from None

        # newline="" lets the csv module see line endings inside quotes.
        records = csv.reader(io.StringIO(text, newline=""), strict=True)
        cells = 0
        try:
            for row_number, record in enumerate(records, start=1):
                for column_number, raw in enumerate(record, start=1):
                    cleaned = raw.strip()
                    if not cleaned:
                        continue  # nothing to point at in an empty cell
                    cells += 1
                    if cells > self._max_cells:
                        raise ReadError("too_many_cells")
                    yield Span(
                        text=cleaned,
                        raw=raw,
                        location=CellLocation(sheet=1, row=row_number, column=column_number),
                    )
        except csv.Error:
            raise ReadError("malformed_csv") from None
