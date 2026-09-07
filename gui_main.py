"""
Dedicated PySide6 GUI Entry Point for Industrial Real-Time Production Monitor.
Launches the native control room desktop application.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from core.data_manager import DataManager
from ui.main_window import MainWindow
from utils.logger import setup_logger, get_logger


def run_gui(
    config_path: str = "config/settings.json",
    mapping_path: str = "config/plc_mapping.json",
    db_path: str | None = None,
) -> int:
    """Launch the PySide6 desktop GUI application."""
    logger = setup_logger("plc_gui", level="INFO")
    logger.info("Starting Industrial Real-Time Production Monitor (PySide6 Native Desktop)...")

    # If running headless without DISPLAY, fall back to offscreen platform safely
    if sys.platform.startswith("linux") and "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
        if "QT_QPA_PLATFORM" not in os.environ:
            logger.warning("No DISPLAY or WAYLAND_DISPLAY found. Setting QT_QPA_PLATFORM='offscreen'.")
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    app.setApplicationName("Industrial Real-Time Production Monitor")
    app.setOrganizationName("Automation Systems")

    # Initialize DataManager
    data_manager = DataManager(
        settings_path=config_path,
        mapping_path=mapping_path,
        db_path=db_path,
    )

    # Start background polling in DataManager
    data_manager.start()

    # Create MainWindow
    window = MainWindow(
        data_manager=data_manager,
        config=data_manager.settings,
    )
    window.show()

    # Run Qt Event Loop
    exit_code = app.exec()

    # Graceful shutdown
    data_manager.stop()
    return exit_code


if __name__ == "__main__":
    cfg = sys.argv[1] if len(sys.argv) > 1 else "config/settings.json"
    sys.exit(run_gui(config_path=cfg))
