"""Versioned analyzer evaluation and metric-report tests."""

import json
from collections import Counter

import pytest

from harken.evaluate import evaluate_sentiment, load_sentiment_dataset


def test_bundled_dataset_is_balanced_versioned_and_measurable():
    dataset = load_sentiment_dataset()
    assert dataset.name == "harken-product-sentiment"
    assert dataset.version == 1
    assert dataset.license == "CC0-1.0"
    assert len(dataset.examples) == 60
    assert Counter(example["label"] for example in dataset.examples) == {
        "positive": 20,
        "neutral": 20,
        "negative": 20,
    }

    report = evaluate_sentiment(dataset)
    assert report["accuracy"] == 0.9667
    assert report["correct"] == 58
    assert report["macro_f1"] == pytest.approx(0.9662, abs=0.0001)
    assert [failure["id"] for failure in report["failures"]] == ["neg-15", "neg-16"]
    assert report["confusion_matrix"]["negative"] == {
        "positive": 1,
        "neutral": 1,
        "negative": 18,
    }


def test_custom_dataset_can_be_loaded(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps(
            {
                "name": "custom",
                "version": 2,
                "license": "private",
                "examples": [
                    {"id": "one", "text": "excellent", "label": "positive"},
                    {"id": "two", "text": "release Tuesday", "label": "neutral"},
                    {"id": "three", "text": "terrible", "label": "negative"},
                ],
            }
        ),
        encoding="utf-8",
    )
    dataset = load_sentiment_dataset(path)
    report = evaluate_sentiment(dataset)
    assert dataset.version == 2
    assert report["accuracy"] == 1.0
    assert report["macro_f1"] == 1.0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "bad", "version": 1, "examples": []},
        {
            "name": "bad",
            "version": 1,
            "examples": [{"id": "x", "text": "hello", "label": "mixed"}],
        },
        {
            "name": "bad",
            "version": 1,
            "examples": [
                {"id": "same", "text": "hello", "label": "neutral"},
                {"id": "same", "text": "again", "label": "neutral"},
            ],
        },
    ],
)
def test_invalid_datasets_are_rejected(tmp_path, payload):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_sentiment_dataset(path)
