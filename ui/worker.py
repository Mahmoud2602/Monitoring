"""
Real-Time Telemetry Background Worker for PySide6.
Ensures the GUI thread NEVER performs blocking PLC network communication or database queries.
Uses Qt Signals to safely marshal immutable data snapshots across thread boundaries.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from core.data_manager import DataManager
from database.models import AlarmEventRecord, DowntimeEventRecord
from database.query_service import DatePreset, HistoricalQueryService, get_production_date
from kpi.models import KPISnapshot
from plc.plc_data import NormalizedPLCData
from utils.logger import get_logger

logger = get_logger("ui.worker")


class TelemetryBridge(QThread):
    """
    Background worker thread connecting DataManager / PLC / SQLite services to Qt UI.
    Emits thread-safe Qt Signals consumed by the Main Dashboard.
    """

    # Qt Signals (automatically marshalled across thread boundaries into GUI event loop)
    telemetry_received = Signal(object)              # NormalizedPLCData
    kpi_received = Signal(object)                    # KPISnapshot
    downtime_stats_received = Signal(dict, float, int) # stats_dict, running_time_s, active_stops_cnt
    alarms_received = Signal(list)                   # List[AlarmEventRecord]
    connection_changed = Signal(bool, str, float)    # is_connected, info_str, scan_time_ms
    error_occurred = Signal(str)

    def __init__(
        self,
        data_manager: DataManager,
        poll_interval_ms: int = 500,
        db_poll_interval_s: float = 1.0,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.data_manager = data_manager
        self.poll_interval_ms = max(100, poll_interval_ms)
        self.db_poll_interval_s = max(0.5, db_poll_interval_s)
        self._running = False
        self._last_conn_state: Optional[bool] = None

        # Hook into DataManager listeners
        self.data_manager.register_data_listener(self._on_plc_data)
        self.data_manager.register_kpi_listener(self._on_kpi_data)

    def _on_plc_data(self, data: NormalizedPLCData) -> None:
        """Invoked from DataManager background thread upon fresh PLC telemetry."""
        if self._running:
            self.telemetry_received.emit(data)

    def _on_kpi_data(self, kpi: KPISnapshot) -> None:
        """Invoked from DataManager background thread upon fresh KPI calculation."""
        if self._running:
            self.kpi_received.emit(kpi)

    def run(self) -> None:
        """
        Main worker loop executing in a dedicated QThread.
        Periodically polls database services for downtime rollups and checks connection health.
        """
        self._running = True
        logger.info("TelemetryBridge background worker thread started.")

        last_db_poll = 0.0

        while self._running:
            try:
                now = time.time()

                # 1. Check PLC connection status
                is_connected = self.data_manager.is_connected()
                scan_time = getattr(self.data_manager, "last_scan_duration_ms", 0.0)

                # Format host/endpoint info
                endpoint = ""
                if hasattr(self.data_manager.client, "ip_address"):
                    endpoint = f"{self.data_manager.client.ip_address}:{self.data_manager.client.port}"
                elif self.data_manager.simulation_mode:
                    endpoint = "SIMULATOR"

                if is_connected != self._last_conn_state:
                    self._last_conn_state = is_connected
                    self.connection_changed.emit(is_connected, endpoint, scan_time)
                else:
                    # Emit regular heartbeat with latest scan time
                    self.connection_changed.emit(is_connected, endpoint, scan_time)

                # 2. Periodic Database stats query (off GUI thread)
                if now - last_db_poll >= self.db_poll_interval_s:
                    last_db_poll = now
                    self._query_database_stats()

            except Exception as exc:
                logger.error("Error in TelemetryBridge worker loop: %s", exc)
                self.error_occurred.emit(str(exc))

            # Sleep briefly to yield CPU
            self.msleep(200)

        logger.info("TelemetryBridge background worker thread stopped.")

    def _query_database_stats(self) -> None:
        """Query SQLite database service layer in background without blocking GUI."""
        try:
            query_svc = self.data_manager.get_query_service()
            if not query_svc:
                return

            # Query today's downtime statistics
            downtime_stats = query_svc.get_downtime_statistics(preset=DatePreset.TODAY)

            # Query active open downtime events
            active_events = []
            if self.data_manager.downtime_manager:
                active_events = self.data_manager.downtime_manager.get_active_downtime_events()

            active_stops_count = len(active_events)

            # Query active alarms
            active_alarms = []
            if self.data_manager.alarm_manager:
                active_alarms = self.data_manager.alarm_manager.get_active_alarms()

            self.alarms_received.emit(active_alarms)

            # Compute approximate running time today from plant start time
            # Using SummaryService or plant day start
            prod_date = get_production_date(self.data_manager.kpi_engine.production_day_start)
            # Calculate day start datetime
            try:
                dt_now = datetime.now(timezone.utc)
                parts = self.data_manager.kpi_engine.production_day_start.split(":")
                start_h, start_m = int(parts[0]), int(parts[1])
                start_today = dt_now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                if dt_now < start_today:
                    start_today = start_today.replace(day=start_today.day - 1)
                elapsed_total = (dt_now - start_today).total_seconds()
                total_down = float(downtime_stats.get("total_downtime_seconds", 0.0))
                running_time_s = max(0.0, elapsed_total - total_down)
            except Exception:
                running_time_s = 0.0

            self.downtime_stats_received.emit(downtime_stats, running_time_s, active_stops_count)

        except Exception as exc:
            logger.debug("Non-fatal database query in TelemetryBridge: %s", exc)

    def stop(self) -> None:
        """Stop background thread safely."""
        self._running = False
        self.wait(2000)
