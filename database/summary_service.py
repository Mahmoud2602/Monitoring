"""
Industrial PLC Production Monitor - Daily Summary Service
Phase 3: Automated daily production rollup, downtime aggregation,
running time derivation, and daily KPI snapshot generation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from database.database_manager import DatabaseManager
from database.models import DailySummaryRecord
from database.repositories import (
    DailySummaryRepository,
    DowntimeRepository,
    ProductionDataRepository,
)
from utils.logger import get_logger

logger = get_logger("database.summary")


class DailySummaryService:
    """
    Computes and aggregates production rollups for a specific production date.
    Calculates total parts produced, overall achievement against target,
    cumulative downtime, stop count, net running time, and average speed/tact time.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager
        self.prod_repo = ProductionDataRepository(db_manager)
        self.downtime_repo = DowntimeRepository(db_manager)
        self.summary_repo = DailySummaryRepository(db_manager)

    def generate_daily_summary(
        self,
        production_date: str,
        daily_target: Optional[float] = None,
    ) -> DailySummaryRecord:
        """
        Aggregate all hourly production records and downtime events for a production date.
        Persists the result to the 'daily_summary' table and returns the record.
        """
        # 1. Aggregate production data
        prod_totals = self.prod_repo.get_daily_totals(production_date)
        total_prod = prod_totals["total_actual"]
        hours_recorded = prod_totals["hours_count"]

        # Target resolution
        if daily_target is not None and daily_target > 0:
            target = float(daily_target)
        elif prod_totals["total_target"] > 0:
            target = float(prod_totals["total_target"])
        else:
            target = 1000.0

        achieve_pct = round((total_prod / target * 100.0), 2) if target > 0 else 0.0

        # 2. Aggregate downtime data
        dt_summary = self.downtime_repo.get_downtime_summary(production_date)
        total_dt_sec = dt_summary["total_downtime_seconds"]
        total_stops = dt_summary["total_stops"]

        # 3. Running time calculation
        # Operating planned time = recorded hours * 3600 seconds
        operating_window_seconds = float(hours_recorded * 3600.0) if hours_recorded > 0 else 0.0
        net_running_time = max(0.0, operating_window_seconds - total_dt_sec)

        summary_rec = DailySummaryRecord(
            id=None,
            production_date=production_date,
            daily_target=target,
            total_production=total_prod,
            cumulative_achievement_percent=achieve_pct,
            total_downtime_seconds=total_dt_sec,
            total_stops=total_stops,
            running_time_seconds=round(net_running_time, 2),
            average_speed=prod_totals["avg_speed"],
            average_tact_time=prod_totals["avg_tact"],
        )

        rec_id = self.summary_repo.upsert(summary_rec)
        summary_rec.id = rec_id

        logger.info(
            "Daily Summary generated for %s: Actual=%d, Target=%.0f (%.1f%%), Stops=%d, Downtime=%.1fs, RunTime=%.1fs",
            production_date,
            total_prod,
            target,
            achieve_pct,
            total_stops,
            total_dt_sec,
            net_running_time,
        )
        return summary_rec

    def get_summary(self, production_date: str) -> Optional[DailySummaryRecord]:
        """Fetch pre-calculated daily summary or None."""
        return self.summary_repo.get_by_date(production_date)
