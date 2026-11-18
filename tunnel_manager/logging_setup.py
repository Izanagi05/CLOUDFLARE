from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


_SECRET_PATTERNS = [
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(--token\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(api[_-]?token\s*[=:]\s*)\S+"),
]


def redact(text: str) -> str:
    value = text
    value = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", value)
    value = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", value)
    value = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", value)
    return value


class EventLogger:
    def __init__(self, log_dir: Path, event_callback=None) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self.event_callback = event_callback
        self.logger = logging.getLogger("cloudflare_tunnel_manager")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = RotatingFileHandler(
                log_dir / "manager.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            self.logger.addHandler(handler)

    def log(self, message: str, level: int = logging.INFO) -> None:
        clean = redact(str(message)).rstrip()
        self.logger.log(level, clean)
        if self.event_callback:
            self.event_callback(clean)

    def info(self, message: str) -> None:
        self.log(message, logging.INFO)

    def warning(self, message: str) -> None:
        self.log(message, logging.WARNING)

    def error(self, message: str) -> None:
        self.log(message, logging.ERROR)
