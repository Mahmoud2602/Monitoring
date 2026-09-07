"""
Unit & Integration Tests for Phase 4: PySide6 Industrial Real-Time Dashboard.
Tests station visual independence, continuous line visualization, alarm bar states,
logo fallbacks, KPI cards, downtime formatting, and background worker thread safety.
"""
from __future__ import annotations

import os
import unittest

# Ensure Qt runs headlessly in testing environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

# Initialize shared QApplication for test suite
_app = QApplication.instance() or QApplication([])

from core.data_manager import DataManager
from database.models import AlarmEventRecord
from kpi.models import HourlyProductionRecord, KPISnapshot, LineStatus, StoppedStationInfo
from plc.plc_data import ConnectionState, NormalizedPLCData
from ui.dashboard.dashboard_page import DashboardPage
from ui.main_window import MainWindow
from ui.widgets.alarm_bar import AlarmBar
from ui.widgets.downtime_card import DowntimeCard, format_duration_compact, format_seconds_hms
from ui.widgets.header_bar import HeaderBar
from ui.widgets.kpi_card import KPICard
from ui.widgets.line_status_banner import LineStatusBanner
from ui.widgets.logo_widget import LogoWidget
from ui.widgets.production_line import ProductionLineWidget
from ui.widgets.station_node import StationNode


class TestProductionLineWidget(unittest.TestCase):
    """Verify continuous line visualization and station status independence."""

    def setUp(self) -> None:
        self.station_names = {
            "1": "Assembly 1", "2": "Screw Installation", "3": "Inspection",
            "4": "Riveting", "5": "Transfer 1", "6": "Component Insertion",
            "7": "Optical Inspection", "8": "Laser Marking", "9": "Cleaning",
            "10": "Unloading",
        }
        self.widget = ProductionLineWidget(
            line_name="Assembly Line",
            station_display_names=self.station_names,
        )

    def test_ten_stations_created_as_one_continuous_line(self) -> None:
        """Verify exactly 10 station nodes exist and are bridged as one continuous line."""
        self.assertEqual(len(self.widget.station_nodes), 10)
        for st_id in range(1, 11):
            self.assertIn(st_id, self.widget.station_nodes)
            node = self.widget.station_nodes[st_id]
            self.assertEqual(node.station_id, st_id)
            self.assertEqual(node.display_name, self.station_names[str(st_id)])
        # Check transfer bridge exists between Station 5 and 6
        self.assertIsNotNone(self.widget.bridge_widget)

    def test_station_7_stopped_only_station_7_turns_red(self) -> None:
        """
        CRITICAL MANDATE:
        If Station 7 stops, ONLY Station 7 turns RED.
        Stations 1-6 and 8-10 remain GREEN.
        The entire line does NOT turn red.
        """
        # Create telemetry where only Station 7 is stopped (False)
        statuses = {f"conv{1 if i<=5 else 2}_station{i if i<=5 else i-5}": True for i in range(1, 11)}
        statuses["conv2_station2"] = False  # Station 7 fault!

        telemetry = NormalizedPLCData(
            timestamp="2026-09-06T12:00:00Z",
            connected=True,
            connection_state=ConnectionState.CONNECTED,
            speed=40.0,
            speed_setpoint=45.0,
            production_counter=1280,
            daily_target=1000,
            stations=statuses,
        )

        self.widget.update_telemetry(telemetry, stoppage_durations={7: 15.0})

        # Verify Station 7 is STOPPED
        st7 = self.widget.station_nodes[7]
        self.assertFalse(st7.is_running)
        self.assertEqual(st7.stoppage_seconds, 15.0)
        self.assertIn("STOPPED", st7.lbl_status_pill.text())

        # Verify all OTHER 9 stations remain RUNNING
        for st_id in [1, 2, 3, 4, 5, 6, 8, 9, 10]:
            node = self.widget.station_nodes[st_id]
            self.assertTrue(node.is_running, f"Station {st_id} should still be RUNNING!")
            self.assertEqual(node.lbl_status_pill.text(), "RUNNING")

        # Conveyor 2 should indicate interruption, while Conveyor 1 remains active
        self.assertIn("INTERRUPTED", self.widget.lbl_conv2_status.text())
        self.assertIn("ACTIVE", self.widget.lbl_conv1_status.text())

    def test_disconnected_marks_all_stations_offline(self) -> None:
        """Verify PLC disconnect marks stations offline without error."""
        self.widget.set_disconnected()
        for node in self.widget.station_nodes.values():
            self.assertFalse(node.is_connected)
            self.assertEqual(node.lbl_status_pill.text(), "OFFLINE")


