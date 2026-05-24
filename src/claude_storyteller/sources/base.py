from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


_NORMALIZE = re.compile(r"[^a-z0-9]+")


def make_stable_id(source_kind: str, canonical_title: str) -> str:
    normalized = _NORMALIZE.sub("-", canonical_title.lower()).strip("-")
    raw = f"{source_kind}::{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Feature:
    stable_id: str
    title: str
    source: str
    summary: str
    url: str = ""
    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def create(
        cls,
        *,
        source_kind: str,
        title: str,
        source: str,
        summary: str,
        url: str = "",
    ) -> "Feature":
        return cls(
            stable_id=make_stable_id(source_kind, title),
            title=title.strip(),
            source=source,
            summary=summary.strip(),
            url=url,
        )


class FeatureSource(ABC):
    name: str = "unknown"

    @abstractmethod
    def fetch(self) -> list[Feature]:
        ...
