"""One piece per spreadsheet row.

The text is split along the file's own layout (its rows), never every N
characters. A piece remembers every cell it was made from, in order, so any
part of it can be traced back to its exact cell.

No row is guessed to be a header: working out which row holds the column
names would be a guess (CLAUDE.md never-do 6). Cells are labelled by their
column letter instead, for example "A: INV-1 | B: 100".

PROVISIONAL: the piece shape waits for the database design (#1) and the
reader contract (#3). Text blocks for PDFs come with the first PDF reader.

Time is O(n + r log r) for n spans in r rows: one pass to group, then a sort
of the row keys.
"""

from collections.abc import Iterable
from dataclasses import dataclass

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
    rows: dict[tuple[int, int], list[Span]] = {}
    for span in spans:
        rows.setdefault((span.location.sheet, span.location.row), []).append(span)

    pieces = []
    for (sheet, row) in sorted(rows):
        row_spans = sorted(rows[(sheet, row)], key=lambda s: s.location.column)
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
