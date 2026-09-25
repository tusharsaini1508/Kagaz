"""Upload limits.

There are deliberately no default values. The maximum size and the allowed
file types are Vrushit's decision (PRD section 6, "Upload limits"), so every
caller, including every test, must pass them in.
"""

from dataclasses import dataclass

from kaagaz.ingestion.sniff import KNOWN_TYPES


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    max_bytes: int
    allowed_types: frozenset[str]

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if not self.allowed_types:
            raise ValueError("allowed_types must not be empty")
        unknown = self.allowed_types - KNOWN_TYPES
        if unknown:
            raise ValueError(f"unknown file types: {sorted(unknown)}")
