"""Deterministic input rules. No database, HTTP, or AI dependencies."""

import re
import unicodedata
from dataclasses import dataclass

NORMALIZATION_VERSION = 1
MAX_NAME_LENGTH = 100
MAX_ENTRIES = 50
MAX_TEXT_LENGTH = 10_000


@dataclass(frozen=True)
class Entry:
    original_input: str
    display_name: str
    normalized_key: str


class InvalidBatch(ValueError):
    def __init__(self, message: str, entry_index: int | None = None):
        super().__init__(message)
        self.entry_index = entry_index


def display_name(raw: str) -> str:
    return " ".join(unicodedata.normalize("NFC", raw).split())


def comparison_key(name: str) -> str:
    # NFC preserves compatibility distinctions; there is no fuzzy matching.
    return unicodedata.normalize("NFC", display_name(name).casefold())


def parse_batch(text: str, *, allow_empty: bool = False) -> list[Entry]:
    if len(text) > MAX_TEXT_LENGTH:
        raise InvalidBatch("Use at most 10,000 characters in one submission.")
    entries = []
    for raw in re.split(r",|\r\n|\r|\n", text):
        name = display_name(raw)
        if not name:
            continue
        index = len(entries) + 1
        if index > MAX_ENTRIES:
            raise InvalidBatch("Add at most 50 nonblank entries at a time.", index)
        if len(name) > MAX_NAME_LENGTH:
            raise InvalidBatch(f"Entry {index} exceeds 100 characters after cleaning.", index)
        if any(unicodedata.category(char) == "Cc" and not char.isspace() for char in raw):
            raise InvalidBatch(f"Entry {index} contains an unsupported control character.", index)
        entries.append(Entry(raw, name, comparison_key(name)))
    if not entries and not allow_empty:
        raise InvalidBatch("Enter at least one ingredient name.")
    return entries


@dataclass(frozen=True)
class PreferenceCheck:
    preferences: list[Entry]
    overlaps: list[Entry]


def check_preferences(
    entries: list[Entry], required_keys: set[str], aliases: dict[str, Entry]
) -> PreferenceCheck:
    """Resolve reviewed identities only; an overlap is a soft preference warning."""
    preferences = []
    overlaps = []
    seen = set()
    for entry in entries:
        identity = aliases.get(entry.normalized_key, entry)
        if identity.normalized_key in seen:
            continue
        seen.add(identity.normalized_key)
        resolved = Entry(entry.original_input, identity.display_name, identity.normalized_key)
        preferences.append(resolved)
        if resolved.normalized_key in required_keys:
            overlaps.append(resolved)
    return PreferenceCheck(preferences, overlaps)
