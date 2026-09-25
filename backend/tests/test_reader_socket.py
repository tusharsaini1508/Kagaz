import ast
import pathlib
import unittest
from collections.abc import Iterator
from typing import cast

from kaagaz.ingestion import sniff
from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.socket import NoReader, ReaderSocket
from kaagaz.reading.spans import CellLocation, ReadError, Span

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "kaagaz"


class ReaderSocketTest(unittest.TestCase):
    def test_socket_returns_what_the_direct_reader_found(self) -> None:
        data = b"a,b\nc,d\n"
        socket = ReaderSocket({sniff.TEXT: CsvReader(max_cells=100)})
        self.assertEqual(socket.read(sniff.TEXT, data), list(CsvReader(max_cells=100).read(data)))

    def test_type_without_a_reader_needs_a_reader(self) -> None:
        socket = ReaderSocket({sniff.TEXT: CsvReader(max_cells=100)})
        with self.assertRaises(NoReader) as ctx:
            socket.read(sniff.PDF, b"%PDF-1.7")
        self.assertEqual(ctx.exception.detected_type, sniff.PDF)

    def test_a_second_reader_plugs_in_without_touching_any_other_module(self) -> None:
        class OneCellReader:  # a test double standing in for a future reader
            def read(self, data: bytes) -> Iterator[Span]:
                yield Span("hello", "hello", CellLocation(1, 1, 1))

        socket = ReaderSocket({sniff.TEXT: CsvReader(max_cells=100), "fake": OneCellReader()})
        self.assertEqual([s.text for s in socket.read("fake", b"")], ["hello"])

    def test_invalid_spans_are_refused_for_good(self) -> None:
        bad_spans = {
            "no location": Span("text", "text", cast(CellLocation, None)),
            "row zero": Span("text", "text", CellLocation(1, 0, 1)),
            "empty text": Span("", "", CellLocation(1, 1, 1)),
        }
        class BadReader:
            def __init__(self, span: Span) -> None:
                self._span = span

            def read(self, data: bytes) -> list[Span]:
                return [self._span]

        for name, bad in bad_spans.items():
            with self.subTest(name), self.assertRaises(ReadError) as ctx:
                ReaderSocket({"bad": BadReader(bad)}).read("bad", b"")
            self.assertEqual(ctx.exception.code, "invalid_reader_output")

    def test_later_changes_to_the_mapping_do_not_change_the_socket(self) -> None:
        readers = {sniff.TEXT: CsvReader(max_cells=100)}
        socket = ReaderSocket(readers)
        readers.clear()
        self.assertEqual(len(socket.read(sniff.TEXT, b"a")), 1)


class NoDirectReaderCallsTest(unittest.TestCase):
    """CLAUDE.md: application code never calls a reader directly."""

    # Every module in kaagaz/reading is a reader, except the socket and the
    # span types, which everyone may use. New readers are covered automatically.
    ALLOWED = {"__init__", "socket", "spans"}

    def reader_modules(self) -> set[str]:
        return {
            f"kaagaz.reading.{path.stem}"
            for path in (PACKAGE_ROOT / "reading").glob("*.py")
            if path.stem not in self.ALLOWED
        }

    def test_the_rule_knows_the_csv_reader(self) -> None:
        self.assertIn("kaagaz.reading.csv_reader", self.reader_modules())

    def test_only_the_reading_package_imports_reader_modules(self) -> None:
        forbidden = self.reader_modules()
        offenders = []
        for path in PACKAGE_ROOT.rglob("*.py"):
            if "reading" in path.relative_to(PACKAGE_ROOT).parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    # Covers both "from kaagaz.reading.csv_reader import X"
                    # and "from kaagaz.reading import csv_reader".
                    names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
                if any(name in forbidden for name in names):
                    offenders.append(str(path.relative_to(PACKAGE_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