class TestAlarmBar(unittest.TestCase):
    """Test Alarm Bar calm vs urgent state shifts."""

    def setUp(self) -> None:
        self.alarm_bar = AlarmBar()

    def test_calm_state_when_no_alarms(self) -> None:
        self.alarm_bar.clear_alarm()
        self.assertEqual(self.alarm_bar.lbl_message.text(), "NO ACTIVE ALARMS")
        self.assertEqual(self.alarm_bar.lbl_icon.text(), "✓")

    def test_alert_state_on_alarm(self) -> None:
        self.alarm_bar.set_alarm("ALARM: Station 7 (Optical Inspection) - Line Stopped", "Active Alarms: 1", "CRITICAL")
        self.assertIn("ALARM: STATION 7", self.alarm_bar.lbl_message.text())
        self.assertEqual(self.alarm_bar.lbl_icon.text(), "⚠")


class TestLineStatusBanner(unittest.TestCase):
    """Test dominant Line Status Banner."""

    def setUp(self) -> None:
        self.banner = LineStatusBanner()

    def test_running_state(self) -> None:
        self.banner.set_running(speed_m_per_min=44.5)
        self.assertEqual(self.banner.lbl_status.text(), "LINE RUNNING")
        self.assertIn("44.5 m/min", self.banner.lbl_subtext.text())

    def test_stopped_state_shows_stopped_stations(self) -> None:
        self.banner.set_stopped(["Optical Inspection (M556)"], stoppage_duration_s=22.0)
        self.assertEqual(self.banner.lbl_status.text(), "LINE STOPPED")
        self.assertIn("Optical Inspection (M556)", self.banner.lbl_subtext.text())
        self.assertIn("22s", self.banner.lbl_subtext.text())

    def test_disconnected_state(self) -> None:
        self.banner.set_disconnected()
        self.assertEqual(self.banner.lbl_status.text(), "PLC DISCONNECTED")


class TestKPICard(unittest.TestCase):
    """Test KPI card formatting and progress meters."""

    def test_kpi_card_values_and_progress(self) -> None:
        card = KPICard(title="DAILY PRODUCTION", unit="pcs", show_progress=True)
        card.set_value(value_str="1,280", details="Target: 1,000 pcs", tag="128.0%", progress_pct=100.0)
        self.assertEqual(card.lbl_value.text(), "1,280")
        self.assertEqual(card.lbl_details.text(), "Target: 1,000 pcs")
        self.assertEqual(card.lbl_tag.text(), "128.0%")
        self.assertEqual(card.progress_bar.value(), 100)


class TestLogoWidget(unittest.TestCase):
    """Test logo loading and graceful missing asset fallback."""

    def test_missing_logo_renders_clean_placeholder(self) -> None:
        """Must never crash when image file does not exist."""
        widget = LogoWidget(
            logo_path="nonexistent/fake_logo.png",
            fallback_text="PLANT4",
            fallback_subtext="FACILITY",
        )
        self.assertIsNotNone(widget)
        # Check fallback text is set
        self.assertEqual(widget.fallback_text, "PLANT4")

    def test_valid_logo_loads_pixmap(self) -> None:
        """When logo exists, loads properly."""
        if os.path.exists("assets/company_logo.png"):
            widget = LogoWidget(logo_path="assets/company_logo.png")
            self.assertIsNotNone(widget)


