"""
Phase 4.1 Stabilization & Production Readiness Tests
Verifies:
1. Production day boundary calculations (core.production_day).
2. DataManager driver instantiation logic (simulation vs real Ethernet driver).
3. Counter reset, rollover, and negative prevention in KPIEngine.
4. Disconnect resilience (no false downtime, no false counter accumulation).
5. Database startup hydration of completed production hours.
6. EthernetPLCDriver connection and frame handling.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.data_manager import DataManager
from core.production_day import (
    get_production_date,
    get_production_day_window,
    parse_time_string,
)
from database.database_manager import DatabaseManager
from database.repositories import ProductionDataRepository
from kpi.kpi_engine import KPIEngine
from kpi.models import LineStatus
from kpi.tact_time import SpeedScalingConfig
from plc.base_driver import BasePLCDriver, PLCConnectionError
from plc.ethernet_driver import EthernetPLCDriver
from plc.plc_data import ConnectionState, NormalizedPLCData
from plc.simulated_driver import SimulatedPLCDriver


class TestProductionDayBoundaries(unittest.TestCase):
    """Test 07:59 vs 08:00 and all boundary conditions for industrial production day."""

    def test_eight_am_shift_boundaries(self) -> None:
        day_start = "08:00"

        # 07:59:59 on Sep 7 belongs to previous production day Sep 6
        dt_pre = datetime(2026, 9, 7, 7, 59, 59)
        self.assertEqual(get_production_date(dt_pre, day_start), "2026-09-06")

        # 08:00:00 on Sep 7 belongs to Sep 7
        dt_start = datetime(2026, 9, 7, 8, 0, 0)
        self.assertEqual(get_production_date(dt_start, day_start), "2026-09-07")

        # 23:59:59 on Sep 7 belongs to Sep 7
        dt_night = datetime(2026, 9, 7, 23, 59, 59)
        self.assertEqual(get_production_date(dt_night, day_start), "2026-09-07")

        # 00:00:01 on Sep 8 belongs to Sep 7
        dt_post_midnight = datetime(2026, 9, 8, 0, 0, 1)
        self.assertEqual(get_production_date(dt_post_midnight, day_start), "2026-09-07")

        # 07:59:59 on Sep 8 belongs to Sep 7
        dt_pre_next = datetime(2026, 9, 8, 7, 59, 59)
        self.assertEqual(get_production_date(dt_pre_next, day_start), "2026-09-07")

        # 08:00:00 on Sep 8 belongs to Sep 8
        dt_start_next = datetime(2026, 9, 8, 8, 0, 0)
        self.assertEqual(get_production_date(dt_start_next, day_start), "2026-09-08")

    def test_midnight_shift_start(self) -> None:
        day_start = "00:00"
        dt1 = datetime(2026, 9, 7, 0, 0, 0)
        self.assertEqual(get_production_date(dt1, day_start), "2026-09-07")

        dt2 = datetime(2026, 9, 7, 23, 59, 59)
        self.assertEqual(get_production_date(dt2, day_start), "2026-09-07")

    def test_production_day_window(self) -> None:
        start_dt, end_dt = get_production_day_window("2026-09-07", "08:00")
        self.assertEqual(start_dt, datetime(2026, 9, 7, 8, 0, 0))
        self.assertEqual(end_dt.date(), datetime(2026, 9, 8).date())
        self.assertEqual(end_dt.hour, 7)
        self.assertEqual(end_dt.minute, 59)


class TestDataManagerDriverSelection(unittest.TestCase):
    """Test DataManager driver instantiation logic."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_simulation_mode_uses_simulated_driver(self) -> None:
        """When simulation_mode is True, SimulatedPLCDriver must be used."""
        dm = DataManager(
            settings_path="config/settings.json",
            db_path=self.temp_db.name,
            simulation_mode=True,
        )
        self.assertTrue(dm.simulation_mode)
        self.assertIsInstance(dm.driver, SimulatedPLCDriver)

    def test_real_plc_mode_uses_ethernet_driver(self) -> None:
        """When simulation_mode is False, EthernetPLCDriver must be instantiated, NOT SimulatedPLCDriver."""
        dm = DataManager(
            settings_path="config/settings.json",
            db_path=self.temp_db.name,
            simulation_mode=False,
        )
        self.assertFalse(dm.simulation_mode)
        self.assertIsInstance(dm.driver, EthernetPLCDriver)
        self.assertNotIsInstance(dm.driver, SimulatedPLCDriver)

    def test_custom_driver_override(self) -> None:
        """User-provided custom driver takes precedence."""
        mock_driver = MagicMock(spec=BasePLCDriver)
        dm = DataManager(
            settings_path="config/settings.json",
            db_path=self.temp_db.name,
            custom_driver=mock_driver,
        )
        self.assertEqual(dm.driver, mock_driver)


