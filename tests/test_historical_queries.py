"""
Unit Tests for Phase 3: Historical Queries & Date Range Presets
Verifies shift-aware production date calculation (e.g. 08:00 shift boundary),
date preset resolution, production aggregations, downtime analytics, and daily summary generation.
"""
from __future__ import annotations

from datetime import datetime
import os
import tempfile
import unittest

from database.database_manager import DatabaseManager
from database.models import DowntimeEventRecord, ProductionDataRecord
from database.query_service import DatePreset, HistoricalQueryService, get_production_date
from database.repositories import (
    DailySummaryRepository,
    DowntimeRepository,
    ProductionDataRepository,
)
from database.summary_service import DailySummaryService


class TestHistoricalQueriesAndSummary(unittest.TestCase):
    """Test suite for analytics queries, preset resolution, and summary calculations."""

    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

        self.db_manager = DatabaseManager(self.db_path)
        self.prod_repo = ProductionDataRepository(self.db_manager)
        self.downtime_repo = DowntimeRepository(self.db_manager)
        self.summary_repo = DailySummaryRepository(self.db_manager)

        self.query_svc = HistoricalQueryService(
            self.db_manager,
            production_day_start="08:00",
        )
        self.summary_svc = DailySummaryService(self.db_manager)

    def tearDown(self) -> None:
        self.db_manager.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_01_shift_aware_production_date_calculation(self) -> None:
        """
        CRITICAL REQUIREMENT: Do NOT assume the production day starts at 00:00.
        When shift starts at 08:00:
          - 07:59:59 belongs to previous calendar day
          - 08:00:00 belongs to current day
          - 03:00:00 next morning belongs to current production day
        """
        # 1. Right before 08:00 on 2026-09-06 -> belongs to 2026-09-05
        t1 = datetime(2026, 9, 6, 7, 59, 59)
        self.assertEqual(get_production_date("08:00", t1), "2026-09-05")

        # 2. Exactly at 08:00 on 2026-09-06 -> belongs to 2026-09-06
        t2 = datetime(2026, 9, 6, 8, 0, 0)
        self.assertEqual(get_production_date("08:00", t2), "2026-09-06")

        # 3. Afternoon at 15:30 on 2026-09-06 -> belongs to 2026-09-06
        t3 = datetime(2026, 9, 6, 15, 30, 0)
        self.assertEqual(get_production_date("08:00", t3), "2026-09-06")

        # 4. Night shift at 02:15 next calendar morning (2026-09-07) -> still belongs to production date 2026-09-06
        t4 = datetime(2026, 9, 7, 2, 15, 0)
        self.assertEqual(get_production_date("08:00", t4), "2026-09-06")

    def test_02_date_preset_resolutions(self) -> None:
        """Verify date ranges resolved for TODAY, YESTERDAY, LAST_7_DAYS, LAST_30_DAYS, LAST_3_MONTHS."""
        today_s, today_e = self.query_svc.resolve_date_range(DatePreset.TODAY)
        self.assertEqual(today_s, today_e)

        yest_s, yest_e = self.query_svc.resolve_date_range(DatePreset.YESTERDAY)
        self.assertEqual(yest_s, yest_e)

        w_s, w_e = self.query_svc.resolve_date_range(DatePreset.LAST_7_DAYS)
        self.assertLess(w_s, w_e)

        m_s, m_e = self.query_svc.resolve_date_range(DatePreset.LAST_30_DAYS)
        self.assertLess(m_s, m_e)

        q_s, q_e = self.query_svc.resolve_date_range(DatePreset.LAST_3_MONTHS)
        self.assertLess(q_s, q_e)

    def test_03_production_aggregation_queries(self) -> None:
        """Verify get_production_by_hour and get_production_by_day aggregations."""
        # Seed 3 completed hours for date 2026-09-05 and 2 hours for 2026-09-06
        h1 = ProductionDataRecord(
            id=None,
            timestamp="2026-09-05T09:00:00",
            production_date="2026-09-05",
            hour_start="08:00",
            hour_end="09:00",
            hourly_target=100.0,
            actual_production=100,
            hourly_achievement_percent=100.0,
            cumulative_target=100.0,
            cumulative_actual=100,
            cumulative_achievement_percent=100.0,
            tact_time=27.0,
            average_speed=45.0,
            production_counter=100,
        )
        h2 = ProductionDataRecord(
            id=None,
            timestamp="2026-09-05T10:00:00",
            production_date="2026-09-05",
            hour_start="09:00",
            hour_end="10:00",
            hourly_target=100.0,
            actual_production=90,
            hourly_achievement_percent=90.0,
            cumulative_target=200.0,
            cumulative_actual=190,
            cumulative_achievement_percent=95.0,
            tact_time=27.0,
            average_speed=45.0,
            production_counter=190,
        )
        self.prod_repo.upsert(h1)
        self.prod_repo.upsert(h2)

        # Query by date
        hourly = self.query_svc.get_production_by_hour("2026-09-05")
        self.assertEqual(len(hourly), 2)
        self.assertEqual(hourly[0]["actual_production"], 100)
        self.assertEqual(hourly[1]["actual_production"], 90)

        # Query by day
        daily = self.query_svc.get_production_by_day(DatePreset.CUSTOM, start_date="2026-09-05", end_date="2026-09-05")
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0]["actual_production"], 190)
        self.assertEqual(daily[0]["target_production"], 200.0)
        self.assertEqual(daily[0]["achievement_percent"], 95.0)

    def test_04_downtime_analytics_and_station_breakdown(self) -> None:
        """Verify downtime statistics, average stop duration, and station rankings."""
        # Record 2 stops for Station 1 and 1 stop for Station 3
        s1_id = self.downtime_repo.create_event(1, "Assembly 1", "2026-09-06T09:10:00", "2026-09-06")
        self.downtime_repo.close_event(s1_id, "2026-09-06T09:12:00", duration_seconds=120.0)

        s2_id = self.downtime_repo.create_event(1, "Assembly 1", "2026-09-06T10:00:00", "2026-09-06")
        self.downtime_repo.close_event(s2_id, "2026-09-06T10:01:00", duration_seconds=60.0)

        s3_id = self.downtime_repo.create_event(3, "Inspection", "2026-09-06T11:00:00", "2026-09-06")
        self.downtime_repo.close_event(s3_id, "2026-09-06T11:05:00", duration_seconds=300.0)

        stats = self.query_svc.get_downtime_statistics(DatePreset.CUSTOM, start_date="2026-09-06", end_date="2026-09-06")
        self.assertEqual(stats["total_stops"], 3)
        self.assertEqual(stats["total_downtime_seconds"], 480.0)
        self.assertEqual(stats["longest_stop_seconds"], 300.0)
        self.assertEqual(stats["average_stop_seconds"], 160.0)

        # Breakdown by station
        by_station = self.query_svc.get_downtime_by_station(DatePreset.CUSTOM, start_date="2026-09-06", end_date="2026-09-06")
        self.assertEqual(len(by_station), 2)
        # Ordered by total downtime DESC -> Station 3 first (300s), Station 1 second (180s)
        self.assertEqual(by_station[0]["station_id"], 3)
        self.assertEqual(by_station[0]["total_downtime_seconds"], 300.0)
        self.assertEqual(by_station[1]["station_id"], 1)
        self.assertEqual(by_station[1]["stop_count"], 2)
        self.assertEqual(by_station[1]["total_downtime_seconds"], 180.0)

    def test_05_daily_summary_service_generation(self) -> None:
        """Verify automated daily rollup generation linking production and downtime."""
        # Add production record
        self.prod_repo.upsert(
            ProductionDataRecord(
                id=None,
                timestamp="2026-09-06T09:00:00",
                production_date="2026-09-06",
                hour_start="08:00",
                hour_end="09:00",
                hourly_target=100.0,
                actual_production=96,
                hourly_achievement_percent=96.0,
                cumulative_target=100.0,
                cumulative_actual=96,
                cumulative_achievement_percent=96.0,
                tact_time=27.0,
                average_speed=45.0,
                production_counter=96,
            )
        )
        # Add downtime record
        eid = self.downtime_repo.create_event(2, "Screw Installation", "2026-09-06T08:30:00", "2026-09-06")
        self.downtime_repo.close_event(eid, "2026-09-06T08:32:00", duration_seconds=120.0)

        # Generate summary
        summary = self.summary_svc.generate_daily_summary("2026-09-06", daily_target=800.0)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.total_production, 96)
        self.assertEqual(summary.daily_target, 800.0)
        self.assertEqual(summary.cumulative_achievement_percent, 12.0)
        self.assertEqual(summary.total_stops, 1)
        self.assertEqual(summary.total_downtime_seconds, 120.0)
        self.assertEqual(summary.running_time_seconds, 3600.0 - 120.0)


if __name__ == "__main__":
    unittest.main()
