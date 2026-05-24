from __future__ import annotations

import logging
from dataclasses import dataclass

from github import Github

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepoSummary:
    name: str
    full_name: str
    description: str
    language: str
    topics: tuple[str, ...]
    is_private: bool
    is_archived: bool
    url: str

    def to_prompt_line(self) -> str:
        bits: list[str] = [f"- {self.name}"]
        if self.language:
            bits.append(f"[{self.language}]")
        if self.description:
            bits.append(f"— {self.description}")
        if self.topics:
            bits.append(f"(topics: {', '.join(self.topics[:5])})")
        return " ".join(bits)


class GitHubRepoLister:
    def __init__(self, token: str, username: str) -> None:
        self._gh = Github(token)
        self._username = username
        self._cache: list[RepoSummary] | None = None

    def list_repos(self) -> list[RepoSummary]:
        if self._cache is not None:
            return self._cache

        try:
            user = self._gh.get_user()
            repos = list(user.get_repos(affiliation="owner"))
        except Exception as exc:
            log.warning(
                "could not list authenticated user repos (%s); falling back to public %s",
                exc,
                self._username,
            )
            try:
                public_user = self._gh.get_user(self._username)
                repos = list(public_user.get_repos())
            except Exception as exc2:
                log.error("public repo listing also failed: %s", exc2)
                self._cache = []
                return self._cache

        summaries: list[RepoSummary] = []
        for repo in repos:
            if repo.archived:
                continue
            summaries.append(
                RepoSummary(
                    name=repo.name,
                    full_name=repo.full_name,
                    description=(repo.description or "").strip(),
                    language=(repo.language or "").strip(),
                    topics=tuple(repo.get_topics() or ()),
                    is_private=repo.private,
                    is_archived=repo.archived,
                    url=repo.html_url,
                )
            )
        log.info("loaded %d non-archived repos for %s", len(summaries), self._username)
        self._cache = summaries
        return summaries
