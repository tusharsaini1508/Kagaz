"""Mask full Aadhaar and PAN numbers in text.

PROVISIONAL: the masking rule is Vrushit's (Sprint 1 PRD question 1). This is
the rule the council recommended, built so real documents can be read safely
until he writes his own. It implements the pipeline's IdentityMasker port.

What is masked:

* **PAN**: five letters, four digits, one letter, for example the made-up
  ``ABCDE1234F``. Matched anywhere, with no word boundaries, because a GSTIN
  (``27ABCDE1234F1Z5``) contains the full PAN inside it. Case does not matter.
* **Aadhaar**: twelve digits starting 2 to 9, written as one run or in groups
  of four split by a space, a hyphen or a non-breaking space. A digit run
  longer than twelve is left alone (it is some other number).

How: every letter and digit of a match becomes ``X`` except the last four,
and separators stay, so the text keeps its length and every position after
it still points at the right place.

Over-masking is deliberate. A 12-digit invoice number that happens to look
like an Aadhaar gets masked too; that costs a little readability. Missing a
real number would break a never-cut rule. No checksum is used to filter
matches, because a mistyped number fails the checksum but still exposes the
person.

Only ASCII digits count as digits, so Devanagari numerals are not matched.
Documents are English only at launch.

Time is O(n) in the text length: two regular expression passes.
"""

import re

_PAN = re.compile(r"[A-Za-z]{5}[0-9]{4}[A-Za-z]")
_AADHAAR = re.compile(r"(?<![0-9])[2-9][0-9]{3}([ \- ]?)[0-9]{4}\1[0-9]{4}(?![0-9])")

_KEEP = 4  # characters kept visible at the end of each match


def _hide(match: re.Match[str]) -> str:
    """Replace letters and digits with X, keeping separators and the last 4."""
    text = match.group(0)
    hidden_part, visible_part = text[:-_KEEP], text[-_KEEP:]
    return "".join("X" if ch.isascii() and ch.isalnum() else ch for ch in hidden_part) + visible_part


class IndianIdMasker:
    """Masks PAN and Aadhaar numbers. Safe to run twice: masked text has no
    matches left."""

    def mask(self, text: str) -> str:
        return _AADHAAR.sub(_hide, _PAN.sub(_hide, text))
