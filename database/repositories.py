"""
Industrial PLC Production Monitor - Repositories
Phase 3: Data-access layer exposing clean, parameterized queries and transactions.
No direct SQL queries are scattered across application logic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.database_manager import DatabaseManager
from database.models import (
    AlarmEventRecord,
    DailySummaryRecord,
    DowntimeEventRecord,
    ProductionDataRecord,
    StationStatusRecord,
)
from utils.logger import get_logger

logger = get_logger("database.repositories")


class ProductionDataRepository:
    """Data-access repository for the 'production_data' table."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def upsert(self, record: ProductionDataRecord) -> int:
        """
        Insert or update an hourly production record identified by (production_date, hour_start).
        Guarantees idempotency and prevents duplicate entries.
        """
        sql = """
        INSERT INTO production_data (
            timestamp, production_date, hour_start, hour_end,
            hourly_target, actual_production, hourly_achievement_percent,
            cumulative_target, cumulative_actual, cumulative_achievement_percent,
            tact_time, average_speed, production_counter
        ) VALUES (
            :timestamp, :production_date, :hour_start, :hour_end,
            :hourly_target, :actual_production, :hourly_achievement_percent,
            :cumulative_target, :cumulative_actual, :cumulative_achievement_percent,
            :tact_time, :average_speed, :production_counter
        )
        ON CONFLICT(production_date, hour_start) DO UPDATE SET
            timestamp = excluded.timestamp,
            hour_end = excluded.hour_end,
            hourly_target = excluded.hourly_target,
            actual_production = excluded.actual_production,
            hourly_achievement_percent = excluded.hourly_achievement_percent,
            cumulative_target = excluded.cumulative_target,
            cumulative_actual = excluded.cumulative_actual,
            cumulative_achievement_percent = excluded.cumulative_achievement_percent,
            tact_time = excluded.tact_time,
            average_speed = excluded.average_speed,
            production_counter = excluded.production_counter;
        """
        params = {
            "timestamp": record.timestamp,
            "production_date": record.production_date,
            "hour_start": record.hour_start,
            "hour_end": record.hour_end,
            "hourly_target": record.hourly_target,
            "actual_production": record.actual_production,
            "hourly_achievement_percent": record.hourly_achievement_percent,
            "cumulative_target": record.cumulative_target,
            "cumulative_actual": record.cumulative_actual,
            "cumulative_achievement_percent": record.cumulative_achievement_percent,
            "tact_time": record.tact_time,
            "average_speed": record.average_speed,
            "production_counter": record.production_counter,
        }
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rec_id = cursor.lastrowid or 0
            cursor.close()
            return rec_id

    def get_by_date(self, production_date: str) -> List[ProductionDataRecord]:
        """Fetch all hourly records for a specific production date ordered chronologically."""
        sql = """
        SELECT * FROM production_data
        WHERE production_date = ?
        ORDER BY hour_start ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (production_date,))
            rows = cursor.fetchall()
            cursor.close()
            return [ProductionDataRecord.from_row(r) for r in rows]

    def get_by_date_range(self, start_date: str, end_date: str) -> List[ProductionDataRecord]:
        """Fetch hourly records within an inclusive date range [start_date, end_date]."""
        sql = """
        SELECT * FROM production_data
        WHERE production_date >= ? AND production_date <= ?
        ORDER BY production_date ASC, hour_start ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()
            cursor.close()
            return [ProductionDataRecord.from_row(r) for r in rows]

    def get_by_id(self, record_id: int) -> Optional[ProductionDataRecord]:
        sql = "SELECT * FROM production_data WHERE id = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (record_id,))
            row = cursor.fetchone()
            cursor.close()
            return ProductionDataRecord.from_row(row) if row else None

    def get_daily_totals(self, production_date: str) -> Dict[str, Any]:
        """Calculate aggregated sums and averages for a given production date."""
        sql = """
        SELECT 
            COALESCE(SUM(actual_production), 0) AS total_actual,
            COALESCE(SUM(hourly_target), 0) AS total_target,
            COUNT(*) AS hours_count,
            AVG(average_speed) AS avg_speed,
            AVG(tact_time) AS avg_tact
        FROM production_data
        WHERE production_date = ?;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (production_date,))
            row = cursor.fetchone()
            cursor.close()
            if not row:
                return {
                    "total_actual": 0,
                    "total_target": 0.0,
                    "hours_count": 0,
                    "avg_speed": 0.0,
                    "avg_tact": 0.0,
                }
            return {
                "total_actual": int(row["total_actual"]),
                "total_target": float(row["total_target"]),
                "hours_count": int(row["hours_count"]),
                "avg_speed": float(row["avg_speed"]) if row["avg_speed"] is not None else 0.0,
                "avg_tact": float(row["avg_tact"]) if row["avg_tact"] is not None else 0.0,
            }


class DowntimeRepository:
    """Data-access repository for the 'downtime_events' table."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def create_event(
        self,
        station_id: int,
        station_name: str,
        start_time: str,
        production_date: str,
        alarm_id: Optional[str] = None,
        alarm_message: Optional[str] = None,
    ) -> int:
        """Record the start of a station downtime event."""
        sql = """
        INSERT INTO downtime_events (
            station_id, station_name, start_time, end_time, duration_seconds,
            alarm_id, alarm_message, production_date
        ) VALUES (
            ?, ?, ?, NULL, NULL, ?, ?, ?
        );
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (station_id, station_name, start_time, alarm_id, alarm_message, production_date),
            )
            event_id = cursor.lastrowid
            cursor.close()
            return int(event_id)

    def close_event(self, event_id: int, end_time: str, duration_seconds: float) -> bool:
        """Close an active downtime event with end time and calculated duration."""
        sql = """
        UPDATE downtime_events
        SET end_time = ?, duration_seconds = ?
        WHERE id = ? AND end_time IS NULL;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (end_time, duration_seconds, event_id))
            updated = cursor.rowcount > 0
            cursor.close()
            return updated

    def get_open_events(self) -> List[DowntimeEventRecord]:
        """Fetch all currently open (unresolved) downtime events."""
        sql = """
        SELECT * FROM downtime_events
        WHERE end_time IS NULL
        ORDER BY start_time ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            return [DowntimeEventRecord.from_row(r) for r in rows]

    def get_open_event_for_station(self, station_id: int) -> Optional[DowntimeEventRecord]:
        """Fetch the current open downtime event for a specific station if any."""
        sql = """
        SELECT * FROM downtime_events
        WHERE station_id = ? AND end_time IS NULL
        ORDER BY start_time DESC LIMIT 1;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (station_id,))
            row = cursor.fetchone()
            cursor.close()
            return DowntimeEventRecord.from_row(row) if row else None

    def get_events_by_date(self, production_date: str) -> List[DowntimeEventRecord]:
        """Fetch all downtime events for a specific production date."""
        sql = """
        SELECT * FROM downtime_events
        WHERE production_date = ?
        ORDER BY start_time ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (production_date,))
            rows = cursor.fetchall()
            cursor.close()
            return [DowntimeEventRecord.from_row(r) for r in rows]

    def get_events_by_date_range(self, start_date: str, end_date: str) -> List[DowntimeEventRecord]:
        """Fetch all downtime events within an inclusive date range."""
        sql = """
        SELECT * FROM downtime_events
        WHERE production_date >= ? AND production_date <= ?
        ORDER BY start_time ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()
            cursor.close()
            return [DowntimeEventRecord.from_row(r) for r in rows]

    def get_events_by_station(
        self,
        station_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[DowntimeEventRecord]:
        """Fetch downtime history for a specific workstation."""
        if start_date and end_date:
            sql = """
            SELECT * FROM downtime_events
            WHERE station_id = ? AND production_date >= ? AND production_date <= ?
            ORDER BY start_time ASC;
            """
            params = (station_id, start_date, end_date)
        else:
            sql = """
            SELECT * FROM downtime_events
            WHERE station_id = ?
            ORDER BY start_time ASC;
            """
            params = (station_id,)  # type: ignore

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close()
            return [DowntimeEventRecord.from_row(r) for r in rows]

    def get_downtime_summary(self, production_date: str) -> Dict[str, Any]:
        """
        Calculate downtime metrics for a given production date.
        Returns total seconds, stop count, longest stop, average stop duration.
        """
        sql = """
        SELECT 
            COALESCE(SUM(duration_seconds), 0.0) AS total_downtime,
            COUNT(*) AS total_stops,
            COALESCE(MAX(duration_seconds), 0.0) AS longest_stop,
            COALESCE(AVG(duration_seconds), 0.0) AS avg_duration
        FROM downtime_events
        WHERE production_date = ? AND end_time IS NOT NULL;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (production_date,))
            row = cursor.fetchone()
            cursor.close()
            if not row:
                return {
                    "total_downtime_seconds": 0.0,
                    "total_stops": 0,
                    "longest_stop_seconds": 0.0,
                    "average_stop_seconds": 0.0,
                }
            return {
                "total_downtime_seconds": round(float(row["total_downtime"]), 2),
                "total_stops": int(row["total_stops"]),
                "longest_stop_seconds": round(float(row["longest_stop"]), 2),
                "average_stop_seconds": round(float(row["avg_duration"]), 2),
            }

    def get_all_events(self) -> List[DowntimeEventRecord]:
        """Fetch all downtime events in chronological order."""
        sql = "SELECT * FROM downtime_events ORDER BY start_time ASC;"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            return [DowntimeEventRecord.from_row(r) for r in rows]

    # Alias for API ergonomics
    get_by_station = get_events_by_station


class AlarmRepository:
    """Data-access repository for the 'alarm_events' table."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def create_alarm(
        self,
        timestamp: str,
        alarm_code: str,
        alarm_message: str,
        severity: str = "WARNING",
        station_id: Optional[int] = None,
        station_name: Optional[str] = None,
        production_date: str = "",
    ) -> int:
        """Insert a newly raised alarm event."""
        sql = """
        INSERT INTO alarm_events (
            timestamp, station_id, station_name, alarm_code, alarm_message,
            severity, active, cleared_at, duration_seconds, production_date
        ) VALUES (
            ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?
        );
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (timestamp, station_id, station_name, alarm_code, alarm_message, severity, production_date),
            )
            alarm_id = cursor.lastrowid
            cursor.close()
            return int(alarm_id)

    def clear_alarm(
        self,
        alarm_id: int,
        cleared_at: str,
        duration_seconds: Optional[float] = None,
    ) -> bool:
        """Clear an alarm by ID."""
        sql = """
        UPDATE alarm_events
        SET active = 0, cleared_at = ?, duration_seconds = ?
        WHERE id = ? AND active = 1;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (cleared_at, duration_seconds, alarm_id))
            updated = cursor.rowcount > 0
            cursor.close()
            return updated

    def clear_active_alarms_by_code(
        self,
        alarm_code: str,
        station_id: Optional[int],
        cleared_at: str,
        duration_seconds: Optional[float] = None,
    ) -> int:
        """Clear all active alarms matching code and station."""
        if station_id is not None:
            sql = """
            UPDATE alarm_events
            SET active = 0, cleared_at = ?, duration_seconds = ?
            WHERE alarm_code = ? AND station_id = ? AND active = 1;
            """
            params = (cleared_at, duration_seconds, alarm_code, station_id)
        else:
            sql = """
            UPDATE alarm_events
            SET active = 0, cleared_at = ?, duration_seconds = ?
            WHERE alarm_code = ? AND active = 1;
            """
            params = (cleared_at, duration_seconds, alarm_code)  # type: ignore

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            count = cursor.rowcount
            cursor.close()
            return count

    def get_active_alarms(self) -> List[AlarmEventRecord]:
        """Fetch all currently active alarms."""
        sql = """
        SELECT * FROM alarm_events
        WHERE active = 1
        ORDER BY timestamp DESC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            return [AlarmEventRecord.from_row(r) for r in rows]

    def get_active_alarm_by_code(
        self,
        alarm_code: str,
        station_id: Optional[int] = None,
    ) -> Optional[AlarmEventRecord]:
        if station_id is not None:
            sql = """
            SELECT * FROM alarm_events
            WHERE alarm_code = ? AND station_id = ? AND active = 1
            ORDER BY timestamp DESC LIMIT 1;
            """
            params = (alarm_code, station_id)
        else:
            sql = """
            SELECT * FROM alarm_events
            WHERE alarm_code = ? AND active = 1
            ORDER BY timestamp DESC LIMIT 1;
            """
            params = (alarm_code,)  # type: ignore

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            cursor.close()
            return AlarmEventRecord.from_row(row) if row else None

    def get_alarms_by_date(self, production_date: str) -> List[AlarmEventRecord]:
        sql = """
        SELECT * FROM alarm_events
        WHERE production_date = ?
        ORDER BY timestamp DESC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (production_date,))
            rows = cursor.fetchall()
            cursor.close()
            return [AlarmEventRecord.from_row(r) for r in rows]

    def get_alarms_by_date_range(
        self,
        start_date: str,
        end_date: str,
        severity: Optional[str] = None,
        station_id: Optional[int] = None,
    ) -> List[AlarmEventRecord]:
        query = "SELECT * FROM alarm_events WHERE production_date >= ? AND production_date <= ?"
        params: List[Any] = [start_date, end_date]

        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if station_id is not None:
            query += " AND station_id = ?"
            params.append(station_id)

        query += " ORDER BY timestamp DESC;"

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            return [AlarmEventRecord.from_row(r) for r in rows]


