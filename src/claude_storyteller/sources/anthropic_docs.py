from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from .base import Feature, FeatureSource

log = logging.getLogger(__name__)

DOCS_BASE = "https://docs.claude.com/"
CHANGELOG_PATHS = (
    "en/release-notes/overview",
    "en/release-notes/api",
    "en/release-notes/claude-code",
    "en/release-notes/claude-apps",
    "en/release-notes/console",
)
SITEMAP_URL = "https://docs.claude.com/sitemap.xml"


class AnthropicDocsSource(FeatureSource):
    name = "anthropic-docs"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def fetch(self) -> list[Feature]:
        features: dict[str, Feature] = {}
        with httpx.Client(
            timeout=self._timeout,
            headers={"User-Agent": "claude-storyteller/0.1 (+github.com/kengyit)"},
            follow_redirects=True,
        ) as client:
            for path in CHANGELOG_PATHS:
                url = urljoin(DOCS_BASE, path)
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("docs changelog fetch failed for %s: %s", url, exc)
                    continue
                for feat in self._parse_changelog(resp.text, url):
                    features.setdefault(feat.stable_id, feat)
        log.info("anthropic-docs source produced %d features", len(features))
        return list(features.values())

    def _parse_changelog(self, html: str, page_url: str) -> list[Feature]:
        tree = HTMLParser(html)
        out: list[Feature] = []
        for header in tree.css("h2, h3"):
            title = (header.text() or "").strip()
            if not title or len(title) < 4:
                continue
            summary_parts: list[str] = []
            node = header.next
            while node is not None and node.tag not in ("h2", "h3"):
                if node.tag in ("p", "li"):
                    text = (node.text() or "").strip()
                    if text:
                        summary_parts.append(text)
                        if sum(len(s) for s in summary_parts) > 400:
                            break
                node = node.next
            summary = " ".join(summary_parts)[:600] or title
            out.append(
                Feature.create(
                    source_kind=self.name,
                    title=title,
                    source=page_url,
                    summary=summary,
                    url=page_url,
                )
            )
        return out
