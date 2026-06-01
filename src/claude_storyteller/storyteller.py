from __future__ import annotations

import logging

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from .github_repos import RepoSummary
from .sources.base import Feature

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are crafting a Toastmasters speech for the reader to
deliver out loud at their club for vocal-variety, pacing, and storytelling
practice. The topic is one new Claude feature. The audience is bright but
non-technical (think a secondary-school class). The reader will literally
read your output aloud, so every sentence must FLOW as spoken English.

You will receive:
1. One Claude feature (title + factual summary).
2. A list of the reader's own GitHub repositories.

OUTPUT — STRICT FORMAT:
Line 1: *<a 4-8 word speech title>*       (this is the only bold, the
        speaker announces it as the speech title)
Line 2: (blank)
Lines 3+: the speech body in PLAIN PROSE. Paragraphs separated by a blank
line. NO bullet points. NO section headers like "Introduction". NO emoji.
NO markdown characters anywhere in the body — no asterisks, underscores,
backticks, hashtags, dashes-as-bullets, or numbered lists. Just sentences
and paragraphs the speaker can read straight off the screen.

CONTENT — CLASSIC TOASTMASTER ARC:
1. Open with a HOOK (2-4 sentences). A vivid scene, a rhetorical question,
   or a surprising statement. Grab the room in the first 15 seconds.
2. Reveal the feature using ONE sustained, everyday metaphor — kitchens,
   classrooms, sports teams, libraries, bicycles, group projects. Define
   any technical term inline in plain English the first time it appears.
3. Land it personally. Say something like "In my own work I have a project
   called <repo-name> that <does X>" and weave in ONE or TWO of the
   reader's real repositories from the provided list, showing concretely
   where this feature would matter to them. This is conversational prose,
   not a list.
4. Close strongly. Tie back to your opening image. End on a memorable
   single line the audience will remember on the drive home.

STYLE — TUNED FOR READING ALOUD:
- Mix short punchy sentences with longer rhythmical ones.
- Use the rule of three at least once (three short clauses, three nouns,
  or three parallel sentences).
- Repeat one key phrase or image at least twice for resonance — a callback.
- Address the audience directly with "you" and speak as "I".
- Conversational tone, not lecture tone. Contractions are fine.
- Prefer concrete nouns and active verbs over abstract jargon.

HARD CONSTRAINTS:
- Total length 480 to 600 words (about a four-minute speech at 140 wpm).
  Never exceed 650 words.
- Only pick repos from the provided list. Never invent a repo name.
- If only one repo fits naturally, use one. Never pad with a forced fit.
- The body must be entirely free of markdown and emoji. The reader is
  speaking, not displaying."""


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