class StationStatusRepository:
    """Data-access repository for the 'station_status' transition table."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def record_transition(
        self,
        timestamp: str,
        station_id: int,
        station_name: str,
        status: str,
        plc_address: str,
    ) -> int:
        """Record a station state transition (RUNNING or STOPPED)."""
        sql = """
        INSERT INTO station_status (
            timestamp, station_id, station_name, status, plc_address
        ) VALUES (
            ?, ?, ?, ?, ?
        );
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (timestamp, station_id, station_name, status, plc_address))
            rec_id = cursor.lastrowid
            cursor.close()
            return int(rec_id)

    def get_latest_status(self, station_id: int) -> Optional[StationStatusRecord]:
        """Fetch the most recent recorded status transition for a station."""
        sql = """
        SELECT * FROM station_status
        WHERE station_id = ?
        ORDER BY timestamp DESC, id DESC LIMIT 1;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (station_id,))
            row = cursor.fetchone()
            cursor.close()
            return StationStatusRecord.from_row(row) if row else None

    def get_history(
        self,
        station_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[StationStatusRecord]:
        """Retrieve recent status transition log."""
        if station_id is not None:
            sql = """
            SELECT * FROM station_status
            WHERE station_id = ?
            ORDER BY timestamp DESC, id DESC LIMIT ?;
            """
            params = (station_id, limit)
        else:
            sql = """
            SELECT * FROM station_status
            ORDER BY timestamp DESC, id DESC LIMIT ?;
            """
            params = (limit,)  # type: ignore

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close()
            return [StationStatusRecord.from_row(r) for r in rows]


class DailySummaryRepository:
    """Data-access repository for the 'daily_summary' table."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def upsert(self, summary: DailySummaryRecord) -> int:
        """Insert or update daily production summary for a given production date."""
        sql = """
        INSERT INTO daily_summary (
            production_date, daily_target, total_production,
            cumulative_achievement_percent, total_downtime_seconds,
            total_stops, running_time_seconds, average_speed, average_tact_time
        ) VALUES (
            :production_date, :daily_target, :total_production,
            :cumulative_achievement_percent, :total_downtime_seconds,
            :total_stops, :running_time_seconds, :average_speed, :average_tact_time
        )
        ON CONFLICT(production_date) DO UPDATE SET
            daily_target = excluded.daily_target,
            total_production = excluded.total_production,
            cumulative_achievement_percent = excluded.cumulative_achievement_percent,
            total_downtime_seconds = excluded.total_downtime_seconds,
            total_stops = excluded.total_stops,
            running_time_seconds = excluded.running_time_seconds,
            average_speed = excluded.average_speed,
            average_tact_time = excluded.average_tact_time;
        """
        params = {
            "production_date": summary.production_date,
            "daily_target": summary.daily_target,
            "total_production": summary.total_production,
            "cumulative_achievement_percent": summary.cumulative_achievement_percent,
            "total_downtime_seconds": summary.total_downtime_seconds,
            "total_stops": summary.total_stops,
            "running_time_seconds": summary.running_time_seconds,
            "average_speed": summary.average_speed,
            "average_tact_time": summary.average_tact_time,
        }
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rec_id = cursor.lastrowid or 0
            cursor.close()
            return rec_id

    def get_by_date(self, production_date: str) -> Optional[DailySummaryRecord]:
        sql = "SELECT * FROM daily_summary WHERE production_date = ?;"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (production_date,))
            row = cursor.fetchone()
            cursor.close()
            return DailySummaryRecord.from_row(row) if row else None

    def get_by_date_range(self, start_date: str, end_date: str) -> List[DailySummaryRecord]:
        sql = """
        SELECT * FROM daily_summary
        WHERE production_date >= ? AND production_date <= ?
        ORDER BY production_date ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()
            cursor.close()
            return [DailySummaryRecord.from_row(r) for r in rows]
