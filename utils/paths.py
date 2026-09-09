"""
Industrial PLC Production Monitor - Runtime Path Resolver
Ensures portable data handling in both standard Python environments
and PyInstaller packaged executable bundles.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True if running inside a PyInstaller or cx_Freeze bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_base_dir() -> Path:
    """
    Get the base directory containing bundled assets, configs, and application source.
    In frozen mode, this points to sys._MEIPASS.
    In development mode, this points to the repository root directory.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def get_app_data_dir() -> Path:
    """
    Get the directory where runtime-generated data (databases, configs, logs) reside.
    In frozen mode, points to the directory containing the executable.
    In development mode, points to the repository root directory.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_config_path(filename: str = "settings.json") -> str:
    """Resolve full path to a configuration file."""
    data_cfg = get_app_data_dir() / "config" / filename
    if data_cfg.exists():
        return str(data_cfg)
    base_cfg = get_base_dir() / "config" / filename
    return str(base_cfg)


def get_mapping_path(filename: str = "plc_mapping.json") -> str:
    """Resolve full path to the PLC mapping configuration file."""
    data_map = get_app_data_dir() / "config" / filename
    if data_map.exists():
        return str(data_map)
    base_map = get_base_dir() / "config" / filename
    return str(base_map)


def get_database_path(filename: str = "production_monitor.db") -> str:
    """Resolve full path to the SQLite database."""
    db_dir = get_app_data_dir() / "data"
    # If legacy root database exists or data dir is used
    if (get_app_data_dir() / filename).exists():
        return str(get_app_data_dir() / filename)
    os.makedirs(db_dir, exist_ok=True)
    return str(db_dir / filename)


def ensure_runtime_directories() -> None:
    """Ensure runtime folders (logs, exports, backups, data) exist."""
    app_dir = get_app_data_dir()
    for sub in ["logs", "exports", "backups", "data", "config"]:
        os.makedirs(app_dir / sub, exist_ok=True)
