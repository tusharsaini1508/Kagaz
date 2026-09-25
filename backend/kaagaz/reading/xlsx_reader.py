"""Read an Excel .xlsx file directly, without any AI (issue #19).

An .xlsx file is a zip of XML parts. This reader uses only the standard
library, and treats the file as hostile: it runs after the virus scan, but a
clean file can still be built to exhaust memory or trick an XML parser.

PROVISIONAL: a standard-library reader, pending Vrushit's Excel library
decision (PRD section 6). Refusing macros, external links and encrypted
parts, and every limit below, are his security settings.

Guards, all limits passed in (no defaults):

* At most ``max_entries`` parts; no two part names that differ only in case.
* Parts must be stored or deflated, and not encrypted or "patched". Sizes are
  counted from the bytes actually read, never trusted from the zip header.
* Each part at most ``max_member_bytes``; all parts together at most
  ``max_total_bytes``. Parsing one part needs about 25 times its size in
  memory, so ``max_member_bytes`` sets the peak memory of a read.
* XML must be UTF-8 and must not contain a DOCTYPE, so entity tricks
  ("billion laughs", external entities) cannot start.
* External relationships in the workbook are refused (nothing is ever
  fetched). Macros are refused, found by name, relationship type and content
  type, ignoring case.
* At most ``max_cells`` non-empty cells, and at most ``max_text_chars``
  characters of text in total, so one long shared string repeated in many
  cells cannot multiply into gigabytes.
* Cells must come in order (each after the one before), as Excel writes
  them, so no two values can claim the same cell.

What comes out: one Span per non-empty cell, with sheet (in workbook order,
starting at 1), row and column. Values are the cell's stored value:

* text (shared or inline, rich text runs joined), TRUE / FALSE, error codes
  such as ``#N/A``, and numbers exactly as stored (``1.10`` stays ``1.10``);
* formulas give their cached result; a formula with no cached result gives
  nothing (it is never computed);
* date cells written as dates come out as ISO text (``2024-03-01T00:00:00``);
* PROVISIONAL: dates stored as numbers stay serial numbers (``45000``), and
  percentages stay fractions. Formatting them needs the style rules, which
  are part of the reader contract (#3).
* merged cells give their value once, at the top-left cell; hidden sheets
  are read like any other.

A zip that is not a spreadsheet (for example .docx) raises NoReader: it needs
file preparation (#17) or another reader, and is not a broken file. Macro
checks for those files belong to their own reader.

Errors are raised as short codes outside any ``except`` block, so no parser
error (which can quote content) is chained on.

Time is O(n) in the size of the parts read. Memory: see ``max_member_bytes``
above, plus the spans (bounded by ``max_cells`` and ``max_text_chars``).
"""

import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass

from kaagaz.ingestion import sniff
from kaagaz.reading.socket import NoReader
from kaagaz.reading.spans import CellLocation, ReadError, Span

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_CONTENT_TYPES_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"

_WORKBOOK = "xl/workbook.xml"
_WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
_SHARED_STRINGS = "xl/sharedStrings.xml"
_CONTENT_TYPES = "[Content_Types].xml"

# Excel's own grid limits.
_MAX_ROW = 1_048_576
_MAX_COLUMN = 16_384
_CELL_REF = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_DOCTYPE = re.compile(r"<!DOCTYPE", re.IGNORECASE)
_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
# Zip flag bits: 0x01 encrypted, 0x20 "compressed patched data", 0x40 strong
# encryption. None of them appear in a normal spreadsheet.
_REFUSED_FLAGS = 0x01 | 0x20 | 0x40

# Signs of macros, compared in lower case.
_MACRO_NAMES = ("vbaproject.bin",)
_MACRO_FOLDERS = ("xl/macrosheets/", "xl/dialogsheets/")
_MACRO_CONTENT_WORDS = ("vbaproject", "macroenabled", "macrosheet")

# Errors the zip and XML libraries raise for a damaged file. zipfile also
# raises NotImplementedError and ValueError for impossible header values
# (a version number or offset no real file has).
_DAMAGED = (
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    ET.ParseError,
    NotImplementedError,
    ValueError,  # includes UnicodeDecodeError
)


@dataclass(frozen=True, slots=True)
class XlsxLimits:
    max_entries: int
    max_member_bytes: int
    max_total_bytes: int
    max_cells: int
    max_text_chars: int

    def __post_init__(self) -> None:
        values = (self.max_entries, self.max_member_bytes, self.max_total_bytes,
                  self.max_cells, self.max_text_chars)
        if min(values) < 1:
            raise ValueError("every limit must be at least 1")


