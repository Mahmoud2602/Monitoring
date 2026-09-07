"""
Industrial PLC Production Monitor - Logging Subsystem

Provides structured, high-visibility logging for PLC events,
connection lifecycles, communication errors, and normalized telemetry.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional


class IndustrialFormatter(logging.Formatter):
    """
    Console log formatter with high-contrast timestamps and level tags.
    """
    FORMAT = "%(asctime)s [%(levelname)-7s] [%(name)s] %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FORMAT, datefmt=self.DATE_FORMAT)


def setup_logger(
    name: str = "plc_monitor",
    level: str = "INFO",
    log_to_file: bool = False,
    log_file_path: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return a standardized logger for the industrial monitoring application.

    Args:
        name: Hierarchy name for the logger.
        level: Log level threshold (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_to_file: When True, writes log records to the designated file.
        log_file_path: Destination path for persistent log file.
    """
    logger = logging.getLogger(name)
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(IndustrialFormatter())
    logger.addHandler(console_handler)

    # File handler (if requested)
    if log_to_file and log_file_path:
        try:
            log_dir = os.path.dirname(log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
            file_handler.setLevel(numeric_level)
            file_formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)-7s] [%(name)s:%(filename)s:%(lineno)d] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as exc:
            logger.warning("Failed to initialize file logger at '%s': %s", log_file_path, exc)

    # Prevent propagating to root logger to avoid duplicated logs in unit test runners
    logger.propagate = False
    return logger


def get_logger(name: str = "plc_monitor") -> logging.Logger:
    """
    Retrieve an existing logger or return a newly created instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name=name)
    return logger
