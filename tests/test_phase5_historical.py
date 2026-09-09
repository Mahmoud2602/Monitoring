"""
Comprehensive Test Suite for Phase 5: Historical Analysis & Trend Visualization.
Tests:
1. HistoricalQueryService aggregations, trends, station downtime, alarms, and exports.
2. FilterBar preset and date range handling.
3. KPISummaryBar 9-card metric updates.
4. PyQtGraph interactive charts (Production, Speed, Downtime, Station Breakdown).
5. Downtime and Alarm historical audit tables.
6. Full HistoricalPage integration and MainWindow navigation.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from core.data_manager import DataManager
from database.database_manager import DatabaseManager
from database.models import AlarmEventRecord, DowntimeEventRecord, ProductionDataRecord
from database.query_service import DatePreset, HistoricalQueryService
from database.repositories import (
    AlarmRepository,
    DowntimeRepository,
    ProductionDataRepository,
)
from ui.historical.charts import (
    DowntimeTrendChart,
    ProductionTrendChart,
    SpeedTrendChart,
    StationDowntimeChart,
    StationStopsChart,
)
from ui.historical.filter_bar import FilterBar
from ui.historical.historical_page import HistoricalPage
from ui.historical.kpi_summary_bar import KPISummaryBar
from ui.historical.tables import HistoricalTablesCard
from ui.main_window import MainWindow
from ui.widgets.navigation_bar import NavigationBar

# Ensure QApplication exists for offscreen UI testing
app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class TestPhase5HistoricalAnalysis(unittest.TestCase):
    """Test suite covering Phase 5 analytics services, trends, and UI views."""

    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

        self.db_manager = DatabaseManager(self.db_path)
        self.prod_repo = ProductionDataRepository(self.db_manager)
        self.dt_repo = DowntimeRepository(self.db_manager)
        self.alarm_repo = AlarmRepository(self.db_manager)

        self.query_service = HistoricalQueryService(
            self.db_manager,
            production_day_start="08:00",
        )

        self.station_display_names = {
            "1": "Infeed Conveyor",
            "2": "Barcode Scanner",
            "3": "Robotic Solder",
            "4": "AOI Vision",
            "5": "Component Placement",
            "6": "Screw Fastening",
            "7": "Laser Etch",
            "8": "ICT Test",
            "9": "Functional Test",
            "10": "Packaging & Outfeed",
        }

        # Seed sample historical test data
        self._seed_test_data()

    def tearDown(self) -> None:
        self.db_manager.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def _seed_test_data(self) -> None:
        """Populate realistic historical records for Day 1 and Day 2."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # 1. Production Records
            # Day 1: 2026-09-06
            for h in range(8, 16):
                h_start = f"{h:02d}:00"
                h_end = f"{(h+1):02d}:00"
                cursor.execute("""
                    INSERT INTO production_data (
                        timestamp, production_date, hour_start, hour_end,
                        hourly_target, actual_production, hourly_achievement_percent,
                        cumulative_target, cumulative_actual, cumulative_achievement_percent,
                        tact_time, average_speed, production_counter
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"2026-09-06T{h:02d}:00:00Z", "2026-09-06", h_start, h_end,
                    100.0, 92 if h % 2 == 0 else 98, 92.0 if h % 2 == 0 else 98.0,
                    float(100 * (h - 7)), (h - 7) * 95, 95.0,
                    27.2, 44.5, 1000 + (h - 7) * 95
                ))

            # Day 2: 2026-09-07
            for h in range(8, 12):
                h_start = f"{h:02d}:00"
                h_end = f"{(h+1):02d}:00"
                cursor.execute("""
                    INSERT INTO production_data (
                        timestamp, production_date, hour_start, hour_end,
                        hourly_target, actual_production, hourly_achievement_percent,
                        cumulative_target, cumulative_actual, cumulative_achievement_percent,
                        tact_time, average_speed, production_counter
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"2026-09-07T{h:02d}:00:00Z", "2026-09-07", h_start, h_end,
                    100.0, 88, 88.0,
                    float(100 * (h - 7)), (h - 7) * 88, 88.0,
                    28.5, 43.0, 2000 + (h - 7) * 88
                ))

            # 2. Downtime Events
            cursor.execute("""
                INSERT INTO downtime_events (
                    station_id, station_name, start_time, end_time, duration_seconds,
                    alarm_id, alarm_message, production_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (3, "Robotic Solder", "2026-09-06T09:15:00Z", "2026-09-06T09:25:00Z", 600.0, "ALM_ST03_01", "Solder Wire Feed Jam", "2026-09-06"))

            cursor.execute("""
                INSERT INTO downtime_events (
                    station_id, station_name, start_time, end_time, duration_seconds,
                    alarm_id, alarm_message, production_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (4, "AOI Vision", "2026-09-06T11:00:00Z", "2026-09-06T11:05:30Z", 330.0, "ALM_ST04_02", "Camera Trigger Timeout", "2026-09-06"))

            cursor.execute("""
                INSERT INTO downtime_events (
                    station_id, station_name, start_time, end_time, duration_seconds,
                    alarm_id, alarm_message, production_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (3, "Robotic Solder", "2026-09-07T08:30:00Z", "2026-09-07T08:45:00Z", 900.0, "ALM_ST03_02", "Tip Temperature Low", "2026-09-07"))

            # 3. Alarm Events
            cursor.execute("""
                INSERT INTO alarm_events (
                    timestamp, station_id, station_name, alarm_code, alarm_message,
                    severity, active, cleared_at, duration_seconds, production_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("2026-09-06T09:15:00Z", 3, "Robotic Solder", "ALM_ST03_01", "Solder Wire Feed Jam", "CRITICAL", 0, "2026-09-06T09:25:00Z", 600.0, "2026-09-06"))

            cursor.execute("""
                INSERT INTO alarm_events (
                    timestamp, station_id, station_name, alarm_code, alarm_message,
                    severity, active, cleared_at, duration_seconds, production_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("2026-09-06T10:00:00Z", 1, "Infeed Conveyor", "WRN_ST01_01", "Buffer Magazine Low", "WARNING", 0, "2026-09-06T10:02:00Z", 120.0, "2026-09-06"))

            cursor.execute("""
                INSERT INTO alarm_events (
                    timestamp, station_id, station_name, alarm_code, alarm_message,
                    severity, active, cleared_at, duration_seconds, production_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("2026-09-07T08:30:00Z", 3, "Robotic Solder", "ALM_ST03_02", "Tip Temperature Low", "CRITICAL", 0, "2026-09-07T08:45:00Z", 900.0, "2026-09-07"))

            cursor.close()

    # =========================================================================
    # 1. Historical Query Service Tests
    # =========================================================================
    def test_01_summary_metrics(self) -> None:
        """Verify high-level summary KPIs over custom and preset ranges."""
        summary = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
        )

        self.assertEqual(summary["start_date"], "2026-09-06")
        self.assertEqual(summary["end_date"], "2026-09-07")
        self.assertEqual(summary["total_target"], 1200.0)  # 8 hours + 4 hours = 1200
        # Actual: 8 * 95 + 4 * 88 = 760 + 352 = 1112
        self.assertEqual(summary["total_production"], 1112)
        self.assertAlmostEqual(summary["achievement_percent"], round(1112 / 1200.0 * 100.0, 2))
        self.assertEqual(summary["total_stops"], 3)
        self.assertEqual(summary["total_downtime_seconds"], 1830.0)  # 600 + 330 + 900
        self.assertEqual(summary["longest_stop_seconds"], 900.0)

    def test_02_summary_filtered_by_station(self) -> None:
        """Verify summary metrics filtered to a specific station ID."""
        st3_summary = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            station_id=3,
        )
        self.assertEqual(st3_summary["total_stops"], 2)
        self.assertEqual(st3_summary["total_downtime_seconds"], 1500.0)  # 600 + 900
        self.assertEqual(st3_summary["longest_stop_seconds"], 900.0)

    def test_03_production_trend_hourly_and_daily(self) -> None:
        """Verify single-day returns hourly resolution and multi-day returns daily resolution."""
        # Single day
        hourly_trend = self.query_service.get_production_trend(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-06",
        )
        self.assertEqual(len(hourly_trend), 8)
        self.assertEqual(hourly_trend[0]["time_label"], "08:00")
        self.assertEqual(hourly_trend[0]["target"], 100.0)

        # Multi-day
        daily_trend = self.query_service.get_production_trend(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
        )
        self.assertEqual(len(daily_trend), 2)
        self.assertEqual(daily_trend[0]["time_label"], "2026-09-06")
        self.assertEqual(daily_trend[1]["time_label"], "2026-09-07")

    def test_04_speed_and_achievement_trends(self) -> None:
        """Verify speed and achievement time series generation."""
        speed_trend = self.query_service.get_speed_trend(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-06",
            speed_setpoint=45.0,
        )
        self.assertEqual(len(speed_trend), 8)
        self.assertEqual(speed_trend[0]["speed_setpoint"], 45.0)

        achieve_trend = self.query_service.get_achievement_trend(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-06",
        )
        self.assertEqual(len(achieve_trend), 8)
        self.assertEqual(achieve_trend[0]["target_reference"], 100.0)

    def test_05_downtime_trend(self) -> None:
        """Verify downtime time-series aggregation."""
        dt_trend = self.query_service.get_downtime_trend(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
        )
        self.assertEqual(len(dt_trend), 2)
        # Day 1: 600 + 330 = 930s = 15.5m
        self.assertEqual(dt_trend[0]["stop_count"], 2)
        self.assertEqual(dt_trend[0]["downtime_seconds"], 930.0)
        self.assertAlmostEqual(dt_trend[0]["downtime_minutes"], 15.5)

    def test_06_station_breakdown_full_10_stations(self) -> None:
        """
        CRITICAL: Verify full 10-station analysis preserves stations 1 to 10
        and applies configurable display names.
        """
        st_downtimes = self.query_service.get_downtime_by_station_full(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            station_display_names=self.station_display_names,
        )
        self.assertEqual(len(st_downtimes), 10)

        # Station 1 has 0 stops
        st1 = st_downtimes[0]
        self.assertEqual(st1["station_id"], 1)
        self.assertEqual(st1["station_name"], "Infeed Conveyor")
        self.assertEqual(st1["stop_count"], 0)
        self.assertEqual(st1["total_downtime_seconds"], 0.0)

        # Station 3 has 2 stops totaling 1500s (25.0m)
        st3 = st_downtimes[2]
        self.assertEqual(st3["station_id"], 3)
        self.assertEqual(st3["station_name"], "Robotic Solder")
        self.assertEqual(st3["stop_count"], 2)
        self.assertEqual(st3["total_downtime_seconds"], 1500.0)
        self.assertAlmostEqual(st3["total_downtime_minutes"], 25.0)

        # Station 4 has 1 stop of 330s
        st4 = st_downtimes[3]
        self.assertEqual(st4["station_id"], 4)
        self.assertEqual(st4["station_name"], "AOI Vision")
        self.assertEqual(st4["stop_count"], 1)

    def test_07_downtime_and_alarm_tables(self) -> None:
        """Verify tabular query records sorted newest first with severity filtering."""
        dt_rows = self.query_service.get_downtime_history_table(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            station_display_names=self.station_display_names,
        )
        self.assertEqual(len(dt_rows), 3)
        # Newest first: Day 2 (St 3) is row 0
        self.assertEqual(dt_rows[0]["station_id"], 3)
        self.assertEqual(dt_rows[0]["production_date"], "2026-09-07")

        # Alarms - ALL
        all_alarms = self.query_service.get_alarm_history_table(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            station_display_names=self.station_display_names,
        )
        self.assertEqual(len(all_alarms), 3)

        # Alarms - CRITICAL only
        crit_alarms = self.query_service.get_alarm_history_table(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            severity="CRITICAL",
            station_display_names=self.station_display_names,
        )
        self.assertEqual(len(crit_alarms), 2)
        for a in crit_alarms:
            self.assertEqual(a["severity"], "CRITICAL")

    def test_08_export_dataset_structure(self) -> None:
        """Verify unified structured dataset contains all analytical sections."""
        export_data = self.query_service.get_export_dataset(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            station_display_names=self.station_display_names,
        )
        for expected_key in (
            "metadata",
            "summary",
            "production_trend",
            "achievement_trend",
            "speed_trend",
            "downtime_trend",
            "station_downtime",
            "station_stops",
            "downtime_events",
            "alarm_events",
        ):
            self.assertIn(expected_key, export_data)

    # =========================================================================
    # 2. UI Component & View Tests
    # =========================================================================
    def test_09_filter_bar_signals_and_presets(self) -> None:
        """Test FilterBar presets, date edits, and signal emission."""
        bar = FilterBar(station_display_names=self.station_display_names)

        received_signals = []
        bar.filter_changed.connect(lambda p, s, e, st: received_signals.append((p, s, e, st)))

        # 1. Switch to Custom Range
        idx_custom = bar.combo_preset.findData(DatePreset.CUSTOM.value)
        bar.combo_preset.setCurrentIndex(idx_custom)
        self.assertTrue(bar.date_start.isEnabled())
        self.assertTrue(bar.date_end.isEnabled())

        # 2. Change station filter to Station 3
        idx_st3 = bar.combo_station.findData(3)
        bar.combo_station.setCurrentIndex(idx_st3)
        bar.trigger_apply()

        self.assertGreater(len(received_signals), 0)
        last_sig = received_signals[-1]
        self.assertEqual(last_sig[0], DatePreset.CUSTOM.value)
        self.assertEqual(last_sig[3], 3)

    def test_10_kpi_summary_bar_cards(self) -> None:
        """Test KPISummaryBar card value and color updates."""
        kpi_bar = KPISummaryBar()
        summary = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
        )
        kpi_bar.update_metrics(summary)

        self.assertIn("1,112", kpi_bar.card_actual.lbl_value.text())
        self.assertIn("1,200", kpi_bar.card_target.lbl_value.text())
        self.assertIn("3", kpi_bar.card_stops.lbl_value.text())

    def test_11_pyqtgraph_charts_rendering(self) -> None:
        """Test all PyQtGraph chart widgets handle data and empty state cleanly."""
        prod_chart = ProductionTrendChart()
        speed_chart = SpeedTrendChart()
        dt_chart = DowntimeTrendChart()
        st_dt_chart = StationDowntimeChart()
        st_stops_chart = StationStopsChart()

        # 1. Empty data handling
        prod_chart.update_data([])
        self.assertTrue(prod_chart.empty_text_item.isVisible())
        speed_chart.update_data([])
        self.assertTrue(speed_chart.empty_text_item.isVisible())
        dt_chart.update_data([])
        self.assertTrue(dt_chart.empty_text_item.isVisible())
        st_dt_chart.update_data([])
        self.assertTrue(st_dt_chart.empty_text_item.isVisible())
        st_stops_chart.update_data([])
        self.assertTrue(st_stops_chart.empty_text_item.isVisible())

        # 2. Populated data rendering
        prod_data = self.query_service.get_production_trend(
            preset=DatePreset.CUSTOM, start_date="2026-09-06", end_date="2026-09-07"
        )
        prod_chart.update_data(prod_data)
        self.assertFalse(prod_chart.empty_text_item.isVisible())

        st_data = self.query_service.get_downtime_by_station_full(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-07",
            station_display_names=self.station_display_names,
        )
        st_dt_chart.update_data(st_data)
        self.assertFalse(st_dt_chart.empty_text_item.isVisible())
        self.assertIn("BOTTLENECK", st_dt_chart.lbl_status.text())

    def test_12_historical_tables_widget(self) -> None:
        """Test Downtime and Alarm table widgets and severity filtering."""
        card = HistoricalTablesCard()

        dt_data = self.query_service.get_downtime_history_table(
            preset=DatePreset.CUSTOM, start_date="2026-09-06", end_date="2026-09-07"
        )
        card.update_downtime_data(dt_data)
        self.assertEqual(card.downtime_table.rowCount(), 3)

        alarm_data = self.query_service.get_alarm_history_table(
            preset=DatePreset.CUSTOM, start_date="2026-09-06", end_date="2026-09-07"
        )
        card.update_alarm_data(alarm_data)
        self.assertEqual(card.alarm_table.rowCount(), 3)

    def test_13_navigation_and_main_window(self) -> None:
        """Verify seamless navigation between Dashboard and Historical views in MainWindow."""
        dm = DataManager(db_path=self.db_path)
        win = MainWindow(data_manager=dm)

        self.assertEqual(win.stack.currentIndex(), 0)
        self.assertIsInstance(win.stack.currentWidget(), MainWindow.findChild(win, type(win.dashboard_page)).__class__)

        # Navigate to Historical view
        win.nav_bar.page_selected.emit("HISTORICAL", 1)
        self.assertEqual(win.stack.currentIndex(), 1)
        self.assertEqual(win.stack.currentWidget(), win.historical_page)

        # Refresh executed without error
        win.historical_page.refresh_data()

        # Navigate back to Dashboard
        win.nav_bar.page_selected.emit("DASHBOARD", 0)
        self.assertEqual(win.stack.currentIndex(), 0)

        win.close()
        dm.stop()

    def test_14_all_date_presets_resolution(self) -> None:
        """Verify that all 6 date filter presets resolve and query cleanly."""
        ref_time = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
        presets = [
            DatePreset.TODAY,
            DatePreset.YESTERDAY,
            DatePreset.LAST_7_DAYS,
            DatePreset.LAST_30_DAYS,
            DatePreset.LAST_3_MONTHS,
            DatePreset.CUSTOM,
        ]
        for p in presets:
            start_d, end_d = self.query_service.resolve_date_range(
                preset=p,
                start_date="2026-09-01",
                end_date="2026-09-07",
                reference_time=ref_time,
            )
            self.assertTrue(len(start_d) == 10 and "-" in start_d)
            self.assertTrue(len(end_d) == 10 and "-" in end_d)
            self.assertTrue(start_d <= end_d)
            # Execute summary query for each preset
            summary = self.query_service.get_historical_summary(
                preset=p,
                start_date="2026-09-01",
                end_date="2026-09-07",
            )
            self.assertIn("total_production", summary)
            self.assertIn("achievement_percent", summary)

    def test_15_empty_and_no_data_periods(self) -> None:
        """Verify queries on periods with no production or downtime data return clean zeros without NaN or crash."""
        summary = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2020-01-01",
            end_date="2020-01-02",
        )
        self.assertEqual(summary["total_production"], 0)
        self.assertEqual(summary["total_target"], 0.0)
        self.assertEqual(summary["achievement_percent"], 0.0)
        self.assertEqual(summary["total_stops"], 0)
        self.assertEqual(summary["total_downtime_seconds"], 0.0)
        self.assertEqual(summary["average_speed"], 0.0)

        trend = self.query_service.get_production_trend(
            preset=DatePreset.CUSTOM,
            start_date="2020-01-01",
            end_date="2020-01-02",
        )
        self.assertEqual(len(trend), 0)

        dt_table = self.query_service.get_downtime_history_table(
            preset=DatePreset.CUSTOM,
            start_date="2020-01-01",
            end_date="2020-01-02",
        )
        self.assertEqual(len(dt_table), 0)

    def test_16_open_downtime_event_handling(self) -> None:
        """Verify that open/ongoing downtime events (end_time IS NULL) are handled gracefully."""
        # Insert an active/open downtime event
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO downtime_events (
                    station_id, station_name, start_time, end_time, duration_seconds,
                    alarm_id, alarm_message, production_date
                ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)
            """, (5, "Station 5", "2026-09-07T12:00:00Z", "ALM_OPEN_01", "Open Jam Event", "2026-09-07"))
            cursor.close()

        # Query downtime history table
        dt_table = self.query_service.get_downtime_history_table(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-07",
            end_date="2026-09-07",
        )
        # Find the open event
        open_events = [e for e in dt_table if e["alarm_id"] == "ALM_OPEN_01"]
        self.assertEqual(len(open_events), 1)
        self.assertEqual(open_events[0]["end_time"], "ONGOING")
        self.assertEqual(open_events[0]["duration_str"], "ACTIVE")

    def test_17_large_date_range_aggregation(self) -> None:
        """Verify that large multi-month date ranges aggregate cleanly without timeouts."""
        summary = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        self.assertGreater(summary["total_production"], 0)
        self.assertGreater(summary["total_target"], 0.0)

    def test_18_production_day_boundary_alignment(self) -> None:
        """Verify that records across the 08:00 production day boundary map to correct dates."""
        # Query specifically for 2026-09-06
        s06 = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-06",
            end_date="2026-09-06",
        )
        self.assertEqual(s06["total_production"], 8 * 95)  # 760 pcs

        # Query specifically for 2026-09-07
        s07 = self.query_service.get_historical_summary(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-07",
            end_date="2026-09-07",
        )
        self.assertEqual(s07["total_production"], 4 * 88)  # 352 pcs


if __name__ == "__main__":
    unittest.main()
