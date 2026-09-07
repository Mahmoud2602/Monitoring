"""
Main Window for the PySide6 Industrial Real-Time Production Monitoring System.
Assembles the Header Bar, Dashboard Page, and TelemetryBridge background thread.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.data_manager import DataManager
from database.models import AlarmEventRecord
from kpi.models import KPISnapshot
from plc.plc_data import NormalizedPLCData
from ui.dashboard.dashboard_page import DashboardPage
from ui.historical.historical_page import HistoricalPage
from ui.theme import IndustrialTheme, get_application_stylesheet
from ui.widgets.header_bar import HeaderBar
from ui.widgets.navigation_bar import NavigationBar
from ui.worker import TelemetryBridge
from utils.logger import get_logger

logger = get_logger("ui.main_window")


class MainWindow(QMainWindow):
    """
    Main desktop window for the Industrial Real-Time Production Monitor.
    Runs in factory control rooms, supervisor stations, and plant manager displays.
    """

    def __init__(
        self,
        data_manager: DataManager,
        config: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.data_manager = data_manager
        self.config = config or {}

        # Extract configuration settings
        assembly_cfg = self.config.get("assembly_line", {})
        self.line_name = assembly_cfg.get("name", "Assembly Line")
        self.station_names = self.config.get("station_display_names", {})

        sim_settings = self.config.get("simulation_settings", {})
        self.speed_setpoint = float(sim_settings.get("base_speed", 45.0))
        self.product_pitch_m = float(assembly_cfg.get("product_pitch_meters", 0.75))

        gui_cfg = self.config.get("gui_settings", {})
        self.window_title = gui_cfg.get("window_title", "Industrial Real-Time Production Monitor")
        self.company_logo_path = gui_cfg.get("company_logo_path", "assets/company_logo.png")
        self.customer_logo_path = gui_cfg.get("customer_logo_path", "assets/customer_logo.png")
        self.refresh_interval_ms = int(gui_cfg.get("refresh_interval_ms", 500))

        # Configure Window
        self.setWindowTitle(f"{self.window_title} - [{self.line_name}]")
        self.resize(1600, 920)
        self.setMinimumSize(1180, 720)

        # Apply dark industrial stylesheet
        self.setStyleSheet(get_application_stylesheet())

        # Build Layout
        self._init_ui()

        # Start Telemetry Worker Thread
        self._init_worker()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setObjectName("CentralWidget")
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Bar
        self.header_bar = HeaderBar(
            line_name=self.line_name,
            company_logo_path=self.company_logo_path,
            customer_logo_path=self.customer_logo_path,
            simulation_mode=self.data_manager.simulation_mode,
            parent=central_widget,
        )
        main_layout.addWidget(self.header_bar)

        # 2. Control Room Navigation Bar (Phase 5)
        self.nav_bar = NavigationBar(parent=central_widget)
        self.nav_bar.page_selected.connect(self._on_navigation_changed)
        main_layout.addWidget(self.nav_bar)

        # 3. Main Stack / Content View
        self.stack = QStackedWidget(central_widget)
        self.dashboard_page = DashboardPage(
            line_name=self.line_name,
            station_display_names=self.station_names,
            speed_setpoint=self.speed_setpoint,
            product_pitch_m=self.product_pitch_m,
            parent=self.stack,
        )
        self.stack.addWidget(self.dashboard_page)

        # 4. Historical Analysis Page (Phase 5)
        self.historical_page = HistoricalPage(
            data_manager=self.data_manager,
            parent=self.stack,
        )
        self.stack.addWidget(self.historical_page)

        main_layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central_widget)

        # 3. Industrial Status Bar
        status_bar = QStatusBar(self)
        status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {IndustrialTheme.BG_DARK};
                color: {IndustrialTheme.TEXT_MUTED};
                border-top: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                font-size: 11px;
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                padding: 2px 8px;
            }}
        """)
        db_path = "production_monitor.db"
        if hasattr(self.data_manager, "db_manager") and self.data_manager.db_manager:
            db_path = self.data_manager.db_manager.db_path
        status_bar.showMessage(
            f"SYSTEM READY | SQLite WAL: ACTIVE [{db_path}] | Background Telemetry Thread: ACTIVE"
        )
        self.setStatusBar(status_bar)

    def _init_worker(self) -> None:
        """Instantiate and start the background telemetry QThread."""
        self.bridge = TelemetryBridge(
            data_manager=self.data_manager,
            poll_interval_ms=self.refresh_interval_ms,
            db_poll_interval_s=1.0,
            parent=self,
        )

        # Connect Qt Signals to GUI slots
        self.bridge.telemetry_received.connect(self._on_telemetry)
        self.bridge.kpi_received.connect(self._on_kpi)
        self.bridge.downtime_stats_received.connect(self._on_downtime_stats)
        self.bridge.alarms_received.connect(self._on_alarms)
        self.bridge.connection_changed.connect(self._on_connection_changed)
        self.bridge.error_occurred.connect(self._on_error)

        # Start background worker thread
        self.bridge.start()

    def _on_telemetry(self, data: NormalizedPLCData) -> None:
        """Handle raw PLC telemetry from background worker."""
        self.dashboard_page.update_telemetry(data)

    def _on_kpi(self, kpi: KPISnapshot) -> None:
        """Handle KPI snapshot from background worker."""
        self.dashboard_page.update_kpi(kpi)

    def _on_downtime_stats(
        self,
        stats: Dict[str, Any],
        running_time_s: float,
        active_stops: int,
    ) -> None:
        """Handle periodic database downtime query results."""
        self.dashboard_page.update_downtime_stats(stats, running_time_s, active_stops)

    def _on_alarms(self, alarms: list) -> None:
        """Handle active alarms list."""
        self.dashboard_page.update_alarms(alarms)

    def _on_connection_changed(
        self,
        connected: bool,
        endpoint_info: str,
        scan_time_ms: float,
    ) -> None:
        """Update header and dashboard connectivity indicators."""
        self.header_bar.set_connection_status(connected, endpoint_info, scan_time_ms)
        if not connected:
            self.dashboard_page.set_disconnected()

    def _on_error(self, err_msg: str) -> None:
        """Log background errors safely."""
        logger.warning("Background worker reported error: %s", err_msg)

    def _on_navigation_changed(self, page_name: str, index: int) -> None:
        """Switch views in the main stack widget."""
        if index < self.stack.count():
            logger.info("Navigation switch to page '%s' (index %d)", page_name, index)
            self.stack.setCurrentIndex(index)
            if index == 1:
                # Refresh historical analysis view on navigation
                self.historical_page.refresh_data()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Gracefully terminate background threads on window exit."""
        logger.info("MainWindow closing, stopping TelemetryBridge worker...")
        if hasattr(self, "bridge") and self.bridge:
            self.bridge.stop()
        super().closeEvent(event)
