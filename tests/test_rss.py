"""RSS source tests — HTTP is mocked, so these run offline and deterministically."""

import httpx
import respx

from harken.sources.rss import RSSSource

_FEED_A = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Acme one</title><description>people are talking</description>
<link>https://example.com/a1</link><author>alice</author>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
<item><title>Acme two</title><description>more chatter</description>
<link>https://example.com/a2</link><author>alice</author>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
</channel></rss>"""

_FEED_B = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Acme three</title><description>from another feed entirely</description>
<link>https://example.com/b1</link><author>bob</author>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
</channel></rss>"""


@respx.mock
def test_fetches_every_configured_feed_even_once_limit_is_hit():
    feed_a = respx.get("https://feeds.example/a.xml").mock(
        return_value=httpx.Response(200, content=_FEED_A)
    )
    feed_b = respx.get("https://feeds.example/b.xml").mock(
        return_value=httpx.Response(200, content=_FEED_B)
    )
    src = RSSSource(feeds=["https://feeds.example/a.xml", "https://feeds.example/b.xml"])
    out = src.fetch("acme", limit=1)

    assert feed_a.called
    assert feed_b.called  # regression: used to never be requested once feed A hit `limit`
    assert len(out) == 1  # the limit is still respected in the returned result


@respx.mock
def test_isolates_a_single_bad_feed():
    respx.get("https://feeds.example/broken.xml").mock(return_value=httpx.Response(500))
    respx.get("https://feeds.example/b.xml").mock(return_value=httpx.Response(200, content=_FEED_B))
    src = RSSSource(feeds=["https://feeds.example/broken.xml", "https://feeds.example/b.xml"])
    out = src.fetch("acme", limit=50)

    assert len(out) == 1
    assert out[0].author == "bob"


@respx.mock
def test_filters_entries_by_query():
    respx.get("https://feeds.example/a.xml").mock(return_value=httpx.Response(200, content=_FEED_A))
    src = RSSSource(feeds=["https://feeds.example/a.xml"])
    out = src.fetch("nonexistent-brand", limit=50)
    assert out == []


def test_uses_the_shared_timeout_client():
    # regression: fetch() used to call feedparser.parse(url) directly, which
    # bypasses Source._client()'s 15s timeout entirely (unbounded hang risk).
    src = RSSSource(feeds=["https://feeds.example/a.xml"])
    client = src._client()
    try:
        assert client.timeout == httpx.Timeout(15.0)
    finally:
        client.close()
