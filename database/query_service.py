"""
Industrial PLC Production Monitor - Historical Query Service
Phase 3: High-level analytics query API supporting standard industrial filtering
presets (Today, Yesterday, Last 7 Days, Last 30 Days, Last 3 Months, Custom Range).
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

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


from core.production_day import get_production_date


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

    # -------------------------------------------------------------------------
    # Phase 5: High-Level Analytics & Trend Query API
    # -------------------------------------------------------------------------
    def get_historical_summary(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Compute high-level executive KPI summaries across the selected date range:
        Total Production, Total Target, Achievement %, Total Downtime, Number of Stops,
        Average Stop Duration, Longest Stop, Average Speed, Average Tact Time.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        date_label = s_date if s_date == e_date else f"{s_date} to {e_date}"

        # 1. Production metrics from production_data
        prod_sql = """
        SELECT 
            COALESCE(SUM(actual_production), 0) AS total_actual,
            COALESCE(SUM(hourly_target), 0.0) AS total_target,
            COUNT(id) AS hours_count,
            AVG(average_speed) AS avg_speed,
            AVG(tact_time) AS avg_tact
        FROM production_data
        WHERE production_date >= ? AND production_date <= ?;
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(prod_sql, (s_date, e_date))
            prod_row = cur.fetchone()
            cur.close()

        total_actual = int(prod_row["total_actual"]) if prod_row else 0
        total_target = float(prod_row["total_target"]) if prod_row else 0.0
        achieve_pct = round((total_actual / total_target * 100.0), 2) if total_target > 0 else 0.0
        avg_speed = round(float(prod_row["avg_speed"]), 2) if (prod_row and prod_row["avg_speed"] is not None) else 0.0
        avg_tact = round(float(prod_row["avg_tact"]), 2) if (prod_row and prod_row["avg_tact"] is not None) else 0.0

        # 2. Downtime metrics from downtime_events
        if station_id is not None:
            dt_sql = """
            SELECT 
                COUNT(id) AS total_stops,
                COALESCE(SUM(duration_seconds), 0.0) AS total_downtime,
                COALESCE(AVG(duration_seconds), 0.0) AS avg_duration,
                COALESCE(MAX(duration_seconds), 0.0) AS longest_stop
            FROM downtime_events
            WHERE production_date >= ? AND production_date <= ? AND station_id = ? AND end_time IS NOT NULL;
            """
            dt_params: Tuple[Any, ...] = (s_date, e_date, station_id)
        else:
            dt_sql = """
            SELECT 
                COUNT(id) AS total_stops,
                COALESCE(SUM(duration_seconds), 0.0) AS total_downtime,
                COALESCE(AVG(duration_seconds), 0.0) AS avg_duration,
                COALESCE(MAX(duration_seconds), 0.0) AS longest_stop
            FROM downtime_events
            WHERE production_date >= ? AND production_date <= ? AND end_time IS NOT NULL;
            """
            dt_params = (s_date, e_date)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(dt_sql, dt_params)
            dt_row = cur.fetchone()
            cur.close()

        total_stops = int(dt_row["total_stops"]) if dt_row else 0
        total_dt_sec = round(float(dt_row["total_downtime"]), 2) if dt_row else 0.0
        avg_stop_sec = round(float(dt_row["avg_duration"]), 2) if dt_row else 0.0
        longest_stop_sec = round(float(dt_row["longest_stop"]), 2) if dt_row else 0.0

        # 3. Best and Worst Hour Calculations
        best_hour_sql = """
        SELECT hour_start, hour_end, actual_production, hourly_target, hourly_achievement_percent, production_date
        FROM production_data
        WHERE production_date >= ? AND production_date <= ?
        ORDER BY actual_production DESC, id ASC
        LIMIT 1;
        """
        worst_hour_sql = """
        SELECT hour_start, hour_end, actual_production, hourly_target, hourly_achievement_percent, production_date
        FROM production_data
        WHERE production_date >= ? AND production_date <= ?
        ORDER BY actual_production ASC, id ASC
        LIMIT 1;
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(best_hour_sql, (s_date, e_date))
            best_row = cur.fetchone()
            cur.execute(worst_hour_sql, (s_date, e_date))
            worst_row = cur.fetchone()
            cur.close()

        best_hour = None
        best_hour_str = "--"
        if best_row and best_row["actual_production"] is not None:
            best_prod = int(best_row["actual_production"])
            best_h_start = str(best_row["hour_start"])
            best_h_end = str(best_row["hour_end"])
            best_hour = {
                "hour_start": best_h_start,
                "hour_end": best_h_end,
                "production": best_prod,
                "target": float(best_row["hourly_target"]),
                "achievement_percent": float(best_row["hourly_achievement_percent"]),
                "date": str(best_row["production_date"]),
            }
            best_hour_str = f"{best_h_start} ({best_prod} pcs)"

        worst_hour = None
        worst_hour_str = "--"
        if worst_row and worst_row["actual_production"] is not None:
            worst_prod = int(worst_row["actual_production"])
            worst_h_start = str(worst_row["hour_start"])
            worst_h_end = str(worst_row["hour_end"])
            worst_hour = {
                "hour_start": worst_h_start,
                "hour_end": worst_h_end,
                "production": worst_prod,
                "target": float(worst_row["hourly_target"]),
                "achievement_percent": float(worst_row["hourly_achievement_percent"]),
                "date": str(worst_row["production_date"]),
            }
            worst_hour_str = f"{worst_h_start} ({worst_prod} pcs)"

        # 4. Running Time Calculation
        hours_count = int(prod_row["hours_count"]) if prod_row else 0
        if hours_count > 0:
            operating_sec = hours_count * 3600.0
            running_time_sec = max(0.0, operating_sec - total_dt_sec)
        else:
            # If checking current production day, use elapsed shift time
            try:
                now_dt = datetime.now()
                curr_date = self.get_production_date(now_dt)
                if s_date == curr_date and s_date == e_date:
                    h_str, m_str = self.production_day_start.split(":")
                    shift_start = now_dt.replace(hour=int(h_str), minute=int(m_str), second=0, microsecond=0)
                    if now_dt < shift_start:
                        shift_start -= timedelta(days=1)
                    elapsed_sec = max(0.0, (now_dt - shift_start).total_seconds())
                    running_time_sec = max(0.0, elapsed_sec - total_dt_sec)
                else:
                    running_time_sec = 0.0
            except Exception:
                running_time_sec = 0.0

        def _fmt_hms(sec: float) -> str:
            s = max(0, int(sec))
            h = s // 3600
            m = (s % 3600) // 60
            sec_rem = s % 60
            return f"{h:02d}:{m:02d}:{sec_rem:02d}"

        def _fmt_compact(sec: float) -> str:
            if sec <= 0:
                return "0s"
            if sec < 60:
                return f"{sec:.1f}s"
            m = int(sec) // 60
            rem_s = int(sec) % 60
            return f"{m}m {rem_s}s"

        return {
            "start_date": s_date,
            "end_date": e_date,
            "date_range_label": date_label,
            "station_id": station_id,
            "total_production": total_actual,
            "total_target": round(total_target, 2),
            "achievement_percent": achieve_pct,
            "total_downtime_seconds": total_dt_sec,
            "total_downtime_str": _fmt_hms(total_dt_sec),
            "running_time_seconds": round(running_time_sec, 2),
            "running_time_str": _fmt_hms(running_time_sec),
            "total_stops": total_stops,
            "average_stop_seconds": avg_stop_sec,
            "average_stop_str": _fmt_compact(avg_stop_sec),
            "longest_stop_seconds": longest_stop_sec,
            "longest_stop_str": _fmt_compact(longest_stop_sec),
            "average_speed": avg_speed,
            "average_tact_time": avg_tact,
            "best_hour": best_hour,
            "best_hour_str": best_hour_str,
            "worst_hour": worst_hour,
            "worst_hour_str": worst_hour_str,
        }

    def get_production_trend(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate time-series data for production charts.
        Uses hourly resolution for single-day queries (or short ranges),
        and daily resolution for multi-day queries.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        is_single_day = (s_date == e_date)

        if is_single_day:
            # Hourly breakdown
            records = self.prod_repo.get_by_date(s_date)
            results = []
            for r in records:
                results.append({
                    "time_label": r.hour_start,
                    "date": r.production_date,
                    "actual": r.actual_production,
                    "target": r.hourly_target,
                    "achievement_percent": r.hourly_achievement_percent,
                    "speed": r.average_speed or 0.0,
                    "tact_time": r.tact_time,
                })
            return results
        else:
            # Daily aggregation
            daily_list = self.get_production_by_day(
                preset=DatePreset.CUSTOM, start_date=s_date, end_date=e_date
            )
            results = []
            for d in daily_list:
                results.append({
                    "time_label": d["production_date"],
                    "date": d["production_date"],
                    "actual": d["actual_production"],
                    "target": d["target_production"],
                    "achievement_percent": d["achievement_percent"],
                    "speed": d["average_speed"],
                    "tact_time": d["average_tact_time"],
                })
            return results

    def get_achievement_trend(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Achievement percentage time series with explicit 100% reference line benchmark.
        """
        prod_trend = self.get_production_trend(preset, start_date, end_date)
        return [
            {
                "time_label": p["time_label"],
                "achievement_percent": p["achievement_percent"],
                "target_reference": 100.0,
                "actual": p["actual"],
                "target": p["target"],
            }
            for p in prod_trend
        ]

    def get_speed_trend(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        speed_setpoint: float = 45.0,
    ) -> List[Dict[str, Any]]:
        """
        Actual conveyor speed vs target speed setpoint over time.
        """
        prod_trend = self.get_production_trend(preset, start_date, end_date)
        return [
            {
                "time_label": p["time_label"],
                "actual_speed": p["speed"],
                "speed_setpoint": speed_setpoint,
            }
            for p in prod_trend
        ]

    def get_downtime_trend(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Downtime duration (seconds & minutes) over time (hourly for single-day, daily for multi-day).
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        is_single_day = (s_date == e_date)

        if is_single_day:
            if station_id is not None:
                sql = """
                SELECT 
                    strftime('%H:00', start_time) AS time_bucket,
                    COUNT(id) AS stop_count,
                    COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds
                FROM downtime_events
                WHERE production_date = ? AND station_id = ? AND end_time IS NOT NULL
                GROUP BY time_bucket
                ORDER BY time_bucket ASC;
                """
                params: Tuple[Any, ...] = (s_date, station_id)
            else:
                sql = """
                SELECT 
                    strftime('%H:00', start_time) AS time_bucket,
                    COUNT(id) AS stop_count,
                    COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds
                FROM downtime_events
                WHERE production_date = ? AND end_time IS NOT NULL
                GROUP BY time_bucket
                ORDER BY time_bucket ASC;
                """
                params = (s_date,)
        else:
            if station_id is not None:
                sql = """
                SELECT 
                    production_date AS time_bucket,
                    COUNT(id) AS stop_count,
                    COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds
                FROM downtime_events
                WHERE production_date >= ? AND production_date <= ? AND station_id = ? AND end_time IS NOT NULL
                GROUP BY time_bucket
                ORDER BY time_bucket ASC;
                """
                params = (s_date, e_date, station_id)
            else:
                sql = """
                SELECT 
                    production_date AS time_bucket,
                    COUNT(id) AS stop_count,
                    COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds
                FROM downtime_events
                WHERE production_date >= ? AND production_date <= ? AND end_time IS NOT NULL
                GROUP BY time_bucket
                ORDER BY time_bucket ASC;
                """
                params = (s_date, e_date)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()

        results = []
        for r in rows:
            sec = round(float(r["total_downtime_seconds"]), 2)
            results.append({
                "time_label": str(r["time_bucket"]),
                "downtime_seconds": sec,
                "downtime_minutes": round(sec / 60.0, 2),
                "stop_count": int(r["stop_count"]),
            })
        return results

    def get_downtime_by_station_full(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Full 10-station downtime analysis with configured station display names.
        Ensures stations 1-10 are systematically present.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        station_names = station_display_names or {}

        sql = """
        SELECT 
            station_id,
            COUNT(id) AS stop_count,
            COALESCE(SUM(duration_seconds), 0.0) AS total_downtime_seconds,
            COALESCE(AVG(duration_seconds), 0.0) AS avg_stop_duration,
            COALESCE(MAX(duration_seconds), 0.0) AS longest_stop_duration
        FROM downtime_events
        WHERE production_date >= ? AND production_date <= ? AND end_time IS NOT NULL
        GROUP BY station_id;
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, (s_date, e_date))
            rows = cur.fetchall()
            cur.close()

        data_map = {int(r["station_id"]): r for r in rows}
        results = []

        for st_id in range(1, 11):
            name = (
                station_names.get(str(st_id))
                or station_names.get(st_id)
                or f"Station {st_id}"
            )
            r = data_map.get(st_id)
            if r:
                sec = round(float(r["total_downtime_seconds"]), 2)
                stops = int(r["stop_count"])
                avg_d = round(float(r["avg_stop_duration"]), 2)
                long_d = round(float(r["longest_stop_duration"]), 2)
            else:
                sec = 0.0
                stops = 0
                avg_d = 0.0
                long_d = 0.0

            results.append({
                "station_id": st_id,
                "station_name": name,
                "display_label": f"St {st_id} - {name}",
                "stop_count": stops,
                "total_downtime_seconds": sec,
                "total_downtime_minutes": round(sec / 60.0, 2),
                "avg_stop_duration": avg_d,
                "longest_stop_duration": long_d,
            })

        return results

    def get_stop_count_by_station_full(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Full 10-station stop-count breakdown for problem identification.
        """
        station_dts = self.get_downtime_by_station_full(
            preset=preset,
            start_date=start_date,
            end_date=end_date,
            station_display_names=station_display_names,
        )
        return [
            {
                "station_id": s["station_id"],
                "station_name": s["station_name"],
                "display_label": s["display_label"],
                "stop_count": s["stop_count"],
                "total_downtime_minutes": s["total_downtime_minutes"],
            }
            for s in station_dts
        ]

    def get_downtime_history_table(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_id: Optional[int] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Downtime events formatted for tabular presentation, sorted newest first.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        station_names = station_display_names or {}

        if station_id is not None:
            sql = """
            SELECT * FROM downtime_events
            WHERE production_date >= ? AND production_date <= ? AND station_id = ?
            ORDER BY start_time DESC, id DESC
            LIMIT ?;
            """
            params: Tuple[Any, ...] = (s_date, e_date, station_id, limit)
        else:
            sql = """
            SELECT * FROM downtime_events
            WHERE production_date >= ? AND production_date <= ?
            ORDER BY start_time DESC, id DESC
            LIMIT ?;
            """
            params = (s_date, e_date, limit)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()

        def _fmt_duration(sec: Optional[float]) -> str:
            if sec is None:
                return "ACTIVE"
            if sec < 60:
                return f"{sec:.1f}s"
            m = int(sec) // 60
            s = int(sec) % 60
            return f"{m}m {s}s"

        results = []
        for r in rows:
            st_id = int(r["station_id"])
            name = (
                station_names.get(str(st_id))
                or station_names.get(st_id)
                or str(r["station_name"])
            )
            duration_s = float(r["duration_seconds"]) if r["duration_seconds"] is not None else None
            results.append({
                "id": r["id"],
                "production_date": str(r["production_date"]),
                "station_id": st_id,
                "station_name": name,
                "start_time": str(r["start_time"]),
                "end_time": str(r["end_time"]) if r["end_time"] else "ONGOING",
                "duration_seconds": duration_s,
                "duration_str": _fmt_duration(duration_s),
                "alarm_id": str(r["alarm_id"] or "--"),
                "alarm_message": str(r["alarm_message"] or "Station Interruption"),
            })
        return results

    def get_alarm_history_table(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_id: Optional[int] = None,
        severity: Optional[str] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Alarm history table with filtering by date range, station, and severity.
        Sorted newest first.
        """
        s_date, e_date = self.resolve_date_range(preset, start_date, end_date)
        station_names = station_display_names or {}

        query = """
        SELECT * FROM alarm_events
        WHERE production_date >= ? AND production_date <= ?
        """
        params: List[Any] = [s_date, e_date]

        if station_id is not None:
            query += " AND station_id = ?"
            params.append(station_id)

        if severity and severity.upper() != "ALL":
            query += " AND severity = ?"
            params.append(severity.upper())

        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            cur.close()

        def _fmt_duration(sec: Optional[float]) -> str:
            if sec is None:
                return "ACTIVE"
            if sec < 60:
                return f"{sec:.1f}s"
            m = int(sec) // 60
            s = int(sec) % 60
            return f"{m}m {s}s"

        results = []
        for r in rows:
            st_id = int(r["station_id"]) if r["station_id"] is not None else None
            if st_id is not None:
                name = (
                    station_names.get(str(st_id))
                    or station_names.get(st_id)
                    or str(r["station_name"] or f"Station {st_id}")
                )
            else:
                name = str(r["station_name"] or "Line Level")

            dur = float(r["duration_seconds"]) if r["duration_seconds"] is not None else None
            is_active = bool(r["active"])
            status = "ACTIVE" if is_active else "CLEARED"

            results.append({
                "id": r["id"],
                "timestamp": str(r["timestamp"]),
                "production_date": str(r["production_date"]),
                "station_id": st_id,
                "station_name": name,
                "alarm_code": str(r["alarm_code"]),
                "alarm_message": str(r["alarm_message"]),
                "severity": str(r["severity"]),
                "start_time": str(r["timestamp"]),
                "cleared_at": str(r["cleared_at"] or "--"),
                "duration_seconds": dur,
                "duration_str": _fmt_duration(dur),
                "status": status,
            })
        return results

    def get_export_dataset(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_id: Optional[int] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
        speed_setpoint: float = 45.0,
    ) -> Dict[str, Any]:
        """
        Unified structured dataset prepared for future PDF, Excel, CSV, or JSON export.
        """
        summary = self.get_historical_summary(preset, start_date, end_date, station_id)
        prod_trend = self.get_production_trend(preset, start_date, end_date)
        achieve_trend = self.get_achievement_trend(preset, start_date, end_date)
        speed_trend = self.get_speed_trend(preset, start_date, end_date, speed_setpoint)
        dt_trend = self.get_downtime_trend(preset, start_date, end_date, station_id)
        st_downtime = self.get_downtime_by_station_full(preset, start_date, end_date, station_display_names)
        st_stops = self.get_stop_count_by_station_full(preset, start_date, end_date, station_display_names)
        dt_events = self.get_downtime_history_table(preset, start_date, end_date, station_id, station_display_names, limit=1000)
        alarms = self.get_alarm_history_table(preset, start_date, end_date, station_id, severity=None, station_display_names=station_display_names, limit=1000)

        return {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "preset": str(preset),
                "start_date": summary["start_date"],
                "end_date": summary["end_date"],
                "station_filter": station_id,
            },
            "summary": summary,
            "production_trend": prod_trend,
            "achievement_trend": achieve_trend,
            "speed_trend": speed_trend,
            "downtime_trend": dt_trend,
            "station_downtime": st_downtime,
            "station_stops": st_stops,
            "downtime_events": dt_events,
            "alarm_events": alarms,
        }
