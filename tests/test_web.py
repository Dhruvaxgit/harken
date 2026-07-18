"""Web dashboard / JSON API tests — cover the surface the review found at 0% coverage."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from harken.models import Mention, Sentiment
from harken.store import Store
from harken.web.app import create_app


def mk(text, sentiment=Sentiment.NEUTRAL, source="hackernews", query="acme", url=None):
    return Mention(
        source=source,
        query=query,
        text=text,
        url=url,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        sentiment=sentiment,
    )


def seeded_db(tmp_path):
    db_path = tmp_path / "t.db"
    store = Store(db_path)
    store.upsert([
        mk("great stuff", Sentiment.POSITIVE, url="u1"),
        mk("terrible bug", Sentiment.NEGATIVE, url="u2"),
        mk("it exists", Sentiment.NEUTRAL, url="u3"),
    ])
    store.close()
    return str(db_path)


def test_dashboard_renders_with_no_data(tmp_path):
    client = TestClient(create_app(str(tmp_path / "empty.db")))
    r = client.get("/")
    assert r.status_code == 200


def test_dashboard_renders_with_data(tmp_path):
    client = TestClient(create_app(seeded_db(tmp_path)))
    r = client.get("/")
    assert r.status_code == 200
    assert "acme" in r.text


def test_api_mentions_returns_rows(tmp_path):
    client = TestClient(create_app(seeded_db(tmp_path)))
    r = client.get("/api/mentions", params={"q": "acme"})
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_api_mentions_filters_by_sentiment(tmp_path):
    client = TestClient(create_app(seeded_db(tmp_path)))
    r = client.get("/api/mentions", params={"q": "acme", "sentiment": "positive"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["sentiment"] == "positive"


def test_api_mentions_rejects_negative_limit(tmp_path):
    # regression test: ?limit=-1 used to pass FastAPI validation (only le=1000
    # was set) and SQLite treats `LIMIT -1` as "no limit", dumping the table.
    client = TestClient(create_app(seeded_db(tmp_path)))
    r = client.get("/api/mentions", params={"q": "acme", "limit": -1})
    assert r.status_code == 422


def test_api_mentions_rejects_zero_limit(tmp_path):
    client = TestClient(create_app(seeded_db(tmp_path)))
    r = client.get("/api/mentions", params={"q": "acme", "limit": 0})
    assert r.status_code == 422


def test_api_summary(tmp_path):
    client = TestClient(create_app(seeded_db(tmp_path)))
    r = client.get("/api/summary", params={"q": "acme"})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] == 3
    assert "net" in body
