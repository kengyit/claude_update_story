from __future__ import annotations

import logging
import re

from github import Github

from ._filter import clean_title, is_feature_worthy
from .base import Feature, FeatureSource

log = logging.getLogger(__name__)

REPO_FULL_NAME = "anthropics/claude-code"

_BULLET = re.compile(r"^\s*[-*]\s+(.*)$", re.MULTILINE)


class ClaudeCodeReleasesSource(FeatureSource):
    name = "claude-code-releases"

    def __init__(self, github_token: str) -> None:
        self._gh = Github(github_token)

    def fetch(self) -> list[Feature]:
        features: dict[str, Feature] = {}
        try:
            repo = self._gh.get_repo(REPO_FULL_NAME)
        except Exception as exc:
            log.warning("could not access %s releases: %s", REPO_FULL_NAME, exc)
            return []

        try:
            releases = list(repo.get_releases()[:30])
        except Exception as exc:
            log.warning("could not list releases for %s: %s", REPO_FULL_NAME, exc)
            return []

        skipped = 0
        for release in releases:
            body = release.body or ""
            base_url = release.html_url
            for match in _BULLET.finditer(body):
                bullet = match.group(1).strip()
                if len(bullet) < 6:
                    continue
                title = clean_title(bullet)
                if not is_feature_worthy(title):
                    skipped += 1
                    continue
                feat = Feature.create(
                    source_kind=self.name,
                    title=title,
                    source=base_url,
                    summary=bullet[:600],
                    url=base_url,
                )
                features.setdefault(feat.stable_id, feat)
        log.info(
            "claude-code-releases produced %d features (skipped %d non-feature bullets)",
            len(features),
            skipped,
        )
        return list(features.values())
