import unittest

from kaagaz.ingestion import sniff
from kaagaz.ingestion.sniff import detect_type


class DetectTypeTest(unittest.TestCase):
    def test_magic_numbers(self) -> None:
        cases = {
            b"%PDF-1.4\n...": sniff.PDF,
            b"\x89PNG\r\n\x1a\n....": sniff.PNG,
            b"\xff\xd8\xff\xe0....": sniff.JPEG,
            b"II*\x00....": sniff.TIFF,
            b"MM\x00*....": sniff.TIFF,
            b"PK\x03\x04....": sniff.ZIP,
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1....": sniff.OLE2,
        }
        for head, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(detect_type(head), expected)

    def test_magic_must_be_at_the_start(self) -> None:
        # "%PDF-" later in the file does not make it a PDF; it is text.
        self.assertEqual(detect_type(b"hello %PDF-1.4"), sniff.TEXT)

    def test_truncated_magic_is_not_that_type(self) -> None:
        self.assertEqual(detect_type(b"%PD"), sniff.TEXT)
        self.assertIsNone(detect_type(b"\x89PN"))

    def test_utf8_csv_is_text(self) -> None:
        self.assertEqual(detect_type(b"name,amount\nA,1\n"), sniff.TEXT)

    def test_utf8_csv_with_bom_is_text(self) -> None:
        self.assertEqual(detect_type(b"\xef\xbb\xbfname,amount\n"), sniff.TEXT)

    def test_head_cut_in_the_middle_of_a_character_is_still_text(self) -> None:
        rupee = "₹".encode()  # three bytes
        self.assertEqual(detect_type(b"amount " + rupee[:2]), sniff.TEXT)

    def test_nul_byte_means_not_text(self) -> None:
        self.assertIsNone(detect_type(b"abc\x00def"))

    def test_other_control_bytes_mean_not_text(self) -> None:
        for byte in (b"\x01", b"\x1b", b"\x7f"):
            with self.subTest(byte=byte):
                self.assertIsNone(detect_type(b"abc" + byte + b"def"))

    def test_tabs_and_both_line_endings_are_text(self) -> None:
        self.assertEqual(detect_type(b"a\tb\r\nc\td\n"), sniff.TEXT)

    def test_invalid_utf8_is_not_text(self) -> None:
        self.assertIsNone(detect_type(b"caf\xe9 au lait"))  # cp1252, not UTF-8

    def test_executable_header_is_unsupported(self) -> None:
        self.assertIsNone(detect_type(b"\x7fELF\x02\x01\x01\x00"))

    def test_empty_head_is_unsupported(self) -> None:
        self.assertIsNone(detect_type(b""))


if __name__ == "__main__":
    unittest.main()
