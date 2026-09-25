import unittest

from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.spans import CellLocation, ReadError, Span


def read(data: bytes, max_cells: int = 1000) -> list[Span]:
    return list(CsvReader(max_cells=max_cells).read(data))


def cells(data: bytes) -> dict[tuple[int, int], str]:
    return {(s.location.row, s.location.column): s.text for s in read(data)}


class CsvReaderTest(unittest.TestCase):
    def test_every_cell_keeps_its_row_and_column(self) -> None:
        self.assertEqual(
            cells(b"invoice,amount\nINV-1,100\nINV-2,250\n"),
            {
                (1, 1): "invoice", (1, 2): "amount",
                (2, 1): "INV-1", (2, 2): "100",
                (3, 1): "INV-2", (3, 2): "250",
            },
        )

    def test_csv_is_sheet_one(self) -> None:
        (span,) = read(b"x")
        self.assertEqual(span.location, CellLocation(sheet=1, row=1, column=1))

    def test_raw_value_is_kept_next_to_the_cleaned_text(self) -> None:
        (span,) = read(b"  padded  ")
        self.assertEqual((span.text, span.raw), ("padded", "  padded  "))

    def test_byte_order_mark_is_dropped_from_the_first_cell(self) -> None:
        self.assertEqual(cells(b"\xef\xbb\xbfname\nA\n")[(1, 1)], "name")

    def test_quoted_newline_stays_in_one_cell_and_rows_count_records(self) -> None:
        got = cells(b'note,amount\n"line one\nline two",5\nnext,6\n')
        self.assertEqual(got[(2, 1)], "line one\nline two")
        self.assertEqual(got[(3, 1)], "next")  # record 3, although it is line 4

    def test_crlf_and_lf_give_the_same_cells(self) -> None:
        self.assertEqual(cells(b"a,b\r\nc,d\r\n"), cells(b"a,b\nc,d\n"))

    def test_empty_cells_are_skipped_but_columns_keep_their_numbers(self) -> None:
        self.assertEqual(cells(b"a,,c\n"), {(1, 1): "a", (1, 3): "c"})

    def test_ragged_rows_are_not_padded(self) -> None:
        self.assertEqual(cells(b"a,b,c\nd\n"), {(1, 1): "a", (1, 2): "b", (1, 3): "c", (2, 1): "d"})

    def test_semicolons_are_not_treated_as_separators(self) -> None:
        self.assertEqual(cells(b"a;b\n"), {(1, 1): "a;b"})

    def test_non_utf8_file_fails_with_a_code(self) -> None:
        with self.assertRaises(ReadError) as ctx:
            read("café".encode("cp1252"))
        self.assertEqual(ctx.exception.code, "not_utf8")

    def test_unterminated_quote_fails_with_a_code_and_no_content(self) -> None:
        with self.assertRaises(ReadError) as ctx:
            read(b'a,"never closed\n')
        self.assertEqual(str(ctx.exception), "malformed_csv")
        # Raised outside the except block: the csv module's error (which can
        # quote the cell) is not chained onto ours at all.
        self.assertIsNone(ctx.exception.__cause__)
        self.assertIsNone(ctx.exception.__context__)

    def test_non_utf8_error_does_not_carry_the_file(self) -> None:
        with self.assertRaises(ReadError) as ctx:
            read(b"made-up secret \xff")
        self.assertIsNone(ctx.exception.__context__)

    def test_control_characters_anywhere_in_the_file_are_refused(self) -> None:
        for data in (b"a,b\nc,\x00d\n", b"a" * 5000 + b"\x1b"):
            with self.subTest(size=len(data)), self.assertRaises(ReadError) as ctx:
                read(data)
            self.assertEqual(ctx.exception.code, "not_text")

    def test_a_line_of_only_commas_counts_every_field(self) -> None:
        with self.assertRaises(ReadError) as ctx:
            read(b"," * 10_000, max_cells=100)
        self.assertEqual(ctx.exception.code, "too_many_cells")

    def test_too_many_cells_fails(self) -> None:
        with self.assertRaises(ReadError) as ctx:
            read(b"a,b,c\n", max_cells=2)
        self.assertEqual(ctx.exception.code, "too_many_cells")

    def test_header_only_file_gives_only_the_header_cells(self) -> None:
        self.assertEqual(cells(b"name,amount\n"), {(1, 1): "name", (1, 2): "amount"})

    def test_empty_file_gives_no_spans(self) -> None:
        self.assertEqual(read(b""), [])

    def test_max_cells_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            CsvReader(max_cells=0)


if __name__ == "__main__":
    unittest.main()
