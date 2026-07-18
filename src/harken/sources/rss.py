"""RSS/Atom source — point it at any feed (blogs, news, Google Alerts RSS).

Filters feed entries to those mentioning the query. Configure feeds via
``feeds=[...]`` or the ``HARKEN_RSS_FEEDS`` env var (comma-separated).
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from harken.models import Mention
from harken.sources.base import Source


class RSSSource(Source):
    name = "rss"
    label = "RSS"
    needs_config = True  # needs at least one feed URL

    def __init__(self, feeds: list[str] | None = None, **options):
        super().__init__(**options)
        self.feeds = feeds or []

    def fetch(self, query: str, limit: int = 50) -> list[Mention]:
        q = query.lower()
        mentions: list[Mention] = []
        with self._client() as client:
            for feed_url in self.feeds:
                try:
                    resp = client.get(feed_url)
                    resp.raise_for_status()
                except httpx.HTTPError:
                    continue  # one bad/slow feed shouldn't cost the others their fetch
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    blob = f"{title} {summary}".lower()
                    if q not in blob:
                        continue
                    created = _entry_time(entry)
                    mentions.append(
                        Mention(
                            source=self.name,
                            query=query,
                            author=entry.get("author"),
                            title=title or None,
                            text=_strip_html(summary),
                            url=entry.get("link"),
                            created_at=created,
                        )
                    )
        return mentions[:limit]


def _entry_time(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(mktime(t), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()
