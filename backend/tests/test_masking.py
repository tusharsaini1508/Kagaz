"""Masking tests. Every number here is made up (FAKE) and follows the format
only; none belongs to a real person."""

import unittest

from kaagaz.masking.identity import IndianIdMasker

mask = IndianIdMasker().mask


class PanTest(unittest.TestCase):
    def test_pan_is_masked_keeping_the_last_four(self) -> None:
        self.assertEqual(mask("PAN ABCDE1234F"), "PAN XXXXXX234F")  # FAKE

    def test_pan_inside_a_gstin_is_masked(self) -> None:
        self.assertEqual(mask("GSTIN 27ABCDE1234F1Z5"), "GSTIN 27XXXXXX234F1Z5")  # FAKE

    def test_lowercase_pan_is_masked(self) -> None:
        self.assertEqual(mask("abcde1234f"), "XXXXXX234f")  # FAKE


class AadhaarTest(unittest.TestCase):
    def test_separator_styles_are_all_masked(self) -> None:
        cases = {
            "2345 6789 0123": "XXXX XXXX 0123",  # FAKE
            "2345-6789-0123": "XXXX-XXXX-0123",  # FAKE
            "234567890123": "XXXXXXXX0123",  # FAKE
            "2345 6789 0123": "XXXX XXXX 0123",  # FAKE
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(mask(f"id {raw} end"), f"id {expected} end")

    def test_mixed_separators_are_not_one_number(self) -> None:
        self.assertEqual(mask("2345 6789-0123"), "2345 6789-0123")

    def test_numbers_starting_with_0_or_1_are_not_aadhaar(self) -> None:
        self.assertEqual(mask("123456789012"), "123456789012")

    def test_longer_digit_runs_are_left_alone(self) -> None:
        self.assertEqual(mask("2345678901234"), "2345678901234")  # 13 digits
        self.assertEqual(mask("1234567890123456"), "1234567890123456")  # card-length


class MaskingPropertiesTest(unittest.TestCase):
    def test_other_text_is_unchanged(self) -> None:
        text = "Invoice INV-1042 dated 12/09/2026, total 45,000.00, phone 9876543210"
        self.assertEqual(mask(text), text)

    def test_length_is_kept_so_positions_stay_valid(self) -> None:
        text = "a ABCDE1234F b 2345 6789 0123 c"  # FAKE
        self.assertEqual(len(mask(text)), len(text))

    def test_masking_twice_changes_nothing(self) -> None:
        once = mask("ABCDE1234F and 2345 6789 0123")  # FAKE
        self.assertEqual(mask(once), once)

    def test_devanagari_digits_are_not_matched(self) -> None:
        text = "२३४५ ६७८९ ०१२३"
        self.assertEqual(mask(text), text)

    def test_empty_text(self) -> None:
        self.assertEqual(mask(""), "")


if __name__ == "__main__":
    unittest.main()
