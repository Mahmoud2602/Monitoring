"""
Industrial PLC Production Monitor - Data Models & Register Mapping

Provides normalized dataclasses and schema mappings for translating raw PLC
D-registers and M-bits into structured, business-ready models.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ConnectionState(str, Enum):
    """
    PLC Communication link states.
    """
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class StationStatus:
    """
    Normalized representation of a single conveyor station sensor / bit.
    """
    station_key: str
    address: str
    conveyor: str
    station_index: int
    is_active: bool
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "station_key": self.station_key,
            "address": self.address,
            "conveyor": self.conveyor,
            "station_index": self.station_index,
            "is_active": self.is_active,
            "description": self.description,
        }


@dataclass
class NormalizedPLCData:
    """
    Normalized snapshot of all industrial telemetry polled from the PLC.
    Guarantees consistent data structure regardless of underlying PLC brand or protocol.
    """
    timestamp: str
    connected: bool
    connection_state: ConnectionState
    speed: float
    speed_setpoint: float
    production_counter: int
    daily_target: int
    stations: Dict[str, bool] = field(default_factory=dict)
    station_details: Dict[str, StationStatus] = field(default_factory=dict)
    scan_time_ms: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self, include_metadata: bool = False) -> Dict[str, Any]:
        """
        Export normalized dictionary matching the project specifications.
        """
        data: Dict[str, Any] = {
            "timestamp": self.timestamp,
            "connected": self.connected,
            "speed": round(self.speed, 2),
            "speed_setpoint": round(self.speed_setpoint, 2),
            "production_counter": int(self.production_counter),
            "daily_target": int(self.daily_target),
            "stations": dict(self.stations),
        }
        if include_metadata:
            data["connection_state"] = self.connection_state.value
            data["scan_time_ms"] = round(self.scan_time_ms, 2)
            data["error_message"] = self.error_message
        return data

    def to_json(self, indent: Optional[int] = 2, include_metadata: bool = False) -> str:
        """
        Serialize normalized snapshot to standard JSON.
        """
        return json.dumps(self.to_dict(include_metadata=include_metadata), indent=indent)

    @classmethod
    def create_empty(
        cls,
        state: ConnectionState = ConnectionState.DISCONNECTED,
        error_message: Optional[str] = None,
    ) -> NormalizedPLCData:
        """
        Construct a default safe snapshot when disconnected or during read errors.
        """
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            timestamp=now,
            connected=(state == ConnectionState.CONNECTED),
            connection_state=state,
            speed=0.0,
            speed_setpoint=0.0,
            production_counter=0,
            daily_target=0,
            stations={},
            station_details={},
            scan_time_ms=0.0,
            error_message=error_message,
        )


class PLCMappingConfig:
    """
    Loads, validates, and manages the decoupled address mapping configuration.
    Translates raw D-register and M-bit reads into the normalized data model.
    """

    def __init__(self, mapping_dict: Dict[str, Any]) -> None:
        self._raw_mapping = mapping_dict
        self._registers = mapping_dict.get("registers", {})
        self._stations = mapping_dict.get("stations", {})
        self._validate()

    @classmethod
    def from_file(cls, filepath: str) -> PLCMappingConfig:
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)
        return cls(data)

    def _validate(self) -> None:
        if not isinstance(self._registers, dict) or not isinstance(self._stations, dict):
            raise ValueError("Invalid mapping schema: 'registers' and 'stations' must be objects.")

        # Ensure required register keys exist
        required_registers = ["speed", "speed_setpoint", "production_counter", "daily_target"]
        for key in required_registers:
            if key not in self._registers:
                raise KeyError(f"Missing required register mapping for key: '{key}'")
            if "address" not in self._registers[key]:
                raise KeyError(f"Register '{key}' missing required 'address' property.")

        # Ensure station entries have address
        for station_key, info in self._stations.items():
            if "address" not in info:
                raise KeyError(f"Station '{station_key}' missing required 'address' property.")

    @property
    def register_addresses(self) -> List[str]:
        """List of all physical PLC register addresses to read (e.g. ['D450', 'D451', ...])."""
        return [info["address"] for info in self._registers.values()]

    @property
    def station_addresses(self) -> List[str]:
        """List of all physical PLC bit addresses to read (e.g. ['M550', 'M551', ...])."""
        return [info["address"] for info in self._stations.values()]

    def get_register_address(self, register_key: str) -> str:
        return self._registers[register_key]["address"]

    def get_station_address(self, station_key: str) -> str:
        return self._stations[station_key]["address"]

    def map_raw_telemetry(
        self,
        raw_registers: Dict[str, Any],
        raw_bits: Dict[str, bool],
        connection_state: ConnectionState,
        scan_time_ms: float = 0.0,
        error_message: Optional[str] = None,
    ) -> NormalizedPLCData:
        """
        Map low-level driver results (keyed by physical address like D450, M550)
        into the standardized NormalizedPLCData structure.
        """
        now = datetime.now(timezone.utc).isoformat()
        is_connected = (connection_state == ConnectionState.CONNECTED)

        # Helper to extract and scale register value
        def extract_register(key: str, default: float = 0.0) -> float:
            reg_info = self._registers.get(key, {})
            addr = reg_info.get("address")
            scale = float(reg_info.get("scale", 1.0))
            raw_val = raw_registers.get(addr)
            if raw_val is None:
                return default
            try:
                return float(raw_val) * scale
            except (ValueError, TypeError):
                return default

        speed = extract_register("speed", default=0.0)
        speed_setpoint = extract_register("speed_setpoint", default=0.0)
        production_counter = int(extract_register("production_counter", default=0))
        daily_target = int(extract_register("daily_target", default=0))

        # Map station status bits
        stations_dict: Dict[str, bool] = {}
        station_details_dict: Dict[str, StationStatus] = {}

        for station_key, info in self._stations.items():
            addr = info["address"]
            active = bool(raw_bits.get(addr, False))
            stations_dict[station_key] = active
            station_details_dict[station_key] = StationStatus(
                station_key=station_key,
                address=addr,
                conveyor=info.get("conveyor", "Conveyor"),
                station_index=int(info.get("station_index", 0)),
                is_active=active,
                description=info.get("description", ""),
            )

        return NormalizedPLCData(
            timestamp=now,
            connected=is_connected,
            connection_state=connection_state,
            speed=speed,
            speed_setpoint=speed_setpoint,
            production_counter=production_counter,
            daily_target=daily_target,
            stations=stations_dict,
            station_details=station_details_dict,
            scan_time_ms=scan_time_ms,
            error_message=error_message,
        )
