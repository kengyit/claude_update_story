from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from .base import Feature, FeatureSource

log = logging.getLogger(__name__)

PROBE_PROMPT = """List up to 15 features, capabilities, or tools that exist
in the Claude product family today (Claude API, Claude apps, Claude Code CLI,
Claude Agent SDK, Managed Agents, etc.). Include both well-known features
(prompt caching, tool use, vision, computer use, thinking mode, sub-agents,
hooks, slash commands, MCP) and any newer ones you are aware of.

Return ONLY a JSON array of objects with this exact shape:
[{"title": "<short feature name>", "summary": "<1-2 sentence description>",
"surface": "<api|claude-code|apps|sdk>"}]

No prose, no markdown fences, just the JSON array."""


class ClaudeProbeSource(FeatureSource):
    name = "claude-probe"

    def __init__(self, api_key: str, model: str) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def fetch(self) -> list[Feature]:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                messages=[{"role": "user", "content": PROBE_PROMPT}],
            )
        except Exception as exc:
            log.warning("claude probe failed: %s", exc)
            return []

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("claude probe JSON parse failed: %s", exc)
            return []

        features: dict[str, Feature] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            summary = (item.get("summary") or title).strip()
            feat = Feature.create(
                source_kind=self.name,
                title=title,
                source="claude-probe",
                summary=summary[:600],
            )
            features.setdefault(feat.stable_id, feat)
        log.info("claude-probe source produced %d features", len(features))
        return list(features.values())
