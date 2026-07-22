"""Evaluate volume and sentiment changes against persisted historical windows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdEvent:
    event_type: str
    text: str
    payload: dict


def evaluate_thresholds(
    query: str,
    metrics: dict,
    *,
    window_hours: int,
    minimum_mentions: int,
    volume_multiplier: float,
    sentiment_drop: float,
) -> dict[str, ThresholdEvent | None]:
    """Return active events by type; ``None`` explicitly clears an episode."""
    events: dict[str, ThresholdEvent | None] = {
        "volume_spike": None,
        "sentiment_drop": None,
    }
    current_count = metrics["current_count"]
    baseline_count = metrics["baseline_count"]
    baseline_average = metrics["baseline_average"]

    if volume_multiplier > 0 and current_count >= minimum_mentions and baseline_count > 0:
        ratio = current_count / baseline_average if baseline_average > 0 else None
        if baseline_average == 0 or ratio >= volume_multiplier:
            comparison = (
                f"{ratio:.1f}× the baseline" if ratio is not None else "up from a zero baseline"
            )
            text = (
                f"Harken alert: volume spike for “{query}”\n"
                f"{current_count} mentions in the last {window_hours}h, {comparison} "
                f"({baseline_average:.1f} average)."
            )
            events["volume_spike"] = ThresholdEvent(
                event_type="volume_spike",
                text=text,
                payload={
                    "event": "harken.volume_spike",
                    "query": query,
                    "window_hours": window_hours,
                    "current_count": current_count,
                    "baseline_average": round(baseline_average, 3),
                    "multiplier": round(ratio, 3) if ratio is not None else None,
                    "threshold": volume_multiplier,
                },
            )

    current_net = metrics["current_net_sentiment"]
    baseline_net = metrics["baseline_net_sentiment"]
    if (
        sentiment_drop > 0
        and current_count >= minimum_mentions
        and baseline_count >= minimum_mentions
        and current_net is not None
        and baseline_net is not None
    ):
        drop = baseline_net - current_net
        if drop >= sentiment_drop:
            text = (
                f"Harken alert: sentiment deterioration for “{query}”\n"
                f"Net sentiment is {current_net:+.0%} in the last {window_hours}h, "
                f"down {drop:.0%} from the {baseline_net:+.0%} baseline."
            )
            events["sentiment_drop"] = ThresholdEvent(
                event_type="sentiment_drop",
                text=text,
                payload={
                    "event": "harken.sentiment_drop",
                    "query": query,
                    "window_hours": window_hours,
                    "current_count": current_count,
                    "current_net_sentiment": round(current_net, 3),
                    "baseline_count": baseline_count,
                    "baseline_net_sentiment": round(baseline_net, 3),
                    "drop": round(drop, 3),
                    "threshold": sentiment_drop,
                },
            )
    return events
