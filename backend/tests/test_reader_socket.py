import ast
import pathlib
import unittest
from collections.abc import Iterator
from typing import cast

from kaagaz.ingestion import sniff
from kaagaz.reading.csv_reader import CsvReader
from kaagaz.reading.socket import NoReader, ReaderSocket
from kaagaz.reading.spans import CellLocation, Span

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

    def test_span_without_a_location_is_refused(self) -> None:
        class BadReader:
            def read(self, data: bytes) -> list[Span]:
                return [Span("text", "text", cast(CellLocation, None))]

        with self.assertRaises(TypeError):
            ReaderSocket({"bad": BadReader()}).read("bad", b"")

    def test_later_changes_to_the_mapping_do_not_change_the_socket(self) -> None:
        readers = {sniff.TEXT: CsvReader(max_cells=100)}
        socket = ReaderSocket(readers)
        readers.clear()
        self.assertEqual(len(socket.read(sniff.TEXT, b"a")), 1)


class NoDirectReaderCallsTest(unittest.TestCase):
    """CLAUDE.md: application code never calls a reader directly."""

    READER_MODULES = {"kaagaz.reading.csv_reader"}

    def test_only_the_reading_package_imports_reader_modules(self) -> None:
        offenders = []
        for path in PACKAGE_ROOT.rglob("*.py"):
            if "reading" in path.relative_to(PACKAGE_ROOT).parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name in self.READER_MODULES for name in names):
                    offenders.append(str(path.relative_to(PACKAGE_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
