from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .sources.base import Feature

log = logging.getLogger(__name__)


class ExplainedStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        self._loaded = False

    def load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text("utf-8"))
            except json.JSONDecodeError:
                log.warning("explained.json was corrupt; starting fresh")
                self._data = {}
        else:
            self._data = {}
        self._loaded = True
        log.info("loaded %d previously explained features", len(self._data))

    def filter_new(self, features: list[Feature]) -> list[Feature]:
        if not self._loaded:
            self.load()
        return [f for f in features if f.stable_id not in self._data]

    def mark_explained(
        self,
        feature: Feature,
        *,
        telegram_message_id: int | None = None,
    ) -> None:
        self._data[feature.stable_id] = {
            "title": feature.title,
            "source": feature.source,
            "url": feature.url,
            "explained_at": datetime.now(timezone.utc).isoformat(),
            "telegram_message_id": telegram_message_id,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = dict(sorted(self._data.items()))
        self.path.write_text(
            json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, stable_id: str) -> bool:
        return stable_id in self._data
