"""Rolling metric evaluation and durable threshold episode tests."""

from datetime import datetime, timedelta, timezone

from harken.models import Mention, Sentiment
from harken.store import Store
from harken.thresholds import evaluate_thresholds

NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


def mention(hours_ago: int, sentiment: Sentiment) -> Mention:
    return Mention(
        source="test",
        query="acme",
        text=f"{sentiment.value} at {hours_ago}",
        url=f"https://example.test/{hours_ago}-{sentiment.value}",
        created_at=NOW - timedelta(hours=hours_ago),
        sentiment=sentiment,
    )


def test_alert_metrics_compare_current_window_with_complete_preceding_windows(tmp_path):
    with Store(tmp_path / "metrics.db") as store:
        store.upsert(
            [
                mention(1, Sentiment.NEGATIVE),
                mention(2, Sentiment.NEGATIVE),
                mention(3, Sentiment.NEGATIVE),
                mention(4, Sentiment.NEGATIVE),
                mention(5, Sentiment.NEGATIVE),
                mention(6, Sentiment.NEGATIVE),
                mention(25, Sentiment.POSITIVE),
                mention(30, Sentiment.POSITIVE),
                mention(49, Sentiment.POSITIVE),
                mention(60, Sentiment.POSITIVE),
            ]
        )
        metrics = store.alert_metrics("acme", now=NOW, window_hours=24, baseline_windows=2)
    assert metrics == {
        "current_count": 6,
        "baseline_count": 4,
        "baseline_average": 2.0,
        "current_net_sentiment": -1.0,
        "baseline_net_sentiment": 1.0,
    }


def test_evaluator_detects_volume_and_sentiment_crossings():
    events = evaluate_thresholds(
        "acme",
        {
            "current_count": 6,
            "baseline_count": 6,
            "baseline_average": 3.0,
            "current_net_sentiment": -1.0,
            "baseline_net_sentiment": 1.0,
        },
        window_hours=24,
        minimum_mentions=5,
        volume_multiplier=2.0,
        sentiment_drop=0.5,
    )
    assert events["volume_spike"].payload["multiplier"] == 2.0
    assert events["sentiment_drop"].payload["drop"] == 2.0
    assert "last 24h" in events["volume_spike"].text


def test_evaluator_requires_baseline_and_minimum_sample():
    events = evaluate_thresholds(
        "acme",
        {
            "current_count": 3,
            "baseline_count": 0,
            "baseline_average": 0.0,
            "current_net_sentiment": -1.0,
            "baseline_net_sentiment": None,
        },
        window_hours=24,
        minimum_mentions=5,
        volume_multiplier=2.0,
        sentiment_drop=0.5,
    )
    assert events == {"volume_spike": None, "sentiment_drop": None}


def test_threshold_episode_dedupes_retries_clears_and_obeys_cooldown(tmp_path):
    with Store(tmp_path / "episodes.db") as store:
        first = store.activate_threshold_alert(
            "acme",
            "volume_spike",
            "target",
            "first",
            {"event": "harken.volume_spike", "current_count": 10},
            cooldown_hours=24,
            now=NOW,
        )
        duplicate = store.activate_threshold_alert(
            "acme",
            "volume_spike",
            "target",
            "updated",
            {"event": "harken.volume_spike", "current_count": 11},
            cooldown_hours=24,
            now=NOW + timedelta(minutes=5),
        )
        assert duplicate == first
        pending = store.pending_threshold_alerts("acme", "target")
        assert len(pending) == 1
        assert pending[0]["text"] == "updated"
        assert pending[0]["payload"]["current_count"] == 11

        store.mark_threshold_alert_failed(first, "temporary")
        assert store.pending_threshold_alerts("acme", "target")[0]["attempts"] == 1
        store.mark_threshold_alert_delivered(first, now=NOW + timedelta(hours=1))
        assert store.threshold_alert_pending_count("acme", "target") == 0

        store.clear_threshold_alert("acme", "volume_spike", "target", now=NOW + timedelta(hours=2))
        suppressed = store.activate_threshold_alert(
            "acme",
            "volume_spike",
            "target",
            "too soon",
            {"event": "harken.volume_spike"},
            cooldown_hours=24,
            now=NOW + timedelta(hours=23),
        )
        assert suppressed is None
        rearmed = store.activate_threshold_alert(
            "acme",
            "volume_spike",
            "target",
            "rearmed",
            {"event": "harken.volume_spike"},
            cooldown_hours=24,
            now=NOW + timedelta(hours=26),
        )
        assert rearmed != first
