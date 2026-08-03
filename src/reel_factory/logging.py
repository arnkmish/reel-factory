"""
Structured logging for the Reel Factory.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def configure_logging(log_dir: str | Path = "runtime/logs", level: str = "INFO"):
    """Configure structured JSON logging."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )


def get_logger(name: str = "reel_factory"):
    """Get a structured logger instance."""
    return structlog.get_logger(name)
