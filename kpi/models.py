"""
Industrial PLC Production Monitor - KPI & Production Data Models
Defines immutable/normalized models for hourly production buckets, station telemetry,
line status assessments, and real-time KPI snapshots.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LineStatus(str, Enum):
    """
    Overall production line operating state.
    """
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


@dataclass
class StationKPIStatus:
    """
    Normalized data structure for an individual workstation.
    Decouples user-facing display names from hardware PLC bit addresses.
    """
    station_id: int
    display_name: str
    plc_address: str
    status: bool
    conveyor: str = "Conveyor 1"

    def to_dict(self, include_conveyor: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "station_id": self.station_id,
            "display_name": self.display_name,
            "plc_address": self.plc_address,
            "status": self.status,
        }
        if include_conveyor:
            result["conveyor"] = self.conveyor
        return result


@dataclass
class StoppedStationInfo:
    """
    Lightweight descriptor of a station triggering a line stoppage.
    """
    station_id: int
    display_name: str
    plc_address: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station_id": self.station_id,
            "display_name": self.display_name,
            "plc_address": self.plc_address,
        }


@dataclass
class LineStatusResult:
    """
    Calculated overall line operational state and list of stopped stations.
    """
    line_status: LineStatus
    stopped_stations: List[StoppedStationInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_status": self.line_status.value,
            "stopped_stations": [s.to_dict() for s in self.stopped_stations],
        }


@dataclass
class HourlyProductionRecord:
    """
    Represents one discrete production hour bucket.
    Matches the schema requirements in Phase 2 Section 8.
    """
    date: str
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

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "date": self.date,
            "hour_start": self.hour_start,
            "hour_end": self.hour_end,
            "hourly_target": round(self.hourly_target, 2),
            "actual_production": int(self.actual_production),
            "hourly_achievement_percent": round(self.hourly_achievement_percent, 2),
            "cumulative_target": round(self.cumulative_target, 2),
            "cumulative_actual": int(self.cumulative_actual),
            "cumulative_achievement_percent": round(self.cumulative_achievement_percent, 2),
            "tact_time": round(self.tact_time, 2),
        }
        if self.average_speed is not None:
            data["average_speed"] = round(self.average_speed, 2)
        return data

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class KPISnapshot:
    """
    Comprehensive real-time production KPI snapshot.
    Combines current line state, running hour telemetry, cumulative targets, and station statuses.
    """
    timestamp: str
    assembly_line_name: str
    line_status: LineStatus
    stopped_stations: List[StoppedStationInfo]
    stations: Dict[str, StationKPIStatus]  # e.g. "station_1" .. "station_10"
    current_hour: HourlyProductionRecord
    completed_hours: List[HourlyProductionRecord]
    target_production_rate: float
    tact_time_seconds: float
    production_counter_raw: int
    daily_target: int
    engineering_speed: float
    speed_unit: str = "m/min"
    daily_production: int = 0
    daily_achievement_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "assembly_line_name": self.assembly_line_name,
            "line_status": self.line_status.value,
            "stopped_stations": [s.to_dict() for s in self.stopped_stations],
            "stations": {
                k: v.to_dict() for k, v in self.stations.items()
            },
            "current_hour": self.current_hour.to_dict(),
            "completed_hours": [h.to_dict() for h in self.completed_hours],
            "target_production_rate": round(self.target_production_rate, 2),
            "tact_time_seconds": round(self.tact_time_seconds, 2),
            "production_counter_raw": int(self.production_counter_raw),
            "daily_target": int(self.daily_target),
            "daily_production": int(self.daily_production),
            "daily_achievement_percent": round(self.daily_achievement_percent, 2),
            "engineering_speed": round(self.engineering_speed, 2),
            "speed_unit": self.speed_unit,
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
