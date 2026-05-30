from __future__ import annotations

import json
import logging

from anthropic import Anthropic

from .base import Feature, FeatureSource

log = logging.getLogger(__name__)


PROBE_PROMPT_TEMPLATE = """You are documenting the most REVOLUTIONARY or
paradigm-shifting features released across the Claude product family
(Claude API, Claude Code CLI, Claude apps, Claude Agent SDK) on or after
{cutoff_date}.

REQUIREMENTS:
1. Return a JSON array of 8-15 entries in CHRONOLOGICAL order (oldest first).
2. The VERY FIRST entry MUST be the subagents / multi-agent orchestration
   feature in Claude Code, which introduced .claude/agents/ YAML
   configuration and let users delegate work to specialized sub-agents.
3. Only include genuinely revolutionary features: new modalities, new
   capabilities, paradigm shifts, novel APIs, or major model launches.
   Skip bug fixes, minor improvements, dependency bumps, and patch releases.

Each entry MUST be a JSON object with exactly these fields:
{{
  "title":        "<short flagship name, e.g. 'Subagents in Claude Code'>",
  "summary":      "<2-3 sentences: what it is and why it's significant>",
  "release_date": "<YYYY-MM-DD; if exact day unknown use the 1st of that month>",
  "surface":      "<api | claude-code | apps | sdk>"
}}

Return ONLY the JSON array. No prose, no markdown fences, no commentary."""


class ClaudeProbeSource(FeatureSource):
    name = "claude-probe"

    def __init__(self, api_key: str, model: str, cutoff_date: str) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._cutoff_date = cutoff_date

    def fetch(self) -> list[Feature]:
        prompt = PROBE_PROMPT_TEMPLATE.format(cutoff_date=self._cutoff_date)
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            log.warning("claude probe failed: %s", exc)
            return []

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        text = (
            text.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("claude probe JSON parse failed: %s", exc)
            return []

        features: list[Feature] = []
        seen_ids: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            summary_bits = []
            if item.get("release_date"):
                summary_bits.append(f"Released {item['release_date']}.")
            if item.get("surface"):
                summary_bits.append(f"Surface: {item['surface']}.")
            if item.get("summary"):
                summary_bits.append(item["summary"].strip())
            summary = " ".join(summary_bits)[:800] or title

            feat = Feature.create(
                source_kind=self.name,
                title=title,
                source="claude-probe",
                summary=summary,
            )
            if feat.stable_id in seen_ids:
                continue
            seen_ids.add(feat.stable_id)
            features.append(feat)

        log.info(
            "claude-probe produced %d curated flagship feature(s) (cutoff=%s)",
            len(features),
            self._cutoff_date,
        )
        return features
