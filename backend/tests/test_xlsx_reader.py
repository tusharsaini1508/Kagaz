import io
import unittest
import warnings
import zipfile

from kaagaz.reading.socket import NoReader
from kaagaz.reading.spans import ReadError, Span
from kaagaz.reading.xlsx_reader import XlsxLimits, XlsxReader
from tests.xlsx_builder import make_xlsx, make_zip, sheet_xml

LIMITS = XlsxLimits(max_entries=50, max_member_bytes=200_000, max_total_bytes=1_000_000, max_cells=10_000, max_text_chars=10_000_000)


def read(data: bytes, limits: XlsxLimits = LIMITS) -> list[Span]:
    return list(XlsxReader(limits).read(data))


def cells(data: bytes) -> dict[tuple[int, int, int], str]:
    return {(s.location.sheet, s.location.row, s.location.column): s.text for s in read(data)}


def one_sheet(cells_xml: str, shared: list[str] | None = None) -> bytes:
    return make_xlsx([("Sheet1", sheet_xml(cells_xml))], shared)


def refused_with(test: unittest.TestCase, data: bytes, code: str, limits: XlsxLimits = LIMITS) -> None:
    with test.assertRaises(ReadError) as ctx:
        read(data, limits)
    test.assertEqual(ctx.exception.code, code)
    test.assertIsNone(ctx.exception.__context__)  # nothing chained


class CellValuesTest(unittest.TestCase):
    def test_shared_strings_numbers_and_positions(self) -> None:
        data = one_sheet(
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>100</v></c></row>',
            shared=["invoice", "amount", "INV-1"],
        )
        self.assertEqual(cells(data), {
            (1, 1, 1): "invoice", (1, 1, 2): "amount",
            (1, 2, 1): "INV-1", (1, 2, 2): "100",
        })

    def test_numbers_stay_exactly_as_stored(self) -> None:
        data = one_sheet('<row r="1"><c r="A1"><v>1.10</v></c><c r="B1"><v>1E-3</v></c></row>')
        self.assertEqual(cells(data), {(1, 1, 1): "1.10", (1, 1, 2): "1E-3"})

    def test_inline_string_and_rich_text_runs(self) -> None:
        data = one_sheet(
            '<row r="1"><c r="A1" t="inlineStr"><is><t>inline</t></is></c>'
            '<c r="B1" t="inlineStr"><is><r><t>Rich </t></r><r><t>text</t></r><rPh><t>skip</t></rPh></is></c></row>'
        )
        self.assertEqual(cells(data), {(1, 1, 1): "inline", (1, 1, 2): "Rich text"})

    def test_booleans_and_errors(self) -> None:
        data = one_sheet(
            '<row r="1"><c r="A1" t="b"><v>1</v></c><c r="B1" t="b"><v>0</v></c>'
            '<c r="C1" t="e"><v>#N/A</v></c></row>'
        )
        self.assertEqual(cells(data), {(1, 1, 1): "TRUE", (1, 1, 2): "FALSE", (1, 1, 3): "#N/A"})

    def test_formula_gives_its_cached_value_and_is_never_computed(self) -> None:
        data = one_sheet(
            '<row r="1"><c r="A1"><f>1+1</f><v>2</v></c><c r="B1"><f>1+1</f></c>'
            '<c r="C1" t="str"><f>"a"&amp;"b"</f><v>ab</v></c></row>'
        )
        self.assertEqual(cells(data), {(1, 1, 1): "2", (1, 1, 3): "ab"})

    def test_raw_value_is_kept_next_to_the_cleaned_text(self) -> None:
        (span,) = read(one_sheet('<row r="1"><c r="A1" t="inlineStr"><is><t xml:space="preserve">  x  </t></is></c></row>'))
        self.assertEqual((span.text, span.raw), ("x", "  x  "))


