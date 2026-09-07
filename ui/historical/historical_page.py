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

from PySide6.QtCore import Qt, QTimer
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

        # Tab 1: Production & Speed Trends
        tab_prod_speed = QWidget()
        t1_layout = QHBoxLayout(tab_prod_speed)
        t1_layout.setContentsMargins(0, 8, 0, 0)
        t1_layout.setSpacing(12)

        self.chart_prod = ProductionTrendChart(tab_prod_speed)
        self.chart_prod.setMinimumHeight(320)
        self.chart_speed = SpeedTrendChart(tab_prod_speed)
        self.chart_speed.setMinimumHeight(320)

        t1_layout.addWidget(self.chart_prod, stretch=1)
        t1_layout.addWidget(self.chart_speed, stretch=1)
        self.chart_tabs.addTab(tab_prod_speed, "📈 Production & Conveyor Speed Trends")

        # Tab 2: Downtime & Bottleneck Trends
        tab_dt_trends = QWidget()
        t2_layout = QHBoxLayout(tab_dt_trends)
        t2_layout.setContentsMargins(0, 8, 0, 0)
        t2_layout.setSpacing(12)

        self.chart_dt_trend = DowntimeTrendChart(tab_dt_trends)
        self.chart_dt_trend.setMinimumHeight(320)
        self.chart_st_downtime = StationDowntimeChart(tab_dt_trends)
        self.chart_st_downtime.setMinimumHeight(320)

        t2_layout.addWidget(self.chart_dt_trend, stretch=1)
        t2_layout.addWidget(self.chart_st_downtime, stretch=1)
        self.chart_tabs.addTab(tab_dt_trends, "⏱️ Downtime Timeline & Station Bottlenecks")

        # Tab 3: Complete 10-Station Breakdown
        tab_stations = QWidget()
        t3_layout = QHBoxLayout(tab_stations)
        t3_layout.setContentsMargins(0, 8, 0, 0)
        t3_layout.setSpacing(12)

        self.chart_st_downtime_clone = StationDowntimeChart(tab_stations)
        self.chart_st_downtime_clone.setMinimumHeight(320)
        self.chart_st_stops = StationStopsChart(tab_stations)
        self.chart_st_stops.setMinimumHeight(320)

        t3_layout.addWidget(self.chart_st_downtime_clone, stretch=1)
        t3_layout.addWidget(self.chart_st_stops, stretch=1)
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
        """Fetch historical datasets from SQLite repository services and update views."""
        try:
            preset = self._current_preset
            s_date = self._current_start_date or None
            e_date = self._current_end_date or None
            station_id = self._current_station_id
            station_names = self.data_manager.kpi_engine.station_display_names

            # 1. Summary Metrics
            summary = self.query_service.get_historical_summary(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_id=station_id,
            )
            self.kpi_summary.update_metrics(summary)

            # Update Filter Bar status text
            st_text = (
                f"Station {station_id:02d} ({station_names.get(str(station_id)) or station_names.get(station_id) or ''})"
                if station_id is not None
                else "All Stations (1 - 10)"
            )
            self.filter_bar.set_active_summary_text(
                f"AUDIT RANGE: {summary['date_range_label']} | TARGET: {st_text}"
            )

            # 2. Production Trend
            prod_trend = self.query_service.get_production_trend(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
            )
            self.chart_prod.update_data(prod_trend)

            # 3. Speed Trend
            speed_trend = self.query_service.get_speed_trend(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
            )
            self.chart_speed.update_data(speed_trend)

            # 4. Downtime Trend
            dt_trend = self.query_service.get_downtime_trend(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_id=station_id,
            )
            self.chart_dt_trend.update_data(dt_trend)

            # 5. Station Breakdown (Stations 1-10)
            st_downtime = self.query_service.get_downtime_by_station_full(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_display_names=station_names,
            )
            self.chart_st_downtime.update_data(st_downtime)
            self.chart_st_downtime_clone.update_data(st_downtime)

            st_stops = self.query_service.get_stop_count_by_station_full(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_display_names=station_names,
            )
            self.chart_st_stops.update_data(st_stops)

            # 6. Downtime History Table
            dt_events = self.query_service.get_downtime_history_table(
                preset=preset,
                start_date=s_date,
                end_date=e_date,
                station_id=station_id,
                station_display_names=station_names,
                limit=500,
            )
            self.tables_card.update_downtime_data(dt_events)

            # 7. Alarm History Table
            self._refresh_alarm_table()

        except Exception as e:
            logger.error("Failed to refresh historical analysis data: %s", e, exc_info=True)

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
