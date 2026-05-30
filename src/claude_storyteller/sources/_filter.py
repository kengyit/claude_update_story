"""Heuristics for keeping real Claude feature announcements and dropping
bug-fix / chore / dep-bump bullets that aren't worth a story."""
from __future__ import annotations

import re

_VERSION_LIKE = re.compile(r"^v?\d+(?:\.\d+)+(?:[-+][\w.]+)?$")

_DENY_PREFIXES = (
    "fix ", "fix:", "fix(", "fixed ", "fixes ", "fixing ",
    "bug ", "bugfix",
    "chore:", "chore ", "chore(",
    "deps:", "deps ", "dep:", "deps(",
    "ci:", "ci ", "ci(",
    "test:", "tests:",
    "refactor:", "refactor ", "refactor(",
    "style:", "style ", "style(",
    "revert ", "revert:", "revert(",
    "bump ",
    "internal:",
    "perf:", "perf(",
    "docs:", "docs(",
)

_DENY_SUBSTRINGS = (
    " fixes #", " fix #", " fixed #",
    "regression",
    "internal change",
    "internal-only",
    "no user-facing",
)

_LEADING_NOISE = "*_`# -[]()"


def _normalize(title: str) -> str:
    return title.strip().lstrip(_LEADING_NOISE).strip()


def clean_title(raw: str, max_len: int = 180) -> str:
    """Trim a bullet down to a sentence-ish title without cutting mid-word."""
    cleaned = _normalize(raw)
    # If the first sentence is a reasonable title length, use it.
    period = cleaned.find(". ")
    if 30 <= period <= max_len:
        return cleaned[:period].rstrip()
    if len(cleaned) <= max_len:
        return cleaned
    # Hard cap on a word boundary.
    cut = cleaned[:max_len].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "..."


def is_feature_worthy(title: str) -> bool:
    """True when the title looks like a real new feature (not a bug fix etc.)."""
    if not title:
        return False
    cleaned = _normalize(title)
    if len(cleaned) < 15 or len(cleaned) > 250:
        return False
    if _VERSION_LIKE.match(cleaned):
        return False
    lowered = cleaned.lower()
    for prefix in _DENY_PREFIXES:
        if lowered.startswith(prefix):
            return False
    for substr in _DENY_SUBSTRINGS:
        if substr in lowered:
            return False
    # Security advisories that are themselves fixes/patches aren't features.
    if lowered.startswith("security:") and any(
        kw in lowered for kw in ("fix", "patch", "cve")
    ):
        return False
    return True
