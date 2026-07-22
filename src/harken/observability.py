"""Small, dependency-free structured logging helpers for Harken."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_HANDLER_MARKER = "_harken_observability_handler"


class JsonFormatter(logging.Formatter):
    """Render one application event as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _timestamp(record.created),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


class ConsoleFormatter(logging.Formatter):
    """Readable local output that preserves the same structured event fields."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            _timestamp(record.created),
            record.levelname,
            record.name,
            str(getattr(record, "event", record.getMessage())),
        ]
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            parts.extend(
                f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
                for key, value in sorted(fields.items())
            )
        if record.exc_info:
            parts.append(self.formatException(record.exc_info))
        return " ".join(parts)


def configure_logging(log_format: str = "console", level: str = "INFO") -> logging.Logger:
    """Configure only Harken's logger, leaving host applications untouched."""
    normalized_format = log_format.strip().lower()
    if normalized_format not in {"console", "json"}:
        raise ValueError("log format must be console or json")
    normalized_level = level.strip().upper()
    if normalized_level == "WARN":
        normalized_level = "WARNING"
    if normalized_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("log level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")

    logger = logging.getLogger("harken")
    logger.setLevel(normalized_level)
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(JsonFormatter() if normalized_format == "json" else ConsoleFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a named event without relying on free-form message parsing."""
    logger.log(level, event, extra={"event": event, "fields": fields})


def _timestamp(created: float) -> str:
    return (
        datetime.fromtimestamp(created, timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
