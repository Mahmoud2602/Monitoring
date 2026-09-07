"""
Industrial PLC Production Monitor - Historical Query Service
Phase 3: High-level analytics query API supporting standard industrial filtering
presets (Today, Yesterday, Last 7 Days, Last 30 Days, Last 3 Months, Custom Range).
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from database.database_manager import DatabaseManager
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
from utils.logger import get_logger

logger = get_logger("database.query_service")


class DatePreset(str, Enum):
    """Standard industrial historical date filtering presets."""
    TODAY = "TODAY"
    YESTERDAY = "YESTERDAY"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"
    LAST_3_MONTHS = "LAST_3_MONTHS"
    CUSTOM = "CUSTOM"


def get_production_date(
    dt_or_day_start: Any = None,
    day_start_or_dt: Any = None,
) -> str:
    """
    Determine the logical production date for a timestamp based on the plant's
    configurable production day start time (e.g. '08:00').
    
    Supports flexible calling conventions:
      - get_production_date(dt, "08:00")
      - get_production_date("08:00", dt)
      - get_production_date(day_start="08:00")
      - get_production_date(dt)
    """
    target_dt: Optional[datetime] = None
    day_start_str: str = "08:00"

    # Analyze first argument
    if isinstance(dt_or_day_start, datetime):
        target_dt = dt_or_day_start
    elif isinstance(dt_or_day_start, str):
        if ":" in dt_or_day_start and len(dt_or_day_start) <= 5:
            day_start_str = dt_or_day_start
        else:
            try:
                target_dt = datetime.fromisoformat(dt_or_day_start.replace("Z", "+00:00"))
            except Exception:
                day_start_str = dt_or_day_start

    # Analyze second argument
    if isinstance(day_start_or_dt, datetime):
        target_dt = day_start_or_dt
    elif isinstance(day_start_or_dt, str):
        if ":" in day_start_or_dt and len(day_start_or_dt) <= 5:
            day_start_str = day_start_or_dt
        else:
            try:
                target_dt = datetime.fromisoformat(day_start_or_dt.replace("Z", "+00:00"))
            except Exception:
                day_start_str = day_start_or_dt

    if target_dt is None:
        target_dt = datetime.now(timezone.utc)

    try:
        parts = day_start_str.split(":")
        start_hour = int(parts[0])
        start_min = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        start_hour, start_min = 8, 0

    threshold_time = dtime(hour=start_hour, minute=start_min)
    if target_dt.time() < threshold_time:
        # Belongs to previous day's shift
        return (target_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    return target_dt.strftime("%Y-%m-%d")


class HistoricalQueryService:
    """
    Unified query service for historical analytics and reports.
    Decouples raw SQL queries from presentation and report consumers.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        production_day_start: str = "08:00",
    ) -> None:
        self.db = db_manager
        self.production_day_start = production_day_start

        # Repositories
        self.prod_repo = ProductionDataRepository(db_manager)
        self.downtime_repo = DowntimeRepository(db_manager)
        self.alarm_repo = AlarmRepository(db_manager)
        self.status_repo = StationStatusRepository(db_manager)
        self.summary_repo = DailySummaryRepository(db_manager)

    def resolve_date_range(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> Tuple[str, str]:
        """
        Convert a DatePreset or date string into an inclusive (start_date, end_date) string pair (YYYY-MM-DD).
        """
        # If caller passed a direct date string such as "2026-09-05"
        if isinstance(preset, str):
            if len(preset) == 10 and preset.count("-") == 2:
                return preset, end_date or preset
            try:
                preset = DatePreset(preset.lower())
            except ValueError:
                pass

        ref_dt = reference_time or datetime.now(timezone.utc)
        today_str = get_production_date(ref_dt, self.production_day_start)
        today_date = datetime.strptime(today_str, "%Y-%m-%d")

        if preset == DatePreset.TODAY:
            return today_str, today_str
        elif preset == DatePreset.YESTERDAY:
            yest_str = (today_date - timedelta(days=1)).strftime("%Y-%m-%d")
            return yest_str, yest_str
        elif preset == DatePreset.LAST_7_DAYS:
            past_str = (today_date - timedelta(days=6)).strftime("%Y-%m-%d")
            return past_str, today_str
        elif preset == DatePreset.LAST_30_DAYS:
            past_str = (today_date - timedelta(days=29)).strftime("%Y-%m-%d")
            return past_str, today_str
        elif preset == DatePreset.LAST_3_MONTHS:
            past_str = (today_date - timedelta(days=90)).strftime("%Y-%m-%d")
            return past_str, today_str
        elif preset == DatePreset.CUSTOM:
            if not start_date or not end_date:
                return today_str, today_str
            return start_date, end_date
        return today_str, today_str

    # -------------------------------------------------------------------------
    # Production Queries
    # -------------------------------------------------------------------------
    def get_production_by_hour(
        self,
        preset: DatePreset = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[ProductionDataRecord]:
        """Fetch granular hourly production records within the requested window."""
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        if s_date == e_date:
            return self.prod_repo.get_by_date(s_date)
        return self.prod_repo.get_by_date_range(s_date, e_date)

    def get_production_by_day(
        self,
        preset: DatePreset = DatePreset.LAST_7_DAYS,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate hourly production metrics rolled up by day.
        Returns daily totals, achievement rates, and average speeds.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        sql = """
        SELECT 
            production_date,
            SUM(actual_production) AS total_actual,
            SUM(hourly_target) AS total_target,
            COUNT(id) AS hours_count,
            AVG(average_speed) AS avg_speed,
            AVG(tact_time) AS avg_tact
        FROM production_data
        WHERE production_date >= ? AND production_date <= ?
        GROUP BY production_date
        ORDER BY production_date ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (s_date, e_date))
            rows = cursor.fetchall()
            cursor.close()

            results = []
            for r in rows:
                actual = int(r["total_actual"])
                target = float(r["total_target"])
                achieve_pct = round((actual / target * 100.0), 2) if target > 0 else 0.0
                results.append({
                    "production_date": str(r["production_date"]),
                    "actual_production": actual,
                    "target_production": round(target, 2),
                    "achievement_percent": achieve_pct,
                    "hours_recorded": int(r["hours_count"]),
                    "average_speed": round(float(r["avg_speed"]), 2) if r["avg_speed"] is not None else 0.0,
                    "average_tact_time": round(float(r["avg_tact"]), 2) if r["avg_tact"] is not None else 0.0,
                })
            return results

    # -------------------------------------------------------------------------
    # Downtime Queries
    # -------------------------------------------------------------------------
    def get_downtime_events(
        self,
        preset: DatePreset = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[DowntimeEventRecord]:
        """Fetch all individual downtime events within the resolved range."""
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        return self.downtime_repo.get_events_by_date_range(s_date, e_date)

    def get_downtime_by_hour(
        self,
        preset: DatePreset = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate total downtime duration and stop counts grouped by the hour bucket (00-23)
        when the stoppage initiated.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        sql = """
        SELECT 
            strftime('%H:00', start_time) AS hour_bucket,
            COUNT(id) AS stop_count,
            COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds,
            AVG(duration_seconds) AS avg_duration_seconds
        FROM downtime_events
        WHERE production_date >= ? AND production_date <= ? AND end_time IS NOT NULL
        GROUP BY hour_bucket
        ORDER BY hour_bucket ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (s_date, e_date))
            rows = cursor.fetchall()
            cursor.close()
            return [
                {
                    "hour_bucket": str(r["hour_bucket"]),
                    "stop_count": int(r["stop_count"]),
                    "total_downtime_seconds": round(float(r["total_downtime_seconds"]), 2),
                    "average_duration_seconds": round(float(r["avg_duration_seconds"]), 2) if r["avg_duration_seconds"] is not None else 0.0,
                }
                for r in rows
            ]

    def get_downtime_by_station(
        self,
        preset: DatePreset = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate downtime duration and stop counts by physical workstation.
        Helps identify bottleneck stations.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        sql = """
        SELECT 
            station_id,
            station_name,
            COUNT(id) AS stop_count,
            COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds,
            COALESCE(AVG(duration_seconds), 0.0) AS avg_stop_duration,
            COALESCE(MAX(duration_seconds), 0.0) AS longest_stop_duration
        FROM downtime_events
        WHERE production_date >= ? AND production_date <= ? AND end_time IS NOT NULL
        GROUP BY station_id, station_name
        ORDER BY total_downtime_seconds DESC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (s_date, e_date))
            rows = cursor.fetchall()
            cursor.close()
            return [
                {
                    "station_id": int(r["station_id"]),
                    "station_name": str(r["station_name"]),
                    "stop_count": int(r["stop_count"]),
                    "total_downtime_seconds": round(float(r["total_downtime_seconds"]), 2),
                    "average_stop_duration": round(float(r["avg_stop_duration"]), 2),
                    "longest_stop_duration": round(float(r["longest_stop_duration"]), 2),
                }
                for r in rows
            ]

    def get_downtime_statistics(
        self,
        preset: DatePreset = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive downtime metrics: total duration, stop count,
        average duration, longest stop, and shortest stop.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        sql = """
        SELECT 
            COUNT(id) AS total_stops,
            COALESCE(SUM(duration_seconds), 0.0) AS total_downtime,
            COALESCE(AVG(duration_seconds), 0.0) AS avg_duration,
            COALESCE(MAX(duration_seconds), 0.0) AS longest_stop,
            COALESCE(MIN(duration_seconds), 0.0) AS shortest_stop
        FROM downtime_events
        WHERE production_date >= ? AND production_date <= ? AND end_time IS NOT NULL;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (s_date, e_date))
            r = cursor.fetchone()
            cursor.close()
            if not r or r["total_stops"] == 0:
                return {
                    "total_stops": 0,
                    "total_downtime_seconds": 0.0,
                    "average_stop_seconds": 0.0,
                    "longest_stop_seconds": 0.0,
                    "shortest_stop_seconds": 0.0,
                }
            return {
                "total_stops": int(r["total_stops"]),
                "total_downtime_seconds": round(float(r["total_downtime"]), 2),
                "average_stop_seconds": round(float(r["avg_duration"]), 2),
                "longest_stop_seconds": round(float(r["longest_stop"]), 2),
                "shortest_stop_seconds": round(float(r["shortest_stop"]), 2),
            }

    # -------------------------------------------------------------------------
    # Station Status & Alarm History
    # -------------------------------------------------------------------------
    def get_station_status_history(
        self,
        station_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[StationStatusRecord]:
        """Retrieve recent status transitions."""
        return self.status_repo.get_history(station_id=station_id, limit=limit)

    def get_alarm_history(
        self,
        preset: DatePreset = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        severity: Optional[str] = None,
        station_id: Optional[int] = None,
    ) -> List[AlarmEventRecord]:
        """Retrieve historical alarm events."""
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        return self.alarm_repo.get_alarms_by_date_range(
            start_date=s_date,
            end_date=e_date,
            severity=severity,
            station_id=station_id,
        )

    def get_daily_summaries(
        self,
        preset: DatePreset = DatePreset.LAST_7_DAYS,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[DailySummaryRecord]:
        """Fetch pre-aggregated daily summaries."""
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        return self.summary_repo.get_by_date_range(s_date, e_date)
