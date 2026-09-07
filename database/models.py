"""
Industrial PLC Production Monitor - Database Models
Phase 3: Strongly typed data records for SQLite historical storage.
Covers:
1. production_data
2. downtime_events
3. alarm_events
4. station_status
5. daily_summary
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Dict, Optional


@dataclass
class ProductionDataRecord:
    """
    Historical record for an hourly production interval.
    Matches schema for the 'production_data' table.
    """
    id: Optional[int]
    timestamp: str
    production_date: str
    hour_start: str
    hour_end: str
    hourly_target: float
    actual_production: int
    hourly_achievement_percent: float
    cumulative_target: float
    cumulative_actual: int
    cumulative_achievement_percent: float
    tact_time: float = 0.0
    average_speed: Optional[float] = None
    production_counter: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "production_date": self.production_date,
            "hour_start": self.hour_start,
            "hour_end": self.hour_end,
            "hourly_target": round(self.hourly_target, 2),
            "actual_production": int(self.actual_production),
            "hourly_achievement_percent": round(self.hourly_achievement_percent, 2),
            "cumulative_target": round(self.cumulative_target, 2),
            "cumulative_actual": int(self.cumulative_actual),
            "cumulative_achievement_percent": round(self.cumulative_achievement_percent, 2),
            "tact_time": round(self.tact_time, 2),
            "average_speed": round(self.average_speed, 2) if self.average_speed is not None else None,
            "production_counter": int(self.production_counter),
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    @classmethod
    def from_row(cls, row: Any) -> ProductionDataRecord:
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            production_date=row["production_date"],
            hour_start=row["hour_start"],
            hour_end=row["hour_end"],
            hourly_target=float(row["hourly_target"]),
            actual_production=int(row["actual_production"]),
            hourly_achievement_percent=float(row["hourly_achievement_percent"]),
            cumulative_target=float(row["cumulative_target"]),
            cumulative_actual=int(row["cumulative_actual"]),
            cumulative_achievement_percent=float(row["cumulative_achievement_percent"]),
            tact_time=float(row["tact_time"]) if row["tact_time"] is not None else 0.0,
            average_speed=float(row["average_speed"]) if row["average_speed"] is not None else None,
            production_counter=int(row["production_counter"]) if row["production_counter"] is not None else 0,
        )


@dataclass
class DowntimeEventRecord:
    """
    Record of a discrete station stoppage event.
    Matches schema for the 'downtime_events' table.
    """
    id: Optional[int]
    station_id: int
    station_name: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    alarm_id: Optional[str] = None
    alarm_message: Optional[str] = None
    production_date: str = ""

    def is_active(self) -> bool:
        """True if the stoppage has not yet concluded."""
        return self.end_time is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "station_id": self.station_id,
            "station_name": self.station_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": round(self.duration_seconds, 2) if self.duration_seconds is not None else None,
            "alarm_id": self.alarm_id,
            "alarm_message": self.alarm_message,
            "production_date": self.production_date,
            "is_active": self.is_active(),
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    @classmethod
    def from_row(cls, row: Any) -> DowntimeEventRecord:
        return cls(
            id=row["id"],
            station_id=int(row["station_id"]),
            station_name=str(row["station_name"]),
            start_time=str(row["start_time"]),
            end_time=row["end_time"],
            duration_seconds=float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
            alarm_id=row["alarm_id"],
            alarm_message=row["alarm_message"],
            production_date=str(row["production_date"]),
        )


@dataclass
class AlarmEventRecord:
    """
    Record of an industrial alarm condition.
    Matches schema for the 'alarm_events' table.
    """
    id: Optional[int]
    timestamp: str
    alarm_code: str
    alarm_message: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    station_id: Optional[int] = None
    station_name: Optional[str] = None
    active: bool = True
    cleared_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    production_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "station_id": self.station_id,
            "station_name": self.station_name,
            "alarm_code": self.alarm_code,
            "alarm_message": self.alarm_message,
            "severity": self.severity,
            "active": self.active,
            "cleared_at": self.cleared_at,
            "duration_seconds": round(self.duration_seconds, 2) if self.duration_seconds is not None else None,
            "production_date": self.production_date,
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    @classmethod
    def from_row(cls, row: Any) -> AlarmEventRecord:
        return cls(
            id=row["id"],
            timestamp=str(row["timestamp"]),
            station_id=int(row["station_id"]) if row["station_id"] is not None else None,
            station_name=row["station_name"],
            alarm_code=str(row["alarm_code"]),
            alarm_message=str(row["alarm_message"]),
            severity=str(row["severity"]),
            active=bool(row["active"]),
            cleared_at=row["cleared_at"],
            duration_seconds=float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
            production_date=str(row["production_date"]),
        )


@dataclass
class StationStatusRecord:
    """
    Record of a station state transition (RUNNING <-> STOPPED).
    Matches schema for the 'station_status' table.
    """
    id: Optional[int]
    timestamp: str
    station_id: int
    station_name: str
    status: str  # "RUNNING" or "STOPPED"
    plc_address: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "station_id": self.station_id,
            "station_name": self.station_name,
            "status": self.status,
            "plc_address": self.plc_address,
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    @classmethod
    def from_row(cls, row: Any) -> StationStatusRecord:
        return cls(
            id=row["id"],
            timestamp=str(row["timestamp"]),
            station_id=int(row["station_id"]),
            station_name=str(row["station_name"]),
            status=str(row["status"]),
            plc_address=str(row["plc_address"]),
        )


@dataclass
class DailySummaryRecord:
    """
    Daily production summary roll-up.
    Matches schema for the 'daily_summary' table.
    """
    id: Optional[int]
    production_date: str
    daily_target: float
    total_production: int
    cumulative_achievement_percent: float
    total_downtime_seconds: float
    total_stops: int
    running_time_seconds: float
    average_speed: float
    average_tact_time: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "production_date": self.production_date,
            "daily_target": round(self.daily_target, 2),
            "total_production": int(self.total_production),
            "cumulative_achievement_percent": round(self.cumulative_achievement_percent, 2),
            "total_downtime_seconds": round(self.total_downtime_seconds, 2),
            "total_stops": int(self.total_stops),
            "running_time_seconds": round(self.running_time_seconds, 2),
            "average_speed": round(self.average_speed, 2),
            "average_tact_time": round(self.average_tact_time, 2),
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    @classmethod
    def from_row(cls, row: Any) -> DailySummaryRecord:
        return cls(
            id=row["id"],
            production_date=str(row["production_date"]),
            daily_target=float(row["daily_target"]),
            total_production=int(row["total_production"]),
            cumulative_achievement_percent=float(row["cumulative_achievement_percent"]),
            total_downtime_seconds=float(row["total_downtime_seconds"]),
            total_stops=int(row["total_stops"]),
            running_time_seconds=float(row["running_time_seconds"]),
            average_speed=float(row["average_speed"]),
            average_tact_time=float(row["average_tact_time"]),
        )
