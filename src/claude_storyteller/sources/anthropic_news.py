from __future__ import annotations

import logging

import feedparser

from .base import Feature, FeatureSource

log = logging.getLogger(__name__)

NEWS_FEEDS = (
    "https://www.anthropic.com/news/rss.xml",
    "https://www.anthropic.com/rss.xml",
)


class AnthropicNewsSource(FeatureSource):
    name = "anthropic-news"

    def fetch(self) -> list[Feature]:
        features: dict[str, Feature] = {}
        for feed_url in NEWS_FEEDS:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as exc:
                log.warning("news feed fetch failed for %s: %s", feed_url, exc)
                continue
            for entry in getattr(parsed, "entries", []) or []:
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                summary = (
                    entry.get("summary") or entry.get("description") or title
                ).strip()
                link = (entry.get("link") or feed_url).strip()
                feat = Feature.create(
                    source_kind=self.name,
                    title=title,
                    source=link,
                    summary=summary[:600],
                    url=link,
                )
                features.setdefault(feat.stable_id, feat)
        log.info("anthropic-news source produced %d features", len(features))
        return list(features.values())
