"""What a reader returns: pieces of text, each with where it came from.

PROVISIONAL until the reader contract (#3) is written. Only spreadsheet cell
locations exist so far; a page box for PDFs is added with the first PDF
reader, once #3 decides units and origin (PRD question 5).

Every span carries a location, because a value that cannot be pointed at
cannot be verified (CLAUDE.md never-do 5). The raw reader output is kept next
to the cleaned text (CLAUDE.md "Keep the raw reader output").
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class CellLocation:
    """A spreadsheet cell. All numbers start at 1. A CSV file is sheet 1.

    The sheet is a number, not a name: a sheet name is typed by the customer
    and could hold an identity number.
    """

    sheet: int
    row: int
    column: int


@dataclass(frozen=True, slots=True)
class Span:
    text: str  # cleaned: surrounding whitespace removed
    raw: str  # exactly what the file held
    location: CellLocation


class ReadError(Exception):
    """The document cannot be read. ``code`` is short and safe to log; the
    message never contains document content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