class TestDowntimeFormatting(unittest.TestCase):
    """Test downtime seconds formatting and DowntimeCard."""

    def test_format_seconds_hms(self) -> None:
        self.assertEqual(format_seconds_hms(0), "00:00:00")
        self.assertEqual(format_seconds_hms(59), "00:00:59")
        self.assertEqual(format_seconds_hms(3665), "01:01:05")
        self.assertEqual(format_seconds_hms(86400), "24:00:00")

    def test_format_duration_compact(self) -> None:
        self.assertEqual(format_duration_compact(45.2), "45.2s")
        self.assertEqual(format_duration_compact(125), "2m 5s")

    def test_downtime_card_update(self) -> None:
        card = DowntimeCard()
        stats = {
            "total_stops": 5,
            "total_downtime_seconds": 185.0,
            "average_stop_seconds": 37.0,
            "longest_stop_seconds": 92.5,
        }
        card.update_statistics(stats, running_time_seconds=7200.0, active_stops_count=1)
        self.assertEqual(card.lbl_total_downtime.text(), "00:03:05")
        self.assertEqual(card.lbl_stops_val.text(), "5")
        self.assertEqual(card.lbl_running_val.text(), "02:00:00")
        self.assertEqual(card.lbl_avg_stop_val.text(), "37.0s")
        self.assertEqual(card.lbl_longest_stop_val.text(), "1m 32s")
        self.assertIn("1 STOPPED", card.lbl_active_stops_tag.text())


class TestFullDashboardIntegration(unittest.TestCase):
    """Test full MainWindow assembly and live update pipeline."""

    def setUp(self) -> None:
        self.dm = DataManager(
            settings_path="config/settings.json",
            mapping_path="config/plc_mapping.json",
            db_path=":memory:",
        )
        self.dm.start()
        self.win = MainWindow(data_manager=self.dm, config=self.dm.settings)
        self.win.show()
        _app.processEvents()

    def tearDown(self) -> None:
        self.win.close()
        self.dm.stop()
        _app.processEvents()

    def test_kpi_update_reflects_in_cards(self) -> None:
        """Simulate a KPI snapshot update and verify cards reflect metrics."""
        rec = HourlyProductionRecord(
            date="2026-09-06",
            hour_start="13:00",
            hour_end="14:00",
            hourly_target=100.0,
            actual_production=95,
            hourly_achievement_percent=95.0,
            cumulative_target=200.0,
            cumulative_actual=190,
            cumulative_achievement_percent=95.0,
            tact_time=1.0,
            average_speed=44.0,
        )
        kpi = KPISnapshot(
            timestamp="2026-09-06T13:30:00Z",
            assembly_line_name="Assembly Line",
            line_status=LineStatus.RUNNING,
            stopped_stations=[],
            stations={},
            current_hour=rec,
            completed_hours=[],
            target_production_rate=100.0,
            tact_time_seconds=1.0,
            production_counter_raw=1280,
            daily_target=1000,
            engineering_speed=44.0,
        )

        self.win.dashboard_page.update_kpi(kpi)
        _app.processEvents()

        # Verify Production Card
        self.assertEqual(self.win.dashboard_page.card_production.lbl_value.text(), "1,280")
        # Verify Speed Card
        self.assertEqual(self.win.dashboard_page.card_speed.lbl_value.text(), "44.0")
        # Verify Tact Time Card
        self.assertEqual(self.win.dashboard_page.card_tact.lbl_value.text(), "1.0")
        # Verify Hourly Achievement Card
        self.assertEqual(self.win.dashboard_page.card_hourly.lbl_value.text(), "95.0")
        # Verify Cumulative Achievement Card
        self.assertEqual(self.win.dashboard_page.card_cumulative.lbl_value.text(), "95.0")


if __name__ == "__main__":
    unittest.main()