class TestKPIEngineCounterRollover(unittest.TestCase):
    """Test counter increment, rollover, and reset handling in KPIEngine."""

    def setUp(self) -> None:
        speed_cfg = SpeedScalingConfig("D450", 1.0, "m/min", 0.75)
        self.engine = KPIEngine(
            assembly_line_name="Test Line",
            station_display_names={},
            production_day_start="08:00",
            target_production_rate=100.0,
            speed_scaling=speed_cfg,
        )

    def test_normal_increment(self) -> None:
        self.assertEqual(self.engine.calculate_counter_delta(100, 105), 5)
        self.assertEqual(self.engine.calculate_counter_delta(100, 100), 0)

    def test_sixteen_bit_rollover(self) -> None:
        # 65530 -> 10: 5 before rollover + 10 after + 1 = 16
        delta = self.engine.calculate_counter_delta(65530, 10)
        self.assertEqual(delta, 16)

    def test_fifteen_bit_signed_rollover(self) -> None:
        # 32760 -> 5: 7 before rollover + 5 after + 1 = 13
        delta = self.engine.calculate_counter_delta(32760, 5)
        self.assertEqual(delta, 13)

    def test_four_digit_decimal_rollover(self) -> None:
        # 9995 -> 5: 4 before rollover + 5 after + 1 = 10
        delta = self.engine.calculate_counter_delta(9995, 5)
        self.assertEqual(delta, 10)

    def test_counter_reset_to_zero(self) -> None:
        # Shift reset back to 0
        delta = self.engine.calculate_counter_delta(500, 0)
        self.assertEqual(delta, 0)

    def test_counter_reset_with_parts(self) -> None:
        # Reset and produced 8 parts since reset
        delta = self.engine.calculate_counter_delta(500, 8)
        self.assertEqual(delta, 8)

    def test_negative_production_never_returned(self) -> None:
        delta = self.engine.calculate_counter_delta(1000, -5)
        self.assertGreaterEqual(delta, 0)


class TestDisconnectResilience(unittest.TestCase):
    """Test that disconnected PLC does not record machine stops or false production."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.dm = DataManager(
            settings_path="config/settings.json",
            db_path=self.temp_db.name,
            simulation_mode=True,
        )

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_disconnected_data_does_not_record_downtime(self) -> None:
        """Station bits marked False when connection is LOST must NOT create downtime events."""
        # Simulated disconnected packet with all stations offline
        disconnected_data = NormalizedPLCData(
            timestamp=datetime.now(timezone.utc).isoformat(),
            connected=False,
            connection_state=ConnectionState.DISCONNECTED,
            speed=0.0,
            speed_setpoint=0.0,
            production_counter=0,
            daily_target=1000,
            stations={f"station_{i}": False for i in range(1, 11)},
            error_message="Cable unplugged",
        )

        self.dm._on_plc_data_received(disconnected_data)

        # Verify no open or recorded downtime events
        active_stops = self.dm.downtime_manager.get_active_downtime_events()
        self.assertEqual(len(active_stops), 0)


class TestStartupHydration(unittest.TestCase):
    """Test that restarting the application retains today's completed production hours."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_manager = DatabaseManager(self.temp_db.name)
        self.prod_repo = ProductionDataRepository(self.db_manager)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_hydrate_from_database(self) -> None:
        from core.production_day import get_production_date
        from database.models import ProductionDataRecord
        today_str = get_production_date("08:00")

        # Insert 2 completed hours into database
        rec1 = ProductionDataRecord(
            id=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            production_date=today_str,
            hour_start="08:00",
            hour_end="09:00",
            hourly_target=100.0,
            actual_production=95,
            hourly_achievement_percent=95.0,
            cumulative_target=100.0,
            cumulative_actual=95,
            cumulative_achievement_percent=95.0,
            tact_time=1.05,
            average_speed=43.0,
        )
        rec2 = ProductionDataRecord(
            id=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            production_date=today_str,
            hour_start="09:00",
            hour_end="10:00",
            hourly_target=100.0,
            actual_production=102,
            hourly_achievement_percent=102.0,
            cumulative_target=200.0,
            cumulative_actual=197,
            cumulative_achievement_percent=98.5,
            tact_time=1.04,
            average_speed=44.0,
        )
        self.prod_repo.upsert(rec1)
        self.prod_repo.upsert(rec2)

        # Initialize fresh DataManager
        dm = DataManager(
            settings_path="config/settings.json",
            db_path=self.temp_db.name,
            simulation_mode=True,
        )

        # Verify KPI engine was hydrated with the 2 completed hours
        completed = dm.kpi_engine.get_completed_hours()
        self.assertEqual(len(completed), 2)
        self.assertEqual(completed[0].actual_production, 95)
        self.assertEqual(completed[1].actual_production, 102)


class TestEthernetDriver(unittest.TestCase):
    """Test EthernetPLCDriver connection and frame building."""

    def test_unreachable_plc_connection_error(self) -> None:
        """Connecting to an unreachable IP raises PLCConnectionError/PLCConnectionTimeoutError."""
        driver = EthernetPLCDriver(host="192.0.2.1", port=502, timeout=0.2)
        with self.assertRaises(PLCConnectionError):
            driver.connect()
        self.assertFalse(driver.is_connected)

    def test_read_without_connection_raises(self) -> None:
        driver = EthernetPLCDriver(host="127.0.0.1", port=502)
        with self.assertRaises(PLCConnectionError):
            driver.read_registers(["D450"])
        with self.assertRaises(PLCConnectionError):
            driver.read_bits(["M550"])


if __name__ == "__main__":
    unittest.main()
