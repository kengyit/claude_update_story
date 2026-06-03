from __future__ import annotations

import logging

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from .github_repos import RepoSummary
from .sources.base import Feature

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are writing about one new Claude feature for a reader
who will:
(a) read the top section ALOUD at their Toastmasters club for vocal-variety
    and storytelling practice, and
(b) SKIM the bottom section as a quick checklist to decide which of their
    own projects to apply the feature to.

The two parts of your output have very different jobs and very different
styles. Treat them as two distinct deliverables.

You will receive:
1. One Claude feature (title + factual summary).
2. A list of the reader's own GitHub repositories.

OUTPUT — STRICT TWO-PART FORMAT
================================

PART 1 — TOASTMASTERS SPEECH (about 300-400 words)
Line 1: *<a 4-8 word speech title>*       (Telegram bold; the only markdown
        in Part 1; the speaker announces it as the speech title)
Line 2: (blank)
Lines 3+: speech body in PLAIN PROSE. Paragraphs separated by a blank line.
NO bullet points. NO emoji. NO markdown characters in the body (no *, _,
`, #, dashes-as-bullets, numbered lists). NO specific repository names —
keep the speech general.

The speech follows a classic Toastmaster arc:
- Hook: a vivid scene, rhetorical question, or surprising statement
  (2-4 sentences). Grab the room in 15 seconds.
- Reveal the feature using ONE sustained, everyday metaphor (kitchens,
  coaches, classrooms, libraries, bicycles). Define any technical term
  inline in plain English the first time it appears.
- Explain why it matters in plain English.
- Close on a memorable line, ideally a callback to the opening image.
- End the speech HERE. Do not introduce project applications yet.

Style: mix short punchy sentences with longer rhythmical ones, use the
rule of three at least once, repeat one key image for resonance, address
the audience with "you", conversational tone, contractions are fine.

PART 2 — APPLICATION CHECKLIST (point form, ≤120 words)
Insert a horizontal divider, then plain bullets. Use exactly this Markdown:

—

*Where you could use this:*
- <repo-name>: <one tight sentence — concrete idea, no fluff>
- <repo-name>: <one tight sentence>

*How it could level up an existing project:*
- <repo-name>: <one tight sentence enhancement>

Rules for Part 2:
- Pick repos from the provided list ONLY. Never invent a repo name.
- 1-2 bullets per section. Never pad.
- Each bullet is ONE direct sentence. No metaphors, no callbacks, no
  storytelling — just the idea, so the reader can accept or reject at a
  glance.
- Skip a section entirely if no repo fits its angle naturally.

HARD CONSTRAINTS
================
- Total length under 600 words.
- Part 1 (speech) contains ZERO markdown and ZERO emoji in the body.
- Part 2 (checklist) uses *bold headers*, `-` bullets, no emoji.
- The em-dash divider line (—) appears exactly once, between the two parts."""


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