class PositionsTest(unittest.TestCase):
    def test_sparse_columns_and_letters_past_z(self) -> None:
        data = one_sheet('<row r="3"><c r="A3"><v>1</v></c><c r="C3"><v>3</v></c><c r="AA3"><v>27</v></c></row>')
        self.assertEqual(set(cells(data)), {(1, 3, 1), (1, 3, 3), (1, 3, 27)})

    def test_cells_and_rows_without_references_follow_on(self) -> None:
        data = one_sheet('<row><c><v>a</v></c><c><v>b</v></c></row><row><c><v>c</v></c></row>')
        self.assertEqual(set(cells(data)), {(1, 1, 1), (1, 1, 2), (1, 2, 1)})

    def test_sheets_come_in_workbook_order_not_part_name_order(self) -> None:
        data = make_xlsx([
            ("First", sheet_xml('<row r="1"><c r="A1"><v>1</v></c></row>')),
            ("Second", sheet_xml('<row r="1"><c r="A1"><v>2</v></c></row>')),
        ])
        self.assertEqual(cells(data), {(1, 1, 1): "1", (2, 1, 1): "2"})

    def test_absolute_relationship_targets_work(self) -> None:
        data = make_xlsx([("S", sheet_xml('<row r="1"><c r="A1"><v>1</v></c></row>'))],
                         rels_target_prefix="/xl/worksheets/")
        self.assertEqual(cells(data), {(1, 1, 1): "1"})

    def test_no_shared_strings_part_is_fine(self) -> None:
        self.assertEqual(cells(one_sheet('<row r="1"><c r="A1"><v>5</v></c></row>')), {(1, 1, 1): "5"})

    def test_empty_cells_and_empty_sheet(self) -> None:
        self.assertEqual(read(one_sheet('<row r="1"><c r="A1"/><c r="B1"><v>  </v></c></row>')), [])
        self.assertEqual(read(one_sheet("")), [])


class DamagedFileTest(unittest.TestCase):
    def test_shared_string_index_out_of_range(self) -> None:
        refused_with(self, one_sheet('<row r="1"><c r="A1" t="s"><v>5</v></c></row>', shared=["only"]), "corrupt_file")

    def test_invalid_cell_references(self) -> None:
        for ref in ("A0", "1A", "XFE1", "a1"):
            with self.subTest(ref=ref):
                refused_with(self, one_sheet(f'<row r="1"><c r="{ref}"><v>1</v></c></row>'), "corrupt_file")

    def test_missing_sheet_part(self) -> None:
        data = make_xlsx([("S", sheet_xml(""))])
        broken = make_zip({n: c for n, c in _parts(data).items() if not n.startswith("xl/worksheets/")})
        refused_with(self, broken, "corrupt_file")

    def test_truncated_file(self) -> None:
        refused_with(self, one_sheet('<row r="1"><c r="A1"><v>1</v></c></row>')[:60], "corrupt_file")

    def test_broken_xml(self) -> None:
        data = make_xlsx([("S", '<worksheet xmlns="x"><sheetData><row>')])
        refused_with(self, data, "corrupt_file")


class HostileFileTest(unittest.TestCase):
    def test_doctype_is_refused_before_any_entity_expands(self) -> None:
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
            '<worksheet xmlns="x"><sheetData><row><c><v>&lol2;</v></c></row></sheetData></worksheet>'
        )
        refused_with(self, make_xlsx([("S", bomb)]), "doctype_not_allowed")

    def test_part_bigger_than_its_limit_is_refused(self) -> None:
        big = sheet_xml('<row r="1"><c r="A1" t="inlineStr"><is><t>' + "x" * 5000 + "</t></is></c></row>")
        small = XlsxLimits(max_entries=50, max_member_bytes=2000, max_total_bytes=1_000_000, max_cells=100, max_text_chars=10_000_000)
        refused_with(self, make_xlsx([("S", big)]), "too_large_inside", small)

    def test_all_parts_together_over_the_limit_are_refused(self) -> None:
        sheets = [(f"S{i}", sheet_xml('<row r="1"><c r="A1"><v>1</v></c></row>')) for i in range(5)]
        small_total = XlsxLimits(max_entries=50, max_member_bytes=10_000, max_total_bytes=600, max_cells=100, max_text_chars=10_000_000)
        refused_with(self, make_xlsx(sheets), "too_large_inside", small_total)

    def test_too_many_parts(self) -> None:
        many = make_xlsx([("S", sheet_xml(""))], extra_parts={f"junk/{i}": b"x" for i in range(60)})
        refused_with(self, many, "too_many_parts")

    def test_duplicate_part_names(self) -> None:
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile warns about the duplicate we write on purpose
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("xl/workbook.xml", "a")
                archive.writestr("xl/workbook.xml", "b")
        refused_with(self, buffer.getvalue(), "duplicate_parts")

    def test_encrypted_part(self) -> None:
        # zipfile clears the flag when writing, so set bit 0 of the "general
        # purpose flags" in every central directory entry (signature PK\1\2,
        # flags at offset 8), which is what the reader's infolist() sees.
        data = bytearray(make_xlsx([("S", sheet_xml(""))]))
        start = 0
        while (start := data.find(b"PK\x01\x02", start)) != -1:
            data[start + 8] |= 0x1
            start += 4
        refused_with(self, bytes(data), "encrypted")

    def test_unusual_compression_is_refused(self) -> None:
        parts = _parts(make_xlsx([("S", sheet_xml(""))]))
        refused_with(self, make_zip(parts, zipfile.ZIP_LZMA), "unsupported_compression")

    def test_external_link_is_refused(self) -> None:
        data = make_xlsx([("S", sheet_xml(""))])
        parts = _parts(data)
        parts["xl/_rels/workbook.xml.rels"] = parts["xl/_rels/workbook.xml.rels"].replace(
            b'Target="worksheets/', b'TargetMode="External" Target="http://example.invalid/'
        )
        refused_with(self, make_zip(parts), "external_link")

    def test_macros_are_refused(self) -> None:
        data = make_xlsx([("S", sheet_xml(""))], extra_parts={"xl/vbaProject.bin": b"macro"})
        refused_with(self, data, "macros_not_allowed")

    def test_strict_open_xml_is_refused(self) -> None:
        data = make_xlsx([("S", sheet_xml(""))], workbook_ns="http://purl.oclc.org/ooxml/spreadsheetml/main")
        refused_with(self, data, "unsupported_spreadsheet")

    def test_too_many_cells(self) -> None:
        row = "".join(f'<c r="{letter}1"><v>1</v></c>' for letter in "ABCDEF")
        few = XlsxLimits(max_entries=50, max_member_bytes=10_000, max_total_bytes=100_000, max_cells=5, max_text_chars=10_000_000)
        refused_with(self, one_sheet(f'<row r="1">{row}</row>'), "too_many_cells", few)


