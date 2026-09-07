"""
Integration Tests for Phase 3: DataManager & End-to-End Historical Workflow
Verifies DataManager coordinating PLC telemetry, KPI engine, SQLite persistence,
downtime event generation, and historical query services.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from core.data_manager import DataManager
from database.query_service import DatePreset
from kpi.models import HourlyProductionRecord
from plc.plc_data import NormalizedPLCData


class TestPhase3Integration(unittest.TestCase):
    """End-to-end test suite for Phase 3 integrated architecture."""

    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

        self.manager = DataManager(
            settings_path="config/settings.json",
            mapping_path="config/plc_mapping.json",
            db_path=self.db_path,
        )

    def tearDown(self) -> None:
        self.manager.stop()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_end_to_end_telemetry_and_downtime_tracking(self) -> None:
        """Verify reading a cycle, processing state transitions, and querying downtime."""
        # 1. Perform single read cycle
        data = self.manager.client.read_cycle()
        self.assertTrue(data.connected)
        self.assertGreater(data.speed, 0.0)

        # 2. Simulate station stop directly through DataManager's downtime manager
        self.manager.downtime_manager.process_station_states({
            2: ("Screw Installation", "M551", False),
            3: ("Inspection", "M552", True),
        })

        active_events = self.manager.downtime_manager.get_active_events()
        self.assertEqual(len(active_events), 1)
        self.assertEqual(active_events[0].station_id, 2)

        time.sleep(0.05)

        # 3. Simulate station 2 resuming operation
        self.manager.downtime_manager.process_station_states({
            2: ("Screw Installation", "M551", True),
            3: ("Inspection", "M552", True),
        })
        self.assertEqual(len(self.manager.downtime_manager.get_active_events()), 0)

        # 4. Verify historical query reflects the stop event
        query_svc = self.manager.get_query_service()
        stats = query_svc.get_downtime_statistics(DatePreset.TODAY)
        self.assertEqual(stats["total_stops"], 1)
        self.assertGreater(stats["total_downtime_seconds"], 0.0)

    def test_hourly_production_persistence_and_daily_summary(self) -> None:
        """Verify that finalized hourly buckets are persisted to SQLite and daily summaries updated."""
        kpi_engine = self.manager.kpi_engine
        today_date = "2026-09-06"

        # Finalize an hour record via KPIEngine
        record = kpi_engine.add_completed_hour_record(
            date_str=today_date,
            hour_start="08:00",
            hour_end="09:00",
            actual_production=98,
            hourly_target=100.0,
            tact_time=27.0,
            average_speed=45.0,
        )
        self.assertEqual(record.actual_production, 98)

        # Verify record exists in SQLite production_data table
        prod_repo = self.manager.prod_repo
        persisted = prod_repo.get_by_date(today_date)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].actual_production, 98)
        self.assertEqual(persisted[0].hourly_achievement_percent, 98.0)

        # Verify daily summary was automatically created
        summary_repo = self.manager.summary_repo
        summary = summary_repo.get_by_date(today_date)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.total_production, 98)


if __name__ == "__main__":
    unittest.main()
