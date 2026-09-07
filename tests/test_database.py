"""
Unit Tests for Phase 3: SQLite Database Manager & Repositories
Verifies schema initialization, table structures, transactions,
and repository query operations using an isolated temporary database.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from database.database_manager import DatabaseManager, EXPECTED_TABLES
from database.models import (
    AlarmEventRecord,
    DailySummaryRecord,
    DowntimeEventRecord,
    ProductionDataRecord,
    StationStatusRecord,
)
from database.repositories import (
    AlarmRepository,
    DailySummaryRepository,
    DowntimeRepository,
    ProductionDataRepository,
    StationStatusRepository,
)


class TestDatabaseManagerAndRepositories(unittest.TestCase):
    """Test suite for the database foundation and repository layer."""

    def setUp(self) -> None:
        # Use an isolated temporary SQLite database file for each test
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

        self.db_manager = DatabaseManager(self.db_path)
        self.prod_repo = ProductionDataRepository(self.db_manager)
        self.downtime_repo = DowntimeRepository(self.db_manager)
        self.alarm_repo = AlarmRepository(self.db_manager)
        self.status_repo = StationStatusRepository(self.db_manager)
        self.summary_repo = DailySummaryRepository(self.db_manager)

    def tearDown(self) -> None:
        self.db_manager.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_database_initialization_and_schema_validation(self) -> None:
        """Verify that all 5 required industrial monitoring tables are created with proper schemas."""
        self.assertTrue(self.db_manager.validate_database_structure())

        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row["name"] for row in cursor.fetchall()}
            cursor.close()

            for expected in EXPECTED_TABLES:
                self.assertIn(expected, tables, f"Expected table '{expected}' not found in database!")

    def test_production_data_repository_upsert_and_query(self) -> None:
        """Verify production_data inserts, conflict resolution on (date, hour_start), and date range queries."""
        rec1 = ProductionDataRecord(
            id=None,
            timestamp="2026-09-06T09:00:00",
            production_date="2026-09-06",
            hour_start="08:00",
            hour_end="09:00",
            hourly_target=100.0,
            actual_production=95,
            hourly_achievement_percent=95.0,
            cumulative_target=100.0,
            cumulative_actual=95,
            cumulative_achievement_percent=95.0,
            tact_time=27.0,
            average_speed=45.0,
            production_counter=95,
        )
        self.prod_repo.upsert(rec1)

        # Query back
        records = self.prod_repo.get_by_date("2026-09-06")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].actual_production, 95)
        self.assertEqual(records[0].hourly_achievement_percent, 95.0)

        # Upsert with revised figures for same hour bucket
        rec1_updated = ProductionDataRecord(
            id=None,
            timestamp="2026-09-06T09:00:00",
            production_date="2026-09-06",
            hour_start="08:00",
            hour_end="09:00",
            hourly_target=100.0,
            actual_production=98,  # updated
            hourly_achievement_percent=98.0,
            cumulative_target=100.0,
            cumulative_actual=98,
            cumulative_achievement_percent=98.0,
            tact_time=26.5,
            average_speed=46.0,
            production_counter=98,
        )
        self.prod_repo.upsert(rec1_updated)

        records_after = self.prod_repo.get_by_date("2026-09-06")
        self.assertEqual(len(records_after), 1, "Upsert should replace existing hour record without duplicates!")
        self.assertEqual(records_after[0].actual_production, 98)

        # Add second hour
        rec2 = ProductionDataRecord(
            id=None,
            timestamp="2026-09-06T10:00:00",
            production_date="2026-09-06",
            hour_start="09:00",
            hour_end="10:00",
            hourly_target=100.0,
            actual_production=102,
            hourly_achievement_percent=102.0,
            cumulative_target=200.0,
            cumulative_actual=200,
            cumulative_achievement_percent=100.0,
            tact_time=25.0,
            average_speed=48.0,
            production_counter=200,
        )
        self.prod_repo.upsert(rec2)

        totals = self.prod_repo.get_daily_totals("2026-09-06")
        self.assertEqual(totals["total_actual"], 200)
        self.assertEqual(totals["total_target"], 200.0)
        self.assertEqual(totals["hours_count"], 2)

    def test_downtime_repository_lifecycle(self) -> None:
        """Verify downtime event creation, closing, duration recording, and querying."""
        # Create stop event
        event_id = self.downtime_repo.create_event(
            station_id=3,
            station_name="Inspection",
            start_time="2026-09-06T10:15:00",
            production_date="2026-09-06",
            alarm_id="ALM_03",
            alarm_message="Vision camera inspection timeout",
        )
        self.assertGreater(event_id, 0)

        # Verify open events
        open_events = self.downtime_repo.get_open_events()
        self.assertEqual(len(open_events), 1)
        self.assertEqual(open_events[0].station_id, 3)
        self.assertIsNone(open_events[0].end_time)

        # Close the event
        closed = self.downtime_repo.close_event(
            event_id=event_id,
            end_time="2026-09-06T10:18:30",
            duration_seconds=210.0,
        )
        self.assertTrue(closed)

        # Verify no open events remaining
        self.assertEqual(len(self.downtime_repo.get_open_events()), 0)

        # Query summary
        summary = self.downtime_repo.get_downtime_summary("2026-09-06")
        self.assertEqual(summary["total_stops"], 1)
        self.assertEqual(summary["total_downtime_seconds"], 210.0)
        self.assertEqual(summary["longest_stop_seconds"], 210.0)
        self.assertEqual(summary["average_stop_seconds"], 210.0)

    def test_alarm_repository_operations(self) -> None:
        """Verify raising, clearing, and querying alarms with severity and timestamps."""
        alarm_id = self.alarm_repo.create_alarm(
            timestamp="2026-09-06T11:00:00",
            alarm_code="ERR_MOTOR_OVERHEAT",
            alarm_message="Conveyor 1 Main Drive motor thermal trip",
            severity="CRITICAL",
            station_id=1,
            station_name="Assembly 1",
            production_date="2026-09-06",
        )
        self.assertGreater(alarm_id, 0)

        active = self.alarm_repo.get_active_alarms()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].alarm_code, "ERR_MOTOR_OVERHEAT")
        self.assertEqual(active[0].severity, "CRITICAL")

        # Clear the alarm
        cleared = self.alarm_repo.clear_alarm(
            alarm_id=alarm_id,
            cleared_at="2026-09-06T11:05:00",
            duration_seconds=300.0,
        )
        self.assertTrue(cleared)
        self.assertEqual(len(self.alarm_repo.get_active_alarms()), 0)

    def test_station_status_repository(self) -> None:
        """Verify recording meaningful station state transitions."""
        self.status_repo.record_transition(
            timestamp="2026-09-06T08:00:00",
            station_id=2,
            station_name="Screw Installation",
            status="RUNNING",
            plc_address="M551",
        )
        self.status_repo.record_transition(
            timestamp="2026-09-06T08:30:00",
            station_id=2,
            station_name="Screw Installation",
            status="STOPPED",
            plc_address="M551",
        )

        latest = self.status_repo.get_latest_status(2)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.status, "STOPPED")

        history = self.status_repo.get_history(station_id=2, limit=10)
        self.assertEqual(len(history), 2)

    def test_daily_summary_repository(self) -> None:
        """Verify daily summary upsert and retrieval."""
        summary = DailySummaryRecord(
            id=None,
            production_date="2026-09-06",
            daily_target=1000.0,
            total_production=980,
            cumulative_achievement_percent=98.0,
            total_downtime_seconds=450.0,
            total_stops=3,
            running_time_seconds=28350.0,
            average_speed=46.5,
            average_tact_time=25.8,
        )
        rec_id = self.summary_repo.upsert(summary)
        self.assertGreater(rec_id, 0)

        fetched = self.summary_repo.get_by_date("2026-09-06")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.total_production, 980)
        self.assertEqual(fetched.total_stops, 3)
        self.assertEqual(fetched.total_downtime_seconds, 450.0)


if __name__ == "__main__":
    unittest.main()
