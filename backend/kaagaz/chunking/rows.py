"""One piece per spreadsheet row.

The text is split along the file's own layout (its rows), never every N
characters. A piece remembers every cell it was made from, in order, so any
part of it can be traced back to its exact cell.

No row is guessed to be a header: working out which row holds the column
names would be a guess (CLAUDE.md never-do 6). Cells are labelled by their
column letter instead, for example "A: INV-1 | B: 100".

PROVISIONAL: the piece shape waits for the database design (#1) and the
reader contract (#3). Text blocks for PDFs come with the first PDF reader.

Time is O(n log n) in the worst case for n spans: one stable sort by
(sheet, row, column), then one pass that groups each row. Readers already
give cells in order, and Python's sort is O(n) on sorted input, so in
practice it is linear.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import groupby

from kaagaz.reading.spans import CellLocation, Span


@dataclass(frozen=True, slots=True)
class Piece:
    customer_id: str
    document_id: str
    sheet: int
    row: int
    text: str
    cells: tuple[CellLocation, ...]  # one per labelled part of ``text``, same order


def column_letter(column: int) -> str:
    """1 -> "A", 26 -> "Z", 27 -> "AA", 16384 -> "XFD". O(log column)."""
    if column < 1:
        raise ValueError("column numbers start at 1")
    letters = []
    while column:
        column, remainder = divmod(column - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def pieces_from_rows(customer_id: str, document_id: str, spans: Iterable[Span]) -> list[Piece]:
    ordered = sorted(spans, key=lambda s: s.location)  # (sheet, row, column)
    pieces = []
    for (sheet, row), group in groupby(ordered, key=lambda s: (s.location.sheet, s.location.row)):
        row_spans = list(group)
        pieces.append(
            Piece(
                customer_id=customer_id,
                document_id=document_id,
                sheet=sheet,
                row=row,
                text=" | ".join(f"{column_letter(s.location.column)}: {s.text}" for s in row_spans),
                cells=tuple(s.location for s in row_spans),
            )
        )
    return pieces
