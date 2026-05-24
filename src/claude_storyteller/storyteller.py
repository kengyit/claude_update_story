from __future__ import annotations

import logging

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from .github_repos import RepoSummary
from .sources.base import Feature

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a friendly tech storyteller. Your audience is a
curious secondary-school student (ages 13-16) who likes computers but has
never built a real software project.

You will be given:
1. One Claude feature (with a short factual description).
2. A list of the reader's own GitHub repositories (name, language, description).

You must respond with STRICTLY this Markdown structure and nothing else:

*<feature title>*

🧒 *The Story*
<A vivid, concrete metaphor or mini-narrative, max 180 words, that explains
what the feature does and why it matters. Use everyday objects (kitchens,
notebooks, group projects, school clubs). Avoid jargon; when you must use a
technical word, define it inline in plain English.>

🛠 *Where you could use this*
- <repo-name>: <2 sentence application idea, concrete and actionable>
- <repo-name>: <2 sentence application idea>

✨ *How it could level up an existing project*
- <repo-name>: <2 sentence enhancement idea — improving something the repo
  already does>

Rules:
- Pick repos from the provided list ONLY. Never invent repo names.
- Pick repos where the feature is genuinely a good fit — explain WHY in the idea.
- If fewer than 2 repos fit, use 1. Never pad.
- Keep total length under ~450 words.
- Use Telegram-flavored Markdown: *bold*, _italic_, `code`. No headings (#),
  no tables, no code fences longer than one line.
"""


def _repo_lines(repos: list[RepoSummary], limit: int = 40) -> str:
    if not repos:
        return "(no repositories available)"
    return "\n".join(r.to_prompt_line() for r in repos[:limit])


class Storyteller:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def tell(self, feature: Feature, repos: list[RepoSummary]) -> str:
        user_prompt = (
            f"Feature title: {feature.title}\n"
            f"Feature source: {feature.source}\n"
            f"Feature summary:\n{feature.summary}\n\n"
            f"Reader's repositories:\n{_repo_lines(repos)}\n"
        )

        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()

        if not text:
            raise RuntimeError("Storyteller returned empty content")
        return text
