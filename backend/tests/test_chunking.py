import unittest

from kaagaz.chunking.rows import column_letter, pieces_from_rows
from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.spans import CellLocation, Span


def span(text: str, sheet: int, row: int, column: int) -> Span:
    return Span(text, text, CellLocation(sheet, row, column))


class ColumnLetterTest(unittest.TestCase):
    def test_known_columns(self) -> None:
        # Literal table, not computed by the code under test.
        cases = {1: "A", 2: "B", 26: "Z", 27: "AA", 52: "AZ", 53: "BA", 702: "ZZ", 703: "AAA", 16384: "XFD"}
        for number, letters in cases.items():
            with self.subTest(number=number):
                self.assertEqual(column_letter(number), letters)

    def test_zero_or_negative_is_refused(self) -> None:
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                column_letter(bad)


class PiecesFromRowsTest(unittest.TestCase):
    def test_one_piece_per_row_labelled_by_column(self) -> None:
        spans = CsvReader(max_cells=100).read(b"invoice,amount\nINV-1,100\n")
        pieces = pieces_from_rows("cust-a", "doc-1", spans)
        self.assertEqual([p.text for p in pieces], ["A: invoice | B: amount", "A: INV-1 | B: 100"])
        self.assertEqual([p.row for p in pieces], [1, 2])

    def test_every_piece_traces_back_to_its_cells(self) -> None:
        spans = list(CsvReader(max_cells=100).read(b"a,,c\nd,e\n"))
        by_location = {s.location: s.text for s in spans}
        for piece in pieces_from_rows("cust-a", "doc-1", spans):
            rebuilt = " | ".join(f"{column_letter(c.column)}: {by_location[c]}" for c in piece.cells)
            self.assertEqual(rebuilt, piece.text)
            self.assertTrue(all(c.row == piece.row and c.sheet == piece.sheet for c in piece.cells))

    def test_long_cell_is_never_cut(self) -> None:
        long_text = "x" * 5000
        (piece,) = pieces_from_rows("cust-a", "doc-1", [span(long_text, 1, 1, 1)])
        self.assertEqual(piece.text, "A: " + long_text)

    def test_rows_are_grouped_and_ordered_even_if_spans_arrive_out_of_order(self) -> None:
        spans = [span("b2", 1, 2, 2), span("a1", 1, 1, 1), span("a2", 1, 2, 1), span("s2", 2, 1, 1)]
        pieces = pieces_from_rows("cust-a", "doc-1", spans)
        self.assertEqual([(p.sheet, p.row, p.text) for p in pieces], [
            (1, 1, "A: a1"),
            (1, 2, "A: a2 | B: b2"),
            (2, 1, "A: s2"),
        ])

    def test_pieces_carry_their_customer_and_document(self) -> None:
        (piece,) = pieces_from_rows("cust-a", "doc-9", [span("x", 1, 1, 1)])
        self.assertEqual((piece.customer_id, piece.document_id), ("cust-a", "doc-9"))

    def test_no_spans_gives_no_pieces(self) -> None:
        self.assertEqual(pieces_from_rows("cust-a", "doc-1", []), [])


if __name__ == "__main__":
    unittest.main()
