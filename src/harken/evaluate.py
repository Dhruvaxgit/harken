"""Reproducible evaluation for Harken's local sentiment analyzer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from harken.analyze.sentiment import LexiconSentiment
from harken.models import Sentiment

_LABELS = tuple(sentiment.value for sentiment in Sentiment)


@dataclass(frozen=True)
class EvaluationDataset:
    name: str
    version: int
    description: str
    license: str
    examples: tuple[dict, ...]


def load_sentiment_dataset(path: str | Path | None = None) -> EvaluationDataset:
    """Load and strictly validate the bundled or operator-supplied JSON dataset."""
    if path is None:
        raw = files("harken").joinpath("evaluation/sentiment_v1.json").read_text("utf-8")
        origin = "bundled dataset"
    else:
        source = Path(path).expanduser()
        raw = source.read_text(encoding="utf-8")
        origin = str(source)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {origin}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{origin} must contain a JSON object")
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError(f"{origin} must contain a non-empty examples list")

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for index, example in enumerate(examples, start=1):
        if not isinstance(example, dict):
            raise ValueError(f"example {index} must be an object")
        example_id = str(example.get("id", "")).strip()
        text = example.get("text")
        label = example.get("label")
        category = str(example.get("category", "uncategorized")).strip() or "uncategorized"
        if not example_id or example_id in seen_ids:
            raise ValueError(f"example {index} has a missing or duplicate id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"example {example_id} must have non-empty text")
        if label not in _LABELS:
            raise ValueError(f"example {example_id} label must be one of {', '.join(_LABELS)}")
        seen_ids.add(example_id)
        normalized.append(
            {"id": example_id, "text": text.strip(), "label": label, "category": category}
        )

    name = str(payload.get("name", "sentiment-evaluation")).strip()
    description = str(payload.get("description", "")).strip()
    license_name = str(payload.get("license", "unspecified")).strip()
    version = payload.get("version", 1)
    if not name or not isinstance(version, int) or version < 1:
        raise ValueError(f"{origin} must have a name and positive integer version")
    return EvaluationDataset(
        name=name,
        version=version,
        description=description,
        license=license_name,
        examples=tuple(normalized),
    )


def evaluate_sentiment(
    dataset: EvaluationDataset, analyzer: LexiconSentiment | None = None
) -> dict:
    """Return accuracy, per-class PR/F1, confusion matrix, and individual errors."""
    scorer = analyzer or LexiconSentiment()
    confusion = {expected: {predicted: 0 for predicted in _LABELS} for expected in _LABELS}
    failures: list[dict] = []
    correct = 0
    for example in dataset.examples:
        result = scorer.score(example["text"])
        expected = example["label"]
        predicted = result.label.value
        confusion[expected][predicted] += 1
        if expected == predicted:
            correct += 1
        else:
            failures.append(
                {
                    **example,
                    "expected": expected,
                    "predicted": predicted,
                    "score": result.score,
                }
            )

    per_label = {}
    for label in _LABELS:
        true_positive = confusion[label][label]
        support = sum(confusion[label].values())
        predicted_count = sum(confusion[expected][label] for expected in _LABELS)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
        }

    total = len(dataset.examples)
    return {
        "dataset": {
            "name": dataset.name,
            "version": dataset.version,
            "description": dataset.description,
            "license": dataset.license,
            "examples": total,
        },
        "analyzer": scorer.name,
        "accuracy": round(correct / total, 4),
        "correct": correct,
        "total": total,
        "macro_f1": round(sum(row["f1"] for row in per_label.values()) / len(_LABELS), 4),
        "per_label": per_label,
        "confusion_matrix": confusion,
        "failures": failures,
    }
