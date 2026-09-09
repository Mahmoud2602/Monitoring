"""
Historical Analysis Page for Industrial Production Monitor.
Assembles:
- Historical Date & Station Filter Bar
- 9-Metric Executive KPI Summary Cards
- Interactive PyQtGraph Performance & Reliability Charts
- Downtime & Alarm History Audit Tables
- Data Export Module
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.data_manager import DataManager
from database.query_service import DatePreset, HistoricalQueryService
from ui.historical.charts import (
    AchievementTrendChart,
    DowntimeTrendChart,
    ProductionTrendChart,
    SpeedTrendChart,
    StationDowntimeChart,
    StationStopsChart,
)
from ui.historical.filter_bar import FilterBar
from ui.historical.kpi_summary_bar import KPISummaryBar
from ui.historical.tables import HistoricalTablesCard
from ui.theme import IndustrialTheme
from utils.logger import get_logger

logger = get_logger("ui.historical.page")


class HistoricalQueryWorker(QThread):
    """
    Background worker thread to execute heavy historical queries without blocking the Qt GUI thread.
    """
    data_loaded = Signal(dict)
    error_occurred = Signal(str)

    def __init__(
        self,
        query_service: HistoricalQueryService,
        preset: str,
        start_date: Optional[str],
        end_date: Optional[str],
        station_id: Optional[int],
        severity: str,
        station_names: Dict[str, str],
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.query_service = query_service
        self.preset = preset
        self.start_date = start_date
        self.end_date = end_date
        self.station_id = station_id
        self.severity = severity
        self.station_names = station_names

    def run(self) -> None:
        try:
            summary = self.query_service.get_historical_summary(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
                station_id=self.station_id,
            )
            prod_trend = self.query_service.get_production_trend(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
            )
            achieve_trend = self.query_service.get_achievement_trend(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
            )
            speed_trend = self.query_service.get_speed_trend(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
            )
            dt_trend = self.query_service.get_downtime_trend(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
                station_id=self.station_id,
            )
            st_downtime = self.query_service.get_downtime_by_station_full(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
                station_display_names=self.station_names,
            )
            st_stops = self.query_service.get_stop_count_by_station_full(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
                station_display_names=self.station_names,
            )
            dt_events = self.query_service.get_downtime_history_table(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
                station_id=self.station_id,
                station_display_names=self.station_names,
                limit=500,
            )
            alarms = self.query_service.get_alarm_history_table(
                preset=self.preset,
                start_date=self.start_date,
                end_date=self.end_date,
                station_id=self.station_id,
                severity=self.severity,
                station_display_names=self.station_names,
                limit=500,
            )

            result = {
                "summary": summary,
                "prod_trend": prod_trend,
                "achieve_trend": achieve_trend,
                "speed_trend": speed_trend,
                "dt_trend": dt_trend,
                "st_downtime": st_downtime,
                "st_stops": st_stops,
                "dt_events": dt_events,
                "alarms": alarms,
            }
            self.data_loaded.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))


class HistoricalPage(QWidget):
    """
    Dedicated Historical Analysis view.
    Communicates strictly with the HistoricalQueryService to fetch and render
    aggregated time-series and event records.
    """

    def __init__(
        self,
        data_manager: DataManager,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.data_manager = data_manager
        self.query_service: HistoricalQueryService = data_manager.query_service
        self.setObjectName("HistoricalAnalysisPage")

        # Current filter state
        self._current_preset = DatePreset.TODAY.value
        self._current_start_date = ""
        self._current_end_date = ""
        self._current_station_id: Optional[int] = None
        self._current_severity = "All"
        self._worker: Optional[HistoricalQueryWorker] = None

        self._init_ui()

        # Connect signals
        self.filter_bar.filter_changed.connect(self._on_filters_changed)
        self.filter_bar.export_requested.connect(self._on_export_requested)
        self.tables_card.severity_filter_changed.connect(self._on_severity_changed)

        # Initial data load
        QTimer.singleShot(100, self.refresh_data)

    def _init_ui(self) -> None:
        self.setStyleSheet(f"""
            QWidget#HistoricalAnalysisPage {{
                background-color: {IndustrialTheme.BG_DARK};
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_SECONDARY};
                padding: 7px 18px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {IndustrialTheme.COLOR_BLUE_BG};
                color: {IndustrialTheme.TEXT_CYAN};
                border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                border-bottom: none;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {IndustrialTheme.BG_CARD_HOVER};
            }}
        """)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(16, 12, 16, 16)
        page_layout.setSpacing(12)

        # 1. Top: Filter Bar
        station_names = self.data_manager.kpi_engine.station_display_names
        self.filter_bar = FilterBar(station_display_names=station_names, parent=self)
        page_layout.addWidget(self.filter_bar)

        # Scrollable container for charts and tables
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # 2. Executive KPI Summary Cards
        self.kpi_summary = KPISummaryBar(scroll_content)
        content_layout.addWidget(self.kpi_summary)

        # 3. Interactive Charts Container (Tabbed to give maximum chart height & legibility)
        self.chart_tabs = QTabWidget(scroll_content)

        # Tab 1: Production & Achievement Trends
        tab_prod_achieve = QWidget()
        t1_layout = QHBoxLayout(tab_prod_achieve)
        t1_layout.setContentsMargins(0, 8, 0, 0)
        t1_layout.setSpacing(12)

        self.chart_prod = ProductionTrendChart(tab_prod_achieve)
        self.chart_prod.setMinimumHeight(320)
        self.chart_achieve = AchievementTrendChart(tab_prod_achieve)
        self.chart_achieve.setMinimumHeight(320)

        t1_layout.addWidget(self.chart_prod, stretch=1)
        t1_layout.addWidget(self.chart_achieve, stretch=1)
        self.chart_tabs.addTab(tab_prod_achieve, "📈 Production & Achievement Trends")

        # Tab 2: Conveyor Speed & Process Dynamics
        tab_speed = QWidget()
        t2_layout = QHBoxLayout(tab_speed)
        t2_layout.setContentsMargins(0, 8, 0, 0)
        t2_layout.setSpacing(12)

        self.chart_speed = SpeedTrendChart(tab_speed)
        self.chart_speed.setMinimumHeight(320)

        t2_layout.addWidget(self.chart_speed, stretch=1)
        self.chart_tabs.addTab(tab_speed, "⚡ Conveyor Speed & Setpoint Dynamics")

        # Tab 3: Downtime & Bottleneck Trends
        tab_dt_trends = QWidget()
        t3_layout = QHBoxLayout(tab_dt_trends)
        t3_layout.setContentsMargins(0, 8, 0, 0)
        t3_layout.setSpacing(12)

        self.chart_dt_trend = DowntimeTrendChart(tab_dt_trends)
        self.chart_dt_trend.setMinimumHeight(320)
        self.chart_st_downtime = StationDowntimeChart(tab_dt_trends)
        self.chart_st_downtime.setMinimumHeight(320)

        t3_layout.addWidget(self.chart_dt_trend, stretch=1)
        t3_layout.addWidget(self.chart_st_downtime, stretch=1)
        self.chart_tabs.addTab(tab_dt_trends, "⏱️ Downtime Timeline & Station Bottlenecks")

        # Tab 4: Complete 10-Station Breakdown
        tab_stations = QWidget()
        t4_layout = QHBoxLayout(tab_stations)
        t4_layout.setContentsMargins(0, 8, 0, 0)
        t4_layout.setSpacing(12)

        self.chart_st_downtime_clone = StationDowntimeChart(tab_stations)
        self.chart_st_downtime_clone.setMinimumHeight(320)
        self.chart_st_stops = StationStopsChart(tab_stations)
        self.chart_st_stops.setMinimumHeight(320)

        t4_layout.addWidget(self.chart_st_downtime_clone, stretch=1)
        t4_layout.addWidget(self.chart_st_stops, stretch=1)
        self.chart_tabs.addTab(tab_stations, "🏭 10-Station Downtime & Stop Frequency")

        content_layout.addWidget(self.chart_tabs)

        # 4. Historical Data Tables Card (Downtime Events & Alarm Audit Logs)
        self.tables_card = HistoricalTablesCard(scroll_content)
        self.tables_card.setMinimumHeight(340)
        content_layout.addWidget(self.tables_card)

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area, stretch=1)

    def _on_filters_changed(
        self,
        preset: str,
        start_date_str: str,
        end_date_str: str,
        station_id: Optional[int],
    ) -> None:
        self._current_preset = preset
        self._current_start_date = start_date_str
        self._current_end_date = end_date_str
        self._current_station_id = station_id
        self.refresh_data()

    def _on_severity_changed(self, severity: str) -> None:
        self._current_severity = severity
        self._refresh_alarm_table()

    def refresh_data(self) -> None:
        """Fetch historical datasets asynchronously in background QThread to avoid GUI blocking."""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(200)

        self.filter_bar.lbl_update_time.setText("Querying database...")

        preset = self._current_preset
        s_date = self._current_start_date or None
        e_date = self._current_end_date or None
        station_id = self._current_station_id
        station_names = self.data_manager.kpi_engine.station_display_names

        self._worker = HistoricalQueryWorker(
            query_service=self.query_service,
            preset=preset,
            start_date=s_date,
            end_date=e_date,
            station_id=station_id,
            severity=self._current_severity,
            station_names=station_names,
            parent=self,
        )
        self._worker.data_loaded.connect(self._on_data_loaded)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.start()

    def _on_data_loaded(self, data: Dict[str, Any]) -> None:
        """Handle loaded data bundle safely on the GUI thread."""
        try:
            summary = data.get("summary", {})
            self.kpi_summary.update_metrics(summary)

            station_names = self.data_manager.kpi_engine.station_display_names
            station_id = self._current_station_id
            st_text = (
                f"Station {station_id:02d} ({station_names.get(str(station_id)) or station_names.get(station_id) or ''})"
                if station_id is not None
                else "All Stations (1 - 10)"
            )
            range_label = summary.get("date_range_label", "")
            self.filter_bar.set_active_summary_text(
                f"AUDIT RANGE: {range_label} | TARGET: {st_text}"
            )

            self.chart_prod.update_data(data.get("prod_trend", []))
            self.chart_achieve.update_data(data.get("achieve_trend", []))
            self.chart_speed.update_data(data.get("speed_trend", []))
            self.chart_dt_trend.update_data(data.get("dt_trend", []))

            st_dt = data.get("st_downtime", [])
            self.chart_st_downtime.update_data(st_dt)
            self.chart_st_downtime_clone.update_data(st_dt)

            self.chart_st_stops.update_data(data.get("st_stops", []))
            self.tables_card.update_downtime_data(data.get("dt_events", []))
            self.tables_card.update_alarm_data(data.get("alarms", []))

            now_str = datetime.now().strftime("%H:%M:%S")
            self.filter_bar.lbl_update_time.setText(f"Updated: {now_str}")
        except Exception as e:
            logger.error("Error updating historical page views: %s", e, exc_info=True)

    def _on_worker_error(self, err_msg: str) -> None:
        logger.error("Historical query worker failed: %s", err_msg)
        self.filter_bar.lbl_update_time.setText("Query Error")

    def _refresh_alarm_table(self) -> None:
        """Fetch alarm records with current severity and station filters."""
        try:
            preset = self._current_preset
            s_date = self._current_start_date or None
            e_date = self._current_end_date or None
            station_id = self._current_station_id
            station_names = self.data_manager.kpi_engine.station_display_names

            alarms = self.query_service.get_alarm_history_table(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_id=station_id,
                severity=self._current_severity,
                station_display_names=station_names,
                limit=500,
            )
            self.tables_card.update_alarm_data(alarms)
        except Exception as e:
            logger.error("Failed to query alarm history table: %s", e, exc_info=True)

    def _on_export_requested(self) -> None:
        """Generate full JSON audit export file."""
        try:
            preset = self._current_preset
            s_date = self._current_start_date or None
            e_date = self._current_end_date or None
            station_id = self._current_station_id
            station_names = self.data_manager.kpi_engine.station_display_names

            dataset = self.query_service.get_export_dataset(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_id=station_id,
                station_display_names=station_names,
            )

            os.makedirs("exports", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"exports/historical_audit_{ts}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(dataset, f, indent=2)

            self.filter_bar.lbl_update_time.setText(f"Exported: {filename}")
            logger.info("Historical audit dataset successfully exported to %s", filename)
        except Exception as e:
            logger.error("Failed to export historical dataset: %s", e, exc_info=True)
            self.filter_bar.lbl_update_time.setText("Export Failed")

    def _refresh_alarm_table(self) -> None:
        """Fetch alarm records with current severity and station filters."""
        try:
            preset = self._current_preset
            s_date = self._current_start_date or None
            e_date = self._current_end_date or None
            station_id = self._current_station_id
            station_names = self.data_manager.kpi_engine.station_display_names

            alarms = self.query_service.get_alarm_history_table(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_id=station_id,
                severity=self._current_severity,
                station_display_names=station_names,
                limit=500,
            )
            self.tables_card.update_alarm_data(alarms)
        except Exception as e:
            logger.error("Failed to query alarm history table: %s", e, exc_info=True)

    def stop(self) -> None:
        """Safely stop and wait for background query worker if running."""
        if self._worker and self._worker.isRunning():
            self._worker.wait(1000)
