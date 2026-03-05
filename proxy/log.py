"""
log.py
------
Structured logging for anonymyzr.

Logs every detected entity and its synthetic replacement so you can
verify what's being scrubbed during testing.

WARNING: Log files contain real PII. Keep them local and delete after
testing. Set ANONYMYZR_LOG_REAL_VALUES=false to log entity types only.

Controlled by environment variables:
  ANONYMYZR_LOG_FILE         path to log file (default: logs/anonymyzr.log)
  ANONYMYZR_LOG_LEVEL        DEBUG | INFO | WARNING  (default: INFO)
  ANONYMYZR_LOG_REAL_VALUES  true | false            (default: true)
"""

import logging
import os
from pathlib import Path

_LOG_FILE = os.environ.get("ANONYMYZR_LOG_FILE", "logs/anonymyzr.log")
_LOG_LEVEL = os.environ.get("ANONYMYZR_LOG_LEVEL", "INFO").upper()
_LOG_REAL_VALUES = os.environ.get("ANONYMYZR_LOG_REAL_VALUES", "true").lower() == "true"

# Ensure log directory exists
Path(_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger("anonymyzr")
_logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

# Console handler
_ch = logging.StreamHandler()
_ch.setFormatter(_fmt)
_logger.addHandler(_ch)

# File handler
_fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
_logger.addHandler(_fh)


def log_request(session_id: str, model: str, message_count: int):
    _logger.info(f"[{session_id[:8]}] REQUEST  model={model}  messages={message_count}")


def log_entity(session_id: str, entity_type: str, real_value: str, synthetic_value: str):
    if _LOG_REAL_VALUES:
        _logger.info(
            f"[{session_id[:8]}] SCRUBBED  {entity_type:<28}  "
            f'"{real_value}"  →  "{synthetic_value}"'
        )
    else:
        _logger.info(
            f"[{session_id[:8]}] SCRUBBED  {entity_type:<28}  "
            f"[{len(real_value)} chars]  →  [{len(synthetic_value)} chars]"
        )


def log_response(session_id: str, stop_reason: str, swaps_applied: int):
    _logger.info(
        f"[{session_id[:8]}] RESPONSE  stop_reason={stop_reason}  "
        f"values_restored={swaps_applied}"
    )


def log_error(session_id: str, error: str):
    _logger.error(f"[{session_id[:8]}] ERROR  {error}")
