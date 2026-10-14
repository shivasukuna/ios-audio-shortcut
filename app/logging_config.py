"""Structured JSON logging configuration for the audio-downloader application.

Provides a custom JSON formatter with automatic masking of sensitive credentials,
contextvars-based request ID tracking, and unified logger initialization.
"""

from contextvars import ContextVar, Token
from datetime import datetime, timezone
import json
import logging
import re
import sys
from typing import Any

# Context variable for tracking request IDs across async tasks
_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Sensitive keys and patterns to redact in logs
SENSITIVE_KEYWORDS: tuple[str, ...] = ("token", "authorization", "password")
REDACTED_TEXT: str = "[REDACTED]"

# Regex patterns to sanitize inline authorization tokens in log messages
_AUTH_HEADER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE)
_QUERY_TOKEN_RE = re.compile(r"((?:token|api_key|password)=)[^\s&]+", re.IGNORECASE)

# Standard LogRecord attributes to exclude from custom 'extra' fields
STANDARD_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def get_request_id() -> str | None:
    """Return the current context request ID, or None if not set."""
    return _request_id_ctx.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Set the current context request ID and return the reset token."""
    return _request_id_ctx.set(request_id)


def is_sensitive_key(key: str) -> bool:
    """Determine if a key name indicates sensitive credential data."""
    lowered = key.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def redact_sensitive_value(value: Any) -> Any:
    """Recursively mask sensitive values in nested mappings and sequences."""
    if isinstance(value, dict):
        redacted_dict: dict[str, Any] = {}
        for k, v in value.items():
            str_k = str(k)
            if is_sensitive_key(str_k):
                redacted_dict[str_k] = REDACTED_TEXT
            else:
                redacted_dict[str_k] = redact_sensitive_value(v)
        return redacted_dict
    elif isinstance(value, (list, tuple, set)):
        return [redact_sensitive_value(item) for item in value]
    return value


def redact_text_message(message: str) -> str:
    """Mask inline secrets such as Bearer tokens in raw string messages."""
    message = _AUTH_HEADER_RE.sub(r"\1" + REDACTED_TEXT, message)
    message = _QUERY_TOKEN_RE.sub(r"\1" + REDACTED_TEXT, message)
    return message


class JSONFormatter(logging.Formatter):
    """Custom logging formatter that renders records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the specified record as a JSON string."""
        now_utc = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        raw_message = record.getMessage()
        sanitized_message = redact_text_message(raw_message)

        log_payload: dict[str, Any] = {
            "timestamp": now_utc,
            "level": record.levelname,
            "logger": record.name,
            "message": sanitized_message,
        }

        # Attach request_id if present in context
        req_id = get_request_id()
        if req_id is not None:
            log_payload["request_id"] = req_id

        # Attach custom 'extra' kwargs passed to logging methods
        for attr, value in record.__dict__.items():
            if attr not in STANDARD_RECORD_ATTRS and not attr.startswith("_"):
                if is_sensitive_key(attr):
                    log_payload[attr] = REDACTED_TEXT
                else:
                    log_payload[attr] = redact_sensitive_value(value)

        # Attach exception details if logged
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Attach stack traces if present
        if record.stack_info:
            log_payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_payload, default=str, ensure_ascii=False)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the root logger with the structured JSON formatter.

    Args:
        log_level: String level name (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR').
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any pre-existing handlers to prevent duplicated output
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # Adjust external noisy loggers
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with the given name.

    Args:
        name: Name of the logger (typically __name__).

    Returns:
        logging.Logger instance.
    """
    return logging.getLogger(name)
