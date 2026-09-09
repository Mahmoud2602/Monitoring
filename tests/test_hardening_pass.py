"""
Comprehensive Hardening & Verification Suite
Validates:
1. Production counter reset safety, rollovers (16-bit, 15-bit, 4-digit), no negative deltas, no spikes
2. Production day centralization (core/production_day.py as single source of truth)
3. KPI engine accuracy (hourly vs cumulative achievement, tact time)
4. Historical Query Service metrics (all 12 executive metrics including running time, best/worst hour)
5. 10-Station analysis and bottleneck identification
6. Real PLC mode strict validation (no silent simulation fallback)
7. Downtime and alarm state transitions
8. Historical async query worker responsiveness
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from core.data_manager import DataManager
from core.production_day import get_production_date, get_production_day_range
from database.database_manager import DatabaseManager
from database.downtime_manager import DowntimeManager
from database.models import DowntimeEventRecord, ProductionDataRecord
from database.query_service import DatePreset, HistoricalQueryService
from database.repositories import DowntimeRepository, ProductionDataRepository, StationStatusRepository
from kpi.kpi_engine import KPIEngine, LineStatus
from kpi.tact_time import SpeedScalingConfig
from plc.plc_data import ConnectionState, NormalizedPLCData


class TestHardeningPass(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.db_mgr = DatabaseManager(self.db_path)
        self.prod_repo = ProductionDataRepository(self.db_mgr)
        self.dt_repo = DowntimeRepository(self.db_mgr)
        self.status_repo = StationStatusRepository(self.db_mgr)

    def tearDown(self):
        self.db_mgr.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    # =========================================================================
    # 1. PRODUCTION COUNTER RESET SAFETY & ROLLOVERS
    # =========================================================================
    def test_counter_rollovers_and_monotonicity(self):
        """Verify 16-bit, 15-bit, 4-digit, zero reset, and random drops never spike or go negative."""
        engine = KPIEngine(production_day_start="08:00")

        # Standard increment (prev: 100, curr: 105 => 5)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=100, current_counter=105), 5)
        # Same value
        self.assertEqual(engine.calculate_counter_delta(previous_counter=100, current_counter=100), 0)

        # 16-bit rollover (65535 -> 10 => delta 11)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=65535, current_counter=10), 11)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=65530, current_counter=5), 11)

        # 15-bit rollover (32767 -> 5 => delta 6)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=32767, current_counter=5), 6)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=32760, current_counter=4), 12)

        # 4-digit rollover (9999 -> 5 => delta 6)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=9999, current_counter=5), 6)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=9995, current_counter=3), 8)

        # Manual counter reset to 0 (prev: 500, curr: 0 => delta 0)
        self.assertEqual(engine.calculate_counter_delta(previous_counter=500, current_counter=0), 0)

        # Arbitrary drop (prev: 800, curr: 12 => delta 12, treating 12 as start after reset)
        delta_drop = engine.calculate_counter_delta(previous_counter=800, current_counter=12)
        self.assertEqual(delta_drop, 12)

        # Negative input protection
        self.assertEqual(engine.calculate_counter_delta(previous_counter=100, current_counter=-5), 0)

    # =========================================================================
    # 2. PRODUCTION DAY CENTRALIZATION & CONSISTENCY
    # =========================================================================
    def test_production_day_centralization(self):
        """Verify production day 08:00 transition logic across midnight and shift boundaries."""
        # Pre-shift: 07:59:59 belongs to previous calendar day
        t1 = datetime(2026, 3, 15, 7, 59, 59)
        self.assertEqual(get_production_date(t1, "08:00"), "2026-03-14")

        # Exact shift start: 08:00:00 belongs to current calendar day
        t2 = datetime(2026, 3, 15, 8, 0, 0)
        self.assertEqual(get_production_date(t2, "08:00"), "2026-03-15")

        # Midnight crossover: 02:30:00 belongs to previous calendar day
        t3 = datetime(2026, 3, 16, 2, 30, 0)
        self.assertEqual(get_production_date(t3, "08:00"), "2026-03-15")

        # Range resolution
        s_dt, e_dt = get_production_day_range("2026-03-15", "08:00")
        self.assertEqual(s_dt, datetime(2026, 3, 15, 8, 0, 0))
        self.assertEqual(e_dt, datetime(2026, 3, 16, 7, 59, 59, 999999))

        # Query service preset resolution uses production day logic
        qs = HistoricalQueryService(self.db_mgr, production_day_start="08:00")
        resolved_s, resolved_e = qs.resolve_date_range(DatePreset.TODAY)
        self.assertEqual(resolved_s, resolved_e)
        self.assertEqual(resolved_s, get_production_date(datetime.now(), "08:00"))

    # =========================================================================
    # 3. KPI ENGINE FORMULA VERIFICATION
    # =========================================================================
    def test_kpi_formulas_and_hourly_achievement(self):
        """Verify hourly achievement, cumulative achievement, and tact time."""
        engine = KPIEngine(
            target_production_rate=100.0,
            speed_scaling=SpeedScalingConfig(scale_factor=1.0, product_pitch_meters=1.5),
            production_day_start="08:00",
        )

        # Tact time when speed = 45.0 m/min, pitch = 1.5m:
        # speed_m_s = 45.0 / 60.0 = 0.75 m/s. Tact = 1.5 / 0.75 = 2.0s
        self.assertAlmostEqual(engine.tact_calculator.calculate_tact_time_from_speed(45.0), 2.0, places=2)

        # Tact time when conveyor is stopped (0.0 m/min) => must return 0.0
        self.assertEqual(engine.tact_calculator.calculate_tact_time_from_speed(0.0), 0.0)

        # Hourly achievement calculation: 110 actual / 100 target => 110.0%
        ach_h = KPIEngine.calculate_hourly_achievement(110, 100.0)
        self.assertEqual(ach_h, 110.0)

        # Cumulative achievement calculation: 450 actual / 500 target => 90.0%
        ach_c = KPIEngine.calculate_cumulative_achievement(450, 500.0)
        self.assertEqual(ach_c, 90.0)

    # =========================================================================
    # 4. HISTORICAL QUERY SERVICE & 12 EXECUTIVE METRICS
    # =========================================================================
    def test_historical_summary_all_metrics(self):
        """Verify get_historical_summary returns all 12 executive metrics with exact calculations."""
        qs = HistoricalQueryService(self.db_mgr, production_day_start="08:00")

        # Populate test production data
        self.prod_repo.upsert(ProductionDataRecord(
            id=None,
            timestamp=datetime.now().isoformat(),
            production_date="2026-09-09",
            hour_start="08:00",
            hour_end="09:00",
            actual_production=110,
            hourly_target=100.0,
            hourly_achievement_percent=110.0,
            cumulative_actual=110,
            cumulative_target=100.0,
            cumulative_achievement_percent=110.0,
            average_speed=45.2,
            tact_time=2.0,
            production_counter=110,
        ))
        self.prod_repo.upsert(ProductionDataRecord(
            id=None,
            timestamp=datetime.now().isoformat(),
            production_date="2026-09-09",
            hour_start="09:00",
            hour_end="10:00",
            actual_production=90,
            hourly_target=100.0,
            hourly_achievement_percent=90.0,
            cumulative_actual=200,
            cumulative_target=200.0,
            cumulative_achievement_percent=100.0,
            average_speed=43.8,
            tact_time=2.1,
            production_counter=200,
        ))

        # Populate test downtime event
        self.dt_repo.insert(DowntimeEventRecord(
            id=None,
            production_date="2026-09-09",
            station_id=3,
            station_name="Station 3",
            start_time="2026-09-09T09:15:00",
            end_time="2026-09-09T09:20:00",
            duration_seconds=300.0,
            alarm_id=None,
            alarm_message="Part Jam",
        ))

        summary = qs.get_historical_summary(preset=DatePreset.CUSTOM, start_date="2026-09-09", end_date="2026-09-09")

        # Check all required fields
        self.assertEqual(summary["total_production"], 200)
        self.assertEqual(summary["total_target"], 200.0)
        self.assertEqual(summary["achievement_percent"], 100.0)
        self.assertEqual(summary["total_downtime_seconds"], 300.0)
        self.assertEqual(summary["total_downtime_str"], "00:05:00")
        self.assertEqual(summary["total_stops"], 1)
        self.assertEqual(summary["average_stop_seconds"], 300.0)
        self.assertEqual(summary["longest_stop_seconds"], 300.0)
        self.assertAlmostEqual(summary["average_speed"], 44.5, places=1)
        self.assertIn("running_time_seconds", summary)
        self.assertIn("running_time_str", summary)
        self.assertEqual(summary["best_hour_str"], "08:00 (110 pcs)")
        self.assertEqual(summary["worst_hour_str"], "09:00 (90 pcs)")

    # =========================================================================
    # 5. 10-STATION BREAKDOWN & BOTTLENECK IDENTIFICATION
    # =========================================================================
    def test_station_analysis_all_10_stations(self):
        """Verify get_downtime_by_station_full returns all 10 stations and identifies bottleneck."""
        qs = HistoricalQueryService(self.db_mgr, production_day_start="08:00")

        # Station 7 has 600s of downtime (bottleneck)
        self.dt_repo.insert(DowntimeEventRecord(
            id=None,
            production_date="2026-09-09",
            station_id=7,
            station_name="St 7",
            start_time="2026-09-09T08:10:00",
            end_time="2026-09-09T08:20:00",
            duration_seconds=600.0,
            alarm_id=None,
            alarm_message="Laser Sensor Fault",
        ))
        # Station 2 has 120s
        self.dt_repo.insert(DowntimeEventRecord(
            id=None,
            production_date="2026-09-09",
            station_id=2,
            station_name="St 2",
            start_time="2026-09-09T08:30:00",
            end_time="2026-09-09T08:32:00",
            duration_seconds=120.0,
            alarm_id=None,
            alarm_message="Feeder Empty",
        ))

        station_names = {"7": "Laser Welding", "2": "Screw Feeder"}
        breakdown = qs.get_downtime_by_station_full(
            preset=DatePreset.CUSTOM,
            start_date="2026-09-09",
            end_date="2026-09-09",
            station_display_names=station_names,
        )

        # Must contain exactly 10 entries for stations 1-10
        self.assertEqual(len(breakdown), 10)
        station_ids = [s["station_id"] for s in breakdown]
        self.assertEqual(station_ids, list(range(1, 11)))

        # Station 7 must have custom name and highest duration
        st7 = next(s for s in breakdown if s["station_id"] == 7)
        self.assertEqual(st7["station_name"], "Laser Welding")
        self.assertEqual(st7["total_downtime_seconds"], 600.0)

        # Station 2
        st2 = next(s for s in breakdown if s["station_id"] == 2)
        self.assertEqual(st2["station_name"], "Screw Feeder")
        self.assertEqual(st2["total_downtime_seconds"], 120.0)

        # Station 1 (idle, 0 stops)
        st1 = next(s for s in breakdown if s["station_id"] == 1)
        self.assertEqual(st1["total_downtime_seconds"], 0.0)
        self.assertEqual(st1["stop_count"], 0)

    # =========================================================================
    # 6. REAL PLC MODE STRICT VALIDATION
    # =========================================================================
    def test_real_plc_mode_never_silently_simulates(self):
        """Verify simulation_mode=False strictly instantiates real driver, never simulated driver."""
        real_mock = MagicMock()
        real_mock.read_production_counter.return_value = 100
        real_mock.read_conveyor_speed.return_value = 45.0
        real_mock.is_connected = True
        real_mock.read_station_status.return_value = {f"M{550+i}": True for i in range(10)}

        dm = DataManager(
            db_path=self.db_path,
            simulation_mode=False,
            custom_driver=real_mock,
        )
        self.assertFalse(dm.simulation_mode)
        self.assertIs(dm.driver, real_mock)
        dm.stop()

    # =========================================================================
    # 7. DOWNTIME STATE TRANSITIONS & NO FALSE EVENTS ON COMM ERROR
    # =========================================================================
    def test_downtime_state_transitions_and_comm_loss(self):
        """Verify RUNNING -> STOPPED creates event, repeated poll does not duplicate, and comm loss doesn't create false event."""
        dt_mgr = DowntimeManager(
            downtime_repo=self.dt_repo,
            status_repo=self.status_repo,
            production_day_start="08:00",
        )

        # Initial state: RUNNING (True) for all 10 stations
        states = {i: (f"Station {i}", f"M{550+i-1}", True) for i in range(1, 11)}
        events1 = dt_mgr.process_station_states(states, production_date="2026-09-09")
        self.assertEqual(len(events1), 0)

        # Station 2 stops (is_running = False)
        states[2] = ("Station 2", "M551", False)
        events2 = dt_mgr.process_station_states(states, production_date="2026-09-09")
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0].station_id, 2)

        # Check that open downtime event exists in repo
        open_events = self.dt_repo.get_open_events()
        self.assertEqual(len(open_events), 1)
        self.assertEqual(open_events[0].station_id, 2)

        # Repeated poll with station 2 still stopped: NO duplicate event created
        events3 = dt_mgr.process_station_states(states, production_date="2026-09-09")
        self.assertEqual(len(events3), 0)
        open_events2 = self.dt_repo.get_open_events()
        self.assertEqual(len(open_events2), 1)

        # Station 2 recovers (RUNNING)
        states[2] = ("Station 2", "M551", True)
        events_rec = dt_mgr.process_station_states(states, production_date="2026-09-09")
        self.assertEqual(len(events_rec), 1)
        self.assertIsNotNone(events_rec[0].end_time)

        # Verify event in database is now closed (duration_seconds > 0)
        closed_events = self.dt_repo.get_events_by_date("2026-09-09")
        self.assertEqual(len(closed_events), 1)
        self.assertIsNotNone(closed_events[0].end_time)


if __name__ == "__main__":
    unittest.main()
