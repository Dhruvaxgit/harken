"""Structured logging is machine-readable and remains useful to local operators."""

import json
import logging

import pytest

from harken.observability import configure_logging, log_event


def test_json_logging_emits_one_structured_event(capsys):
    logger = configure_logging("json", "INFO").getChild("test")
    try:
        log_event(
            logger,
            "source_scan_complete",
            query="acme",
            source="hackernews",
            duration_seconds=0.125,
            fetched=3,
        )
        payload = json.loads(capsys.readouterr().err)
        assert payload == {
            "timestamp": payload["timestamp"],
            "level": "info",
            "logger": "harken.test",
            "event": "source_scan_complete",
            "query": "acme",
            "source": "hackernews",
            "duration_seconds": 0.125,
            "fetched": 3,
        }
        assert payload["timestamp"].endswith("Z")
    finally:
        configure_logging("console", "INFO")


@pytest.mark.parametrize(
    ("log_format", "level", "message"),
    [
        ("xml", "INFO", "format must be console or json"),
        ("json", "TRACE", "level must be"),
    ],
)
def test_logging_configuration_rejects_unknown_values(log_format, level, message):
    with pytest.raises(ValueError, match=message):
        configure_logging(log_format, level)


def test_log_level_filters_debug_events(capsys):
    logger = configure_logging("json", "WARNING").getChild("filter")
    try:
        log_event(logger, "hidden", level=logging.DEBUG)
        assert capsys.readouterr().err == ""
    finally:
        configure_logging("console", "INFO")
