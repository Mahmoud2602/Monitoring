"""
Industrial PLC Production Monitor - Comprehensive Unit Tests for Phase 2
Tests all 13 core requirements:
1. Hourly production calculation
2. Hourly achievement
3. Cumulative target
4. Cumulative achievement
5. Production counter increasing
6. Production counter reset
7. Tact time calculation
8. Target production rate
9. Line status
10. Stopped station detection
11. Configurable station display names
12. Configurable Assembly Line name
13. Production day start time
"""
from datetime import datetime, timezone
import unittest

from kpi.kpi_engine import KPIEngine, PHYSICAL_STATION_MAP
from kpi.models import LineStatus
from kpi.tact_time import SpeedScalingConfig, TactTimeCalculator
from plc.plc_data import ConnectionState, NormalizedPLCData


class TestKPIEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.custom_station_names = {
            1: "Assembly 1",
            2: "Screw Installation",
            3: "Inspection",
            4: "Riveting",
            5: "Transfer 1",
            6: "Component Insertion",
            7: "Optical Inspection",
            8: "Laser Marking",
            9: "Cleaning",
            10: "Unloading",
        }
        self.engine = KPIEngine(
            assembly_line_name="Automotive Line Alpha",
            station_display_names=self.custom_station_names,
            production_day_start="08:00",
            target_production_rate=100.0,
            speed_scaling=SpeedScalingConfig(
                raw_address="D450",
                scale_factor=1.0,
                engineering_unit="m/min",
                product_pitch_meters=0.75,
            ),
        )

    # -------------------------------------------------------------------------
    # Test 1: Hourly Production Calculation
    # -------------------------------------------------------------------------
    def test_01_hourly_production_calculation(self) -> None:
        """
        Verify hourly production delta calculation across hour transitions.
        Example: 08:00 -> 100, 09:00 -> 195, 10:00 -> 287.
        08:00-09:00 production = 95
        09:00-10:00 production = 92
        """
        engine = KPIEngine(target_production_rate=100.0)

        # 08:00 reading: counter = 100
        t1 = datetime(2026, 9, 6, 8, 0, 0, tzinfo=timezone.utc)
        d1 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d1.production_counter = 100
        engine.process_data(d1, override_timestamp=t1)

        # Advance within the 08:00 hour: counter reaches 195
        t2 = datetime(2026, 9, 6, 8, 59, 59, tzinfo=timezone.utc)
        d2 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d2.production_counter = 195
        snap2 = engine.process_data(d2, override_timestamp=t2)
        self.assertEqual(snap2.current_hour.actual_production, 95)

        # 09:00 transition: counter = 195, hour 08:00-09:00 is finalized
        t3 = datetime(2026, 9, 6, 9, 0, 0, tzinfo=timezone.utc)
        d3 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d3.production_counter = 195
        engine.process_data(d3, override_timestamp=t3)

        completed = engine.get_completed_hours()
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].actual_production, 95)
        self.assertEqual(completed[0].hour_start, "08:00")
        self.assertEqual(completed[0].hour_end, "09:00")

        # Advance within 09:00 hour: counter reaches 287
        t4 = datetime(2026, 9, 6, 9, 59, 59, tzinfo=timezone.utc)
        d4 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d4.production_counter = 287
        snap4 = engine.process_data(d4, override_timestamp=t4)
        self.assertEqual(snap4.current_hour.actual_production, 92)

        # 10:00 transition
        t5 = datetime(2026, 9, 6, 10, 0, 0, tzinfo=timezone.utc)
        d5 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d5.production_counter = 287
        engine.process_data(d5, override_timestamp=t5)

        completed = engine.get_completed_hours()
        self.assertEqual(len(completed), 2)
        self.assertEqual(completed[1].actual_production, 92)
        self.assertEqual(completed[1].hour_start, "09:00")
        self.assertEqual(completed[1].hour_end, "10:00")

    # -------------------------------------------------------------------------
    # Test 2: Hourly Achievement %
    # -------------------------------------------------------------------------
    def test_02_hourly_achievement(self) -> None:
        """
        Verify hourly achievement % formula: (Actual / Target) * 100.
        Example: Target = 100, Actual = 95 -> 95.0%
        Example: Target = 100, Actual = 110 -> 110.0%
        """
        achieve1 = KPIEngine.calculate_hourly_achievement(actual_production=95, target_production=100.0)
        self.assertEqual(achieve1, 95.0)

        achieve2 = KPIEngine.calculate_hourly_achievement(actual_production=110, target_production=100.0)
        self.assertEqual(achieve2, 110.0)

        # Safe division by zero
        achieve_zero = KPIEngine.calculate_hourly_achievement(actual_production=50, target_production=0.0)
        self.assertEqual(achieve_zero, 0.0)

    # -------------------------------------------------------------------------
    # Test 3: Cumulative Target
    # -------------------------------------------------------------------------
    def test_03_cumulative_target(self) -> None:
        """
        After 5 completed production hours with hourly target of 100 pcs/hour:
        Expected Cumulative Target = 500 pcs.
        """
        engine = KPIEngine(target_production_rate=100.0)
        for i in range(1, 6):
            engine.add_completed_hour_record(
                date_str="2026-09-06",
                hour_start=f"{7+i:02d}:00",
                hour_end=f"{8+i:02d}:00",
                actual_production=92,
                hourly_target=100.0,
            )

        completed = engine.get_completed_hours()
        self.assertEqual(len(completed), 5)
        # 5th hour cumulative target
        self.assertEqual(completed[4].cumulative_target, 500.0)

        metrics = engine.get_cumulative_metrics()
        self.assertEqual(metrics["cumulative_target"], 500.0)

    # -------------------------------------------------------------------------
    # Test 4: Cumulative Achievement %
    # -------------------------------------------------------------------------
    def test_04_cumulative_achievement(self) -> None:
        """
        Verify cumulative achievement %: (Cumulative Actual / Cumulative Target) * 100.
        Example from prompt:
        5 hours * 100 target = 500 pcs.
        Actual cumulative production = 460 pcs.
        Expected Cumulative Achievement = 460 / 500 * 100 = 92.0%.
        """
        engine = KPIEngine(target_production_rate=100.0)
        actuals = [95, 90, 92, 93, 90]  # Sum = 460
        for i, act in enumerate(actuals, start=1):
            engine.add_completed_hour_record(
                date_str="2026-09-06",
                hour_start=f"{7+i:02d}:00",
                hour_end=f"{8+i:02d}:00",
                actual_production=act,
                hourly_target=100.0,
            )

        completed = engine.get_completed_hours()
        record_5 = completed[4]
        self.assertEqual(record_5.cumulative_actual, 460)
        self.assertEqual(record_5.cumulative_target, 500.0)
        self.assertEqual(record_5.cumulative_achievement_percent, 92.0)

        metrics = engine.get_cumulative_metrics()
        self.assertEqual(metrics["cumulative_achievement_percent"], 92.0)

    # -------------------------------------------------------------------------
    # Test 5: Production Counter Continuously Increasing
    # -------------------------------------------------------------------------
    def test_05_production_counter_increasing(self) -> None:
        """
        Verify that monotonically increasing counter ticks accumulate accurately.
        """
        delta1 = self.engine.calculate_counter_delta(previous_counter=100, current_counter=150)
        self.assertEqual(delta1, 50)

        delta2 = self.engine.calculate_counter_delta(previous_counter=150, current_counter=220)
        self.assertEqual(delta2, 70)

    # -------------------------------------------------------------------------
    # Test 6: Production Counter Safe Reset / Rollover
    # -------------------------------------------------------------------------
    def test_06_production_counter_reset(self) -> None:
        """
        Verify safe counter reset handling:
        Previous counter = 999, Current counter = 10.
        Must NEVER calculate -989.
        Must treat as reset/rollover and produce >= 0.
        """
        prev_counter = 999
        curr_counter = 10

        safe_delta = self.engine.calculate_counter_delta(previous_counter=prev_counter, current_counter=curr_counter)
        self.assertGreaterEqual(safe_delta, 0)
        self.assertNotEqual(safe_delta, -989)
        self.assertEqual(safe_delta, 10)

        # In a real session:
        t1 = datetime(2026, 9, 6, 8, 0, 0, tzinfo=timezone.utc)
        d1 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d1.production_counter = 999
        self.engine.process_data(d1, override_timestamp=t1)

        t2 = datetime(2026, 9, 6, 8, 5, 0, tzinfo=timezone.utc)
        d2 = NormalizedPLCData.create_empty(state=ConnectionState.CONNECTED)
        d2.production_counter = 10  # Reset event
        snap2 = self.engine.process_data(d2, override_timestamp=t2)
        self.assertEqual(snap2.current_hour.actual_production, 10)

    # -------------------------------------------------------------------------
    # Test 7: Tact Time Calculation
    # -------------------------------------------------------------------------
    def test_07_tact_time_calculation(self) -> None:
        """
        Verify tact time calculation: Product Pitch / Line Speed with unit conversion.
        Pitch = 0.75 m.
        Speed = 45.0 m/min = 0.75 m/s.
        Tact Time = 0.75 / 0.75 = 1.0 second per part.
        """
        calc = TactTimeCalculator()
        tact_time = calc.calculate_tact_time_from_speed(
            engineering_speed=45.0,
            pitch_meters=0.75,
            speed_unit="m/min",
        )
        self.assertEqual(tact_time, 1.0)

        # Realistic factory line example: Pitch = 0.6m, Speed = 1.0 m/min -> 36.0 seconds
        tact_36 = calc.calculate_tact_time_from_speed(
            engineering_speed=1.0,
            pitch_meters=0.6,
            speed_unit="m/min",
        )
        self.assertEqual(tact_36, 36.0)

        # Zero speed test (must not divide by zero)
        tact_zero = calc.calculate_tact_time_from_speed(engineering_speed=0.0)
        self.assertEqual(tact_zero, 0.0)

    # -------------------------------------------------------------------------
    # Test 8: Target Production Rate
    # -------------------------------------------------------------------------
    def test_08_target_production_rate(self) -> None:
        """
        Verify target production rate modular derivations:
        Rate = 3600 / Tact Time.
        Example: Tact time = 36.0 sec/pc -> 100 pcs/hour.
        Inverse: Target rate = 100 pcs/hour -> Tact time = 36.0 sec/pc.
        """
        rate = TactTimeCalculator.calculate_target_rate_from_tact_time(36.0)
        self.assertEqual(rate, 100.0)

        tact = TactTimeCalculator.calculate_tact_time_from_target_rate(100.0)
        self.assertEqual(tact, 36.0)

        # Edge cases
        self.assertEqual(TactTimeCalculator.calculate_target_rate_from_tact_time(0.0), 0.0)
        self.assertEqual(TactTimeCalculator.calculate_tact_time_from_target_rate(0.0), 0.0)

    # -------------------------------------------------------------------------
    # Test 9: Line Status (RUNNING vs STOPPED)
    # -------------------------------------------------------------------------
    def test_09_line_status(self) -> None:
        """
        All stations running -> LINE = RUNNING.
        One or more stations stopped -> LINE = STOPPED.
        """
        # All 10 active
        all_running = {f"M{550 + i}": True for i in range(10)}
        res_running = self.engine.evaluate_line_status(all_running)
        self.assertEqual(res_running.line_status, LineStatus.RUNNING)
        self.assertEqual(len(res_running.stopped_stations), 0)

        # Station 3 (M552) stopped
        one_stopped = dict(all_running)
        one_stopped["M552"] = False
        res_stopped = self.engine.evaluate_line_status(one_stopped)
        self.assertEqual(res_stopped.line_status, LineStatus.STOPPED)
        self.assertEqual(len(res_stopped.stopped_stations), 1)

    # -------------------------------------------------------------------------
    # Test 10: Stopped Station Detection
    # -------------------------------------------------------------------------
    def test_10_stopped_station_detection(self) -> None:
        """
        Verify accurate detection and reporting of stopped stations with display names and PLC addresses.
        """
        raw_bits = {f"M{550 + i}": True for i in range(10)}
        raw_bits["M556"] = False  # Station 7: Optical Inspection (M556)
        raw_bits["M558"] = False  # Station 9: Cleaning (M558)

        status_result = self.engine.evaluate_line_status(raw_bits)
        self.assertEqual(status_result.line_status, LineStatus.STOPPED)
        self.assertEqual(len(status_result.stopped_stations), 2)

        stopped_ids = [s.station_id for s in status_result.stopped_stations]
        self.assertIn(7, stopped_ids)
        self.assertIn(9, stopped_ids)

        s7 = next(s for s in status_result.stopped_stations if s.station_id == 7)
        self.assertEqual(s7.display_name, "Optical Inspection")
        self.assertEqual(s7.plc_address, "M556")

    # -------------------------------------------------------------------------
    # Test 11: Configurable Station Display Names
    # -------------------------------------------------------------------------
    def test_11_configurable_station_display_names(self) -> None:
        """
        Verify that station display names can be changed without altering PLC addresses.
        """
        # Station 1: initial name is "Assembly 1", PLC address M550
        st1_initial = self.engine._current_stations["station_1"]
        self.assertEqual(st1_initial.display_name, "Assembly 1")
        self.assertEqual(st1_initial.plc_address, "M550")

        # Update display name to "Robotic Pick & Place"
        self.engine.update_station_display_name(1, "Robotic Pick & Place")

        st1_updated = self.engine._current_stations["station_1"]
        self.assertEqual(st1_updated.display_name, "Robotic Pick & Place")
        self.assertEqual(st1_updated.plc_address, "M550")  # Address remains stable!

    # -------------------------------------------------------------------------
    # Test 12: Configurable Assembly Line Name
    # -------------------------------------------------------------------------
    def test_12_configurable_assembly_line_name(self) -> None:
        """
        Verify default and dynamic customization of Assembly Line name without source modification.
        """
        default_engine = KPIEngine()
        self.assertEqual(default_engine.assembly_line_name, "Assembly Line")

        # Custom initialization
        custom_engine = KPIEngine(assembly_line_name="Battery Pack Line 04")
        self.assertEqual(custom_engine.assembly_line_name, "Battery Pack Line 04")

        # Dynamic update
        custom_engine.update_assembly_line_name("Battery Pack Line 04 - Refurbished")
        self.assertEqual(custom_engine.assembly_line_name, "Battery Pack Line 04 - Refurbished")

    # -------------------------------------------------------------------------
    # Test 13: Production Day Start Time
    # -------------------------------------------------------------------------
    def test_13_production_day_start_time(self) -> None:
        """
        Verify configurable production day start time (e.g. 08:00 instead of midnight).
        """
        engine_default = KPIEngine()
        self.assertEqual(engine_default.production_day_start, "08:00")

        engine_shift_7 = KPIEngine(production_day_start="07:00")
        self.assertEqual(engine_shift_7.production_day_start, "07:00")


if __name__ == "__main__":
    unittest.main()