class _Refused(Exception):
    """Internal: stop reading with this code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class XlsxReader:
    def __init__(self, limits: XlsxLimits) -> None:
        self._limits = limits

    def read(self, data: bytes) -> Iterator[Span]:
        code = None
        spans: list[Span] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                spans = _Workbook(archive, self._limits).spans()
        except _Refused as refused:
            code = refused.code
        except _DAMAGED:
            code = "corrupt_file"
        if code is not None:
            raise ReadError(code)  # outside the except blocks: nothing chained
        return iter(spans)


class _Workbook:
    """One pass over one workbook. Not reused."""

    def __init__(self, archive: zipfile.ZipFile, limits: XlsxLimits) -> None:
        self._limits = limits
        self._zip = archive
        infos = archive.infolist()
        self._parts = {info.filename: info for info in infos}
        if _WORKBOOK not in self._parts:
            raise NoReader(sniff.ZIP)  # a zip, but not a spreadsheet
        if len(infos) > limits.max_entries:
            raise _Refused("too_many_parts")
        if len({info.filename.lower() for info in infos}) != len(infos):
            raise _Refused("duplicate_parts")
        self._bytes_read = 0
        self._cells = 0
        self._text_chars = 0
        self._last_cell = (0, 0, 0)  # (sheet, row, column) of the previous cell

    def spans(self) -> list[Span]:
        self._refuse_macros()
        workbook = self._xml(_WORKBOOK)
        if workbook.tag != f"{_MAIN}workbook":
            raise _Refused("unsupported_spreadsheet")  # e.g. Strict Open XML
        sheets = workbook.find(f"{_MAIN}sheets")
        if sheets is None:
            raise _Refused("corrupt_file")
        targets = self._relationship_targets()
        shared = self._shared_strings()

        spans: list[Span] = []
        for sheet_number, sheet in enumerate(sheets.findall(f"{_MAIN}sheet"), start=1):
            part = targets.get(sheet.get(f"{_DOC_REL}id"))
            if part is None:
                raise _Refused("corrupt_file")
            self._read_sheet(sheet_number, self._xml(part), shared, spans)
        return spans

    # -- parts ------------------------------------------------------------

    def _refuse_macros(self) -> None:
        for name in self._parts:
            lower = name.lower()
            if lower.endswith(_MACRO_NAMES) or lower.startswith(_MACRO_FOLDERS):
                raise _Refused("macros_not_allowed")
        if _CONTENT_TYPES in self._parts:
            for entry in self._xml(_CONTENT_TYPES):
                content_type = entry.get("ContentType", "").lower()
                if any(word in content_type for word in _MACRO_CONTENT_WORDS):
                    raise _Refused("macros_not_allowed")

    def _member(self, name: str) -> bytes:
        info = self._parts.get(name)
        if info is None or info.header_offset < 0:
            raise _Refused("corrupt_file")
        if info.flag_bits & _REFUSED_FLAGS:
            raise _Refused("encrypted")
        if info.compress_type not in _ALLOWED_COMPRESSION:
            raise _Refused("unsupported_compression")
        limit = self._limits.max_member_bytes
        if info.file_size > limit:
            raise _Refused("too_large_inside")
        content = bytearray()
        with self._zip.open(info) as part:
            while chunk := part.read(64 * 1024):
                content += chunk
                # Backstop: zipfile stops at the declared size and fails the
                # CRC check, but the limit must hold whatever zipfile does.
                if len(content) > limit:
                    raise _Refused("too_large_inside")
        self._bytes_read += len(content)
        if self._bytes_read > self._limits.max_total_bytes:
            raise _Refused("too_large_inside")
        return bytes(content)

    def _xml(self, name: str) -> ET.Element:
        text = self._member(name).decode("utf-8")
        if _DOCTYPE.search(text):
            raise _Refused("doctype_not_allowed")
        return ET.fromstring(text)

    def _relationship_targets(self) -> dict[str, str]:
        """Relationship id -> part name inside this zip."""
        targets = {}
        for rel in self._xml(_WORKBOOK_RELS).iter(f"{_PKG_REL}Relationship"):
            if (rel.get("TargetMode") or "").lower() == "external":
                raise _Refused("external_link")
            if (rel.get("Type") or "").lower().endswith("/vbaproject"):
                raise _Refused("macros_not_allowed")
            rel_id, target = rel.get("Id"), rel.get("Target")
            if not rel_id or not target:
                continue
            if target.startswith("/"):
                targets[rel_id] = target.lstrip("/")
            else:
                targets[rel_id] = posixpath.normpath(posixpath.join("xl", target))
        return targets

    def _shared_strings(self) -> list[str]:
        if _SHARED_STRINGS not in self._parts:
            return []
        return [_rich_text(item) for item in self._xml(_SHARED_STRINGS).findall(f"{_MAIN}si")]

    # -- cells ------------------------------------------------------------

    def _read_sheet(self, sheet_number: int, root: ET.Element, shared: list[str], spans: list[Span]) -> None:
        data = root.find(f"{_MAIN}sheetData")
        if data is None:
            return
        row_number = 0
        for row in data.findall(f"{_MAIN}row"):
            row_number = _row_number(row.get("r"), default=row_number + 1)
            column = 0
            for cell in row.findall(f"{_MAIN}c"):
                ref = cell.get("r")
                if ref is None:
                    column += 1  # no reference: the next column
                else:
                    column, ref_row = _parse_ref(ref)
                    if ref_row != row_number:
                        raise _Refused("corrupt_file")  # a cell outside its row
                self._check_order(sheet_number, row_number, column)
                value = _cell_value(cell, shared)
                if value is None or not value.strip():
                    continue
                self._count(value)
                spans.append(Span(value.strip(), value, CellLocation(sheet_number, row_number, column)))

    def _check_order(self, sheet: int, row: int, column: int) -> None:
        position = (sheet, row, column)
        if position <= self._last_cell:
            raise _Refused("corrupt_file")  # repeated or backwards cell
        self._last_cell = position

    def _count(self, value: str) -> None:
        self._cells += 1
        self._text_chars += len(value)
        if self._cells > self._limits.max_cells:
            raise _Refused("too_many_cells")
        if self._text_chars > self._limits.max_text_chars:
            raise _Refused("too_much_text")


def _cell_value(cell: ET.Element, shared: list[str]) -> str | None:
    kind = cell.get("t", "n")
    if kind == "inlineStr":
        inline = cell.find(f"{_MAIN}is")
        return None if inline is None else _rich_text(inline)
    stored = cell.find(f"{_MAIN}v")
    value = None if stored is None else stored.text
    if value is None:
        return None  # includes a formula with no cached result: never computed
    if kind == "s":
        return shared[_shared_index(value, len(shared))]
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value  # "n", "str", "e", "d": exactly as stored


def _rich_text(item: ET.Element) -> str:
    """Text of a shared or inline string: one <t>, or runs <r><t>. Phonetic
    hints (<rPh>) are not part of the text."""
    parts = []
    for child in item:
        if child.tag == f"{_MAIN}t":
            parts.append(child.text or "")
        elif child.tag == f"{_MAIN}r":
            run_text = child.find(f"{_MAIN}t")
            parts.append("" if run_text is None or run_text.text is None else run_text.text)
    return "".join(parts)


def _parse_ref(ref: str) -> tuple[int, int]:
    """"B7" -> (column 2, row 7). O(len(ref))."""
    match = _CELL_REF.fullmatch(ref)
    if match is None:
        raise _Refused("corrupt_file")
    column = 0
    for letter in match.group(1):
        column = column * 26 + (ord(letter) - ord("A") + 1)
    row = int(match.group(2))
    if column > _MAX_COLUMN or row > _MAX_ROW:
        raise _Refused("corrupt_file")
    return column, row


def _whole_number(text: str) -> int:
    """At most 7 ASCII digits (the largest row number); anything else means a
    damaged file. The length check comes first, so a huge digit string never
    reaches int()."""
    if len(text) > 7 or not text.isascii() or not text.isdigit():
        raise _Refused("corrupt_file")
    return int(text)


def _row_number(text: str | None, *, default: int) -> int:
    """A row's number from its "r" attribute, or the next row if it has none."""
    row = default if text is None else _whole_number(text)
    if not 1 <= row <= _MAX_ROW:
        raise _Refused("corrupt_file")
    return row


def _shared_index(text: str, count: int) -> int:
    """A position in the shared strings list, which must exist."""
    index = _whole_number(text)
    if index >= count:
        raise _Refused("corrupt_file")
    return index