class CouncilFindingsTest(unittest.TestCase):
    """Cases the council review found untested or unguarded (25 Sep)."""

    def test_one_long_shared_string_repeated_in_many_cells_is_capped(self) -> None:
        cells_xml = "".join(f'<c r="{col}1" t="s"><v>0</v></c>' for col in ("A", "B", "C", "D", "E"))
        data = one_sheet(f'<row r="1">{cells_xml}</row>', shared=["x" * 1000])
        capped = XlsxLimits(max_entries=50, max_member_bytes=200_000, max_total_bytes=1_000_000,
                            max_cells=10_000, max_text_chars=3000)
        refused_with(self, data, "too_much_text", capped)

    def test_impossible_zip_header_values_are_corrupt_not_a_crash(self) -> None:
        good = one_sheet('<row r="1"><c r="A1"><v>1</v></c></row>')
        version_patched = bytearray(good)
        version_patched[version_patched.find(b"PK\x01\x02") + 6] = 228  # version made by / needed
        offset_patched = bytearray(good)
        offset_patched[offset_patched.rfind(b"PK\x05\x06") + 19] = 0xFF  # central directory offset
        for name, data in (("version", version_patched), ("offset", offset_patched)):
            with self.subTest(name):
                refused_with(self, bytes(data), "corrupt_file")

    def test_huge_digit_strings_are_corrupt_before_int_is_called(self) -> None:
        refused_with(self, one_sheet(f'<row r="1"><c r="A1" t="s"><v>{"9" * 5000}</v></c></row>', ["x"]),
                     "corrupt_file")
        refused_with(self, one_sheet(f'<row r="{"1" * 5000}"><c><v>1</v></c></row>'), "corrupt_file")

    def test_bad_row_numbers(self) -> None:
        for row in ("0", "1048577", "abc", "١"):  # last one is an Arabic-Indic digit
            with self.subTest(row=row):
                refused_with(self, one_sheet(f'<row r="{row}"><c><v>1</v></c></row>'), "corrupt_file")

    def test_row_past_excel_limit_in_a_cell_reference(self) -> None:
        refused_with(self, one_sheet('<row r="1"><c r="A1048577"><v>1</v></c></row>'), "corrupt_file")

    def test_utf16_part_is_corrupt(self) -> None:
        data = make_xlsx([("S", sheet_xml("").encode("utf-16").decode("latin-1"))])
        refused_with(self, data, "corrupt_file")

    def test_damaged_deflate_data_is_corrupt(self) -> None:
        data = bytearray(one_sheet('<row r="1"><c r="A1" t="inlineStr"><is><t>' + "abc" * 300 + "</t></is></c></row>"))
        start = data.find(b"PK\x03\x04") + 60  # inside the first part's compressed bytes
        for i in range(start, start + 8):
            data[i] ^= 0xFF
        refused_with(self, bytes(data), "corrupt_file")

    def test_header_that_lies_about_size_is_corrupt(self) -> None:
        data = bytearray(one_sheet('<row r="1"><c r="A1" t="inlineStr"><is><t>' + "y" * 3000 + "</t></is></c></row>"))
        for signature, size_offset in ((b"PK\x01\x02", 24), (b"PK\x03\x04", 22)):
            start = 0
            while (start := data.find(signature, start)) != -1:
                data[start + size_offset:start + size_offset + 4] = (100).to_bytes(4, "little")
                start += 4
        refused_with(self, bytes(data), "corrupt_file")

    def test_patched_data_flag_is_refused(self) -> None:
        data = bytearray(one_sheet(""))
        start = 0
        while (start := data.find(b"PK\x01\x02", start)) != -1:
            data[start + 8] |= 0x20  # "compressed patched data"
            start += 4
        refused_with(self, bytes(data), "encrypted")

    def test_macros_are_found_by_case_folder_relationship_and_content_type(self) -> None:
        base = [("S", sheet_xml(""))]
        cases = {
            "upper case name": make_xlsx(base, extra_parts={"xl/VBAPROJECT.BIN": b"m"}),
            "old macro sheets": make_xlsx(base, extra_parts={"xl/macrosheets/sheet1.xml": b"<m/>"}),
            "content type": make_xlsx(base, extra_parts={"[Content_Types].xml": (
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                b'<Override PartName="/xl/workbook.xml" '
                b'ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/></Types>')}),
        }
        rels = _parts(make_xlsx(base))
        rels["xl/_rels/workbook.xml.rels"] = rels["xl/_rels/workbook.xml.rels"].replace(
            b"</Relationships>",
            b'<Relationship Id="rId9" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" '
            b'Target="macros.bin"/></Relationships>',
        )
        cases["relationship type"] = make_zip(rels)
        for name, data in cases.items():
            with self.subTest(name):
                refused_with(self, data, "macros_not_allowed")

    def test_part_names_differing_only_in_case_are_duplicates(self) -> None:
        data = make_xlsx([("S", sheet_xml(""))], extra_parts={"XL/Workbook.xml": b"<x/>"})
        refused_with(self, data, "duplicate_parts")

    def test_repeated_or_backwards_cells_are_corrupt(self) -> None:
        cases = {
            "same cell twice": '<row r="1"><c r="A1"><v>1</v></c><c r="A1"><v>2</v></c></row>',
            "rows backwards": '<row r="5"><c r="A5"><v>1</v></c></row><row r="2"><c r="A2"><v>2</v></c></row>',
            "cell outside its row": '<row r="1"><c r="A7"><v>1</v></c></row>',
            "columns backwards": '<row r="1"><c r="C1"><v>1</v></c><c r="A1"><v>2</v></c></row>',
        }
        for name, xml in cases.items():
            with self.subTest(name):
                refused_with(self, one_sheet(xml), "corrupt_file")

    def test_workbook_without_a_sheet_list_is_corrupt_not_empty(self) -> None:
        parts = _parts(make_xlsx([("S", sheet_xml(""))]))
        parts["xl/workbook.xml"] = (
            b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        )
        refused_with(self, make_zip(parts), "corrupt_file")

    def test_sheet_without_a_relationship_id_is_corrupt(self) -> None:
        parts = _parts(make_xlsx([("S", sheet_xml(""))]))
        parts["xl/workbook.xml"] = parts["xl/workbook.xml"].replace(b' r:id="rId1"', b"")
        refused_with(self, make_zip(parts), "corrupt_file")

    def test_large_word_file_is_still_needs_a_reader(self) -> None:
        docx = make_zip({f"word/part{i}.xml": b"<x/>" for i in range(60)})
        with self.assertRaises(NoReader):
            read(docx)


class NotASpreadsheetTest(unittest.TestCase):
    def test_word_document_needs_a_reader_and_is_not_broken(self) -> None:
        docx = make_zip({"word/document.xml": b"<document/>", "[Content_Types].xml": b"<Types/>"})
        with self.assertRaises(NoReader):
            read(docx)

    def test_limits_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            XlsxLimits(max_entries=0, max_member_bytes=1, max_total_bytes=1, max_cells=1, max_text_chars=10_000_000)


def _parts(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


if __name__ == "__main__":
    unittest.main()
