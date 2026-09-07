"""
Industrial PLC Production Monitor - Production Data & KPI Engine
Phase 2: Core computational engine for tracking continuously increasing production counters,
safe reset/rollover handling, hourly targets, achievement rates, cumulative metrics,
station status normalization, and line operating states.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Tuple

from kpi.models import (
    HourlyProductionRecord,
    KPISnapshot,
    LineStatus,
    LineStatusResult,
    StationKPIStatus,
    StoppedStationInfo,
)
from kpi.tact_time import SpeedScalingConfig, TactTimeCalculator
from plc.plc_data import NormalizedPLCData
from utils.logger import get_logger

logger = get_logger("kpi.engine")

# Fixed industrial physical PLC mapping for the 10 stations
PHYSICAL_STATION_MAP: Dict[int, Tuple[str, str]] = {
    1: ("M550", "Conveyor 1"),
    2: ("M551", "Conveyor 1"),
    3: ("M552", "Conveyor 1"),
    4: ("M553", "Conveyor 1"),
    5: ("M554", "Conveyor 1"),
    6: ("M555", "Conveyor 2"),
    7: ("M556", "Conveyor 2"),
    8: ("M557", "Conveyor 2"),
    9: ("M558", "Conveyor 2"),
    10: ("M559", "Conveyor 2"),
}

DEFAULT_STATION_NAMES: Dict[int, str] = {
    1: "Assembly 1",
    2: "Screw Installation",
    3: "Inspection",
    4: "Riveting",
    5: "Transfer 1",
    6: "Component Insertion",
    7: "Optical Inspection",
    8: "Laser Marking",
    9: "Cleaning",
    10: "Unloading",
}


class KPIEngine:
    """
    Production Data & KPI Engine.
    Processes normalized PLC telemetry packets, computes hourly and cumulative KPIs,
    manages counter deltas and reset conditions, and evaluates overall line status.
    """

    def __init__(
        self,
        assembly_line_name: str = "Assembly Line",
        station_display_names: Optional[Dict[Any, str]] = None,
        production_day_start: str = "08:00",
        target_production_rate: float = 100.0,
        speed_scaling: Optional[SpeedScalingConfig] = None,
    ) -> None:
        self._lock = threading.RLock()

        # 1. Configurable Line & Station identities
        self.assembly_line_name = assembly_line_name
        self.production_day_start = production_day_start
        self.target_production_rate = float(target_production_rate)

        # Build station display names map (1..10)
        self.station_display_names: Dict[int, str] = dict(DEFAULT_STATION_NAMES)
        if station_display_names:
            for k, name in station_display_names.items():
                try:
                    # Support keys like 1 or "1" or "station_1"
                    idx = int(str(k).replace("station_", "").replace("conv1_station", "").replace("conv2_station", ""))
                    if idx in self.station_display_names:
                        self.station_display_names[idx] = str(name)
                except (ValueError, TypeError):
                    continue

        # 2. Tact Time Calculator
        self.speed_config = speed_scaling or SpeedScalingConfig()
        self.tact_calculator = TactTimeCalculator(self.speed_config)

        # 3. State Tracking for Production Counter
        self._last_counter: Optional[int] = None
        self._hour_start_counter: Optional[int] = None
        self._hour_accumulated_production: int = 0
        self._total_accumulated_resets: int = 0

        # Current Hour Bucket Tracking
        self._current_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._current_hour_label: str = self.production_day_start
        self._current_hour_key: Optional[str] = None  # e.g. "2026-09-06_08"
        self._speed_samples: List[float] = []

        # Completed hours storage
        self._completed_hours: List[HourlyProductionRecord] = []
        self._hour_finalized_listeners: List[Callable[[HourlyProductionRecord], None]] = []

        # Station states and line status cache
        self._current_stations: Dict[str, StationKPIStatus] = self._init_default_stations()
        self._current_line_status: LineStatusResult = LineStatusResult(line_status=LineStatus.RUNNING)
        self._daily_target: int = 1000
        self._last_engineering_speed: float = 0.0

    def _init_default_stations(self) -> Dict[str, StationKPIStatus]:
        stations: Dict[str, StationKPIStatus] = {}
        for station_id in range(1, 11):
            plc_addr, conveyor = PHYSICAL_STATION_MAP[station_id]
            disp_name = self.station_display_names.get(station_id, f"Station {station_id}")
            stations[f"station_{station_id}"] = StationKPIStatus(
                station_id=station_id,
                display_name=disp_name,
                plc_address=plc_addr,
                status=True,
                conveyor=conveyor,
            )
        return stations

    def update_assembly_line_name(self, name: str) -> None:
        """Update line name dynamically without source modifications."""
        with self._lock:
            self.assembly_line_name = str(name).strip()
            logger.info("Assembly Line name updated to: '%s'", self.assembly_line_name)

    def update_station_display_name(self, station_id: int, new_display_name: str) -> None:
        """Update display name for a specific station, preserving hardware PLC address."""
        with self._lock:
            if station_id in PHYSICAL_STATION_MAP:
                self.station_display_names[station_id] = new_display_name
                key = f"station_{station_id}"
                if key in self._current_stations:
                    self._current_stations[key].display_name = new_display_name
                logger.info("Station %d display name updated to: '%s'", station_id, new_display_name)

    # -------------------------------------------------------------------------
    # Core Mathematical Formulas (Requirements 4, 5, 6, 7)
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_hourly_achievement(actual_production: int, target_production: float) -> float:
        """
        Formula:
        Hourly Achievement % = (Actual Production / Target Production) * 100
        Safely returns 0.0 if target is zero or negative.
        """
        if target_production <= 0.0:
            return 0.0
        return round((float(actual_production) / float(target_production)) * 100.0, 2)

    @staticmethod
    def calculate_cumulative_achievement(cumulative_actual: int, cumulative_target: float) -> float:
        """
        Formula:
        Cumulative Achievement % = (Cumulative Actual / Cumulative Target) * 100
        Safely returns 0.0 if cumulative target is zero or negative.
        """
        if cumulative_target <= 0.0:
            return 0.0
        return round((float(cumulative_actual) / float(cumulative_target)) * 100.0, 2)

    def hydrate_from_database(self, prod_repo: Any, production_date: str) -> None:
        """
        Hydrate today's completed hours and daily production from SQLite on application startup.
        Ensures today's production is not reset or lost when the application restarts.
        """
        with self._lock:
            try:
                records = prod_repo.get_by_date(production_date)
                if records:
                    self._completed_hours = [
                        HourlyProductionRecord(
                            date=r.production_date,
                            hour_start=r.hour_start,
                            hour_end=r.hour_end,
                            hourly_target=r.hourly_target,
                            actual_production=r.actual_production,
                            hourly_achievement_percent=r.hourly_achievement_percent,
                            cumulative_target=r.cumulative_target,
                            cumulative_actual=r.cumulative_actual,
                            cumulative_achievement_percent=r.cumulative_achievement_percent,
                            tact_time=r.tact_time or 0.0,
                            average_speed=r.average_speed,
                        )
                        for r in records
                    ]
                    logger.info(
                        "Hydrated %d completed hourly record(s) from database for production date %s",
                        len(records),
                        production_date,
                    )
            except Exception as exc:
                logger.warning("Could not hydrate completed hours from database: %s", exc)

    def calculate_counter_delta(self, previous_counter: int, current_counter: int) -> int:
        """
        Calculate production increment between successive counter readings.
        Handles safe counter reset / rollover:
        - Normal increment: current_counter >= previous_counter -> diff
        - 16-bit unsigned rollover (65535 -> small number)
        - 15-bit signed rollover (32767 -> small number)
        - 4-digit BCD / decimal rollover (9999 -> small number)
        - Arbitrary reset (shift change, maintenance reset to 0 or small number)
        Guarantees that negative production is NEVER returned.
        """
        if current_counter >= previous_counter:
            return current_counter - previous_counter

        # Rollover / Reset detected
        # Check standard rollover boundaries
        if previous_counter > 64000 and current_counter < 2000:
            rollover_delta = (65535 - previous_counter) + current_counter + 1
            logger.info("16-bit counter rollover detected: %d -> %d (Delta: %d)", previous_counter, current_counter, rollover_delta)
            return max(0, rollover_delta)
        elif previous_counter > 31500 and current_counter < 1500:
            rollover_delta = (32767 - previous_counter) + current_counter + 1
            logger.info("32767 counter rollover detected: %d -> %d (Delta: %d)", previous_counter, current_counter, rollover_delta)
            return max(0, rollover_delta)
        elif previous_counter > 9800 and current_counter < 200:
            rollover_delta = (9999 - previous_counter) + current_counter + 1
            logger.info("9999 counter rollover detected: %d -> %d (Delta: %d)", previous_counter, current_counter, rollover_delta)
            return max(0, rollover_delta)
        else:
            logger.warning(
                "Production counter reset/rollover detected! (Prev: %d -> Curr: %d). Handling safely.",
                previous_counter,
                current_counter,
            )
            return max(0, current_counter)

    # -------------------------------------------------------------------------
    # Station & Line Status Evaluation (Requirements 10 & 11)
    # -------------------------------------------------------------------------
    def evaluate_line_status(
        self,
        raw_station_bits: Dict[str, bool],
    ) -> LineStatusResult:
        """
        Normalizes station statuses (station_1 .. station_10) and evaluates overall line state.
        If all required stations are active -> RUNNING.
        If 1 or more are stopped -> STOPPED with detailed stopped_stations list.
        """
        stopped_list: List[StoppedStationInfo] = []

        for station_id in range(1, 11):
            plc_addr, conveyor = PHYSICAL_STATION_MAP[station_id]
            disp_name = self.station_display_names.get(station_id, f"Station {station_id}")

            # Check matching keys in raw telemetry (e.g. "M550", "conv1_station1", "station_1")
            status = True
            if plc_addr in raw_station_bits:
                status = bool(raw_station_bits[plc_addr])
            elif f"station_{station_id}" in raw_station_bits:
                status = bool(raw_station_bits[f"station_{station_id}"])
            else:
                # Check conv1/conv2 format
                conv_idx = station_id if station_id <= 5 else (station_id - 5)
                conv_prefix = "conv1" if station_id <= 5 else "conv2"
                legacy_key = f"{conv_prefix}_station{conv_idx}"
                if legacy_key in raw_station_bits:
                    status = bool(raw_station_bits[legacy_key])

            self._current_stations[f"station_{station_id}"] = StationKPIStatus(
                station_id=station_id,
                display_name=disp_name,
                plc_address=plc_addr,
                status=status,
                conveyor=conveyor,
            )

            if not status:
                stopped_list.append(
                    StoppedStationInfo(
                        station_id=station_id,
                        display_name=disp_name,
                        plc_address=plc_addr,
                    )
                )

        overall_status = LineStatus.STOPPED if stopped_list else LineStatus.RUNNING
        return LineStatusResult(line_status=overall_status, stopped_stations=stopped_list)

    # -------------------------------------------------------------------------
    # Telemetry Processing & Real-time Integration (Requirement 12)
    # -------------------------------------------------------------------------
    def process_data(
        self,
        data: NormalizedPLCData,
        override_timestamp: Optional[datetime] = None,
    ) -> KPISnapshot:
        """
        Primary entry point for streaming normalized PLC telemetry into the KPI engine.
        Processes production counters, updates hourly buckets, computes achievements,
        and generates an immutable KPISnapshot. Non-blocking and thread-safe.
        """
        with self._lock:
            # 1. Parse current timestamp & hour bucket using authoritative production day
            dt = override_timestamp or self._parse_iso_or_now(data.timestamp)
            from core.production_day import get_production_date
            prod_date_str = get_production_date(dt, self.production_day_start)
            hour_int = dt.hour
            hour_start_str = f"{hour_int:02d}:00"
            hour_end_str = f"{(hour_int + 1) % 24:02d}:00"
            hour_key = f"{prod_date_str}_{hour_int:02d}"

            # 2. Update speed and physical parameters
            raw_speed = float(data.speed)
            eng_speed = self.speed_config.raw_to_engineering(raw_speed)
            self._last_engineering_speed = eng_speed
            self._speed_samples.append(eng_speed)
            if data.daily_target > 0:
                self._daily_target = int(data.daily_target)

            # 3. Evaluate Station & Line Status
            raw_bits: Dict[str, bool] = dict(data.stations)
            self._current_line_status = self.evaluate_line_status(raw_bits)

            # 4. Handle Hourly Bucket Transitions
            if self._current_hour_key is None:
                # Initialization tick
                self._current_hour_key = hour_key
                self._current_date = prod_date_str
                self._current_hour_label = hour_start_str
                self._hour_start_counter = data.production_counter
                if data.is_connected and data.connection_state.value == "CONNECTED":
                    self._last_counter = data.production_counter
                self._hour_accumulated_production = 0
            elif hour_key != self._current_hour_key:
                # Completed an hour! Finalize previous hour
                self._finalize_completed_hour(
                    date_str=self._current_date,
                    hour_start=self._current_hour_label,
                    hour_end=hour_start_str,
                )
                # Initialize new hour
                self._current_hour_key = hour_key
                self._current_date = prod_date_str
                self._current_hour_label = hour_start_str
                self._hour_start_counter = data.production_counter
                self._hour_accumulated_production = 0
                self._speed_samples = [eng_speed]

            # 5. Process Production Counter Delta safely
            # Only accumulate production if the PLC is actively connected
            is_connected = data.is_connected and (data.connection_state.value == "CONNECTED")
            if is_connected:
                curr_counter = int(data.production_counter)
                if self._last_counter is not None:
                    delta = self.calculate_counter_delta(self._last_counter, curr_counter)
                    self._hour_accumulated_production += delta
                self._last_counter = curr_counter
            else:
                curr_counter = self._last_counter if self._last_counter is not None else int(data.production_counter)

            # 6. Derive Tact Time and Hourly Target
            tact_time = self.tact_calculator.calculate_tact_time_from_speed(eng_speed)
            hourly_target = self.target_production_rate

            # 7. Calculate Current Running Hour Metrics
            actual_hour_prod = self._hour_accumulated_production
            hourly_achieve = self.calculate_hourly_achievement(actual_hour_prod, hourly_target)

            # Cumulative values strictly scoped to the CURRENT production day
            today_completed = [h for h in self._completed_hours if h.date == prod_date_str]
            completed_cum_target = sum(h.hourly_target for h in today_completed)
            completed_cum_actual = sum(h.actual_production for h in today_completed)

            cum_target = completed_cum_target + hourly_target
            cum_actual = completed_cum_actual + actual_hour_prod
            cum_achieve = self.calculate_cumulative_achievement(cum_actual, cum_target)

            daily_target = self._daily_target if self._daily_target > 0 else 1000
            daily_achieve = self.calculate_cumulative_achievement(cum_actual, daily_target)

            avg_speed = (
                sum(self._speed_samples) / len(self._speed_samples)
                if self._speed_samples
                else eng_speed
            )

            current_hour_record = HourlyProductionRecord(
                date=prod_date_str,
                hour_start=hour_start_str,
                hour_end=hour_end_str,
                hourly_target=hourly_target,
                actual_production=actual_hour_prod,
                hourly_achievement_percent=hourly_achieve,
                cumulative_target=cum_target,
                cumulative_actual=cum_actual,
                cumulative_achievement_percent=cum_achieve,
                tact_time=tact_time,
                average_speed=round(avg_speed, 2),
            )

            # Build and return comprehensive KPI snapshot
            return KPISnapshot(
                timestamp=dt.isoformat(),
                assembly_line_name=self.assembly_line_name,
                line_status=self._current_line_status.line_status,
                stopped_stations=self._current_line_status.stopped_stations,
                stations=dict(self._current_stations),
                current_hour=current_hour_record,
                completed_hours=list(self._completed_hours),
                target_production_rate=self.target_production_rate,
                tact_time_seconds=tact_time,
                production_counter_raw=curr_counter,
                daily_target=daily_target,
                daily_production=cum_actual,
                daily_achievement_percent=daily_achieve,
                engineering_speed=eng_speed,
                speed_unit=self.speed_config.engineering_unit,
            )

    def _finalize_completed_hour(self, date_str: str, hour_start: str, hour_end: str) -> None:
        """
        Roll up the finished hour, record its metrics, and link cumulative tallies.
        """
        actual_prod = self._hour_accumulated_production
        target_prod = self.target_production_rate
        achieve_pct = self.calculate_hourly_achievement(actual_prod, target_prod)

        # Cumulative totals scoped to the date of this completed hour
        today_completed = [h for h in self._completed_hours if h.date == date_str]
        prev_cum_target = sum(h.hourly_target for h in today_completed)
        prev_cum_actual = sum(h.actual_production for h in today_completed)

        new_cum_target = prev_cum_target + target_prod
        new_cum_actual = prev_cum_actual + actual_prod
        cum_achieve_pct = self.calculate_cumulative_achievement(new_cum_actual, new_cum_target)

        avg_speed = (
            sum(self._speed_samples) / len(self._speed_samples)
            if self._speed_samples
            else self._last_engineering_speed
        )
        tact_time = self.tact_calculator.calculate_tact_time_from_speed(avg_speed)

        record = HourlyProductionRecord(
            date=date_str,
            hour_start=hour_start,
            hour_end=hour_end,
            hourly_target=target_prod,
            actual_production=actual_prod,
            hourly_achievement_percent=achieve_pct,
            cumulative_target=new_cum_target,
            cumulative_actual=new_cum_actual,
            cumulative_achievement_percent=cum_achieve_pct,
            tact_time=tact_time,
            average_speed=round(avg_speed, 2),
        )
        self._completed_hours.append(record)
        logger.info(
            "Hour finalized [%s - %s]: Target=%.0f, Actual=%d (Achieve=%.1f%%) | Cumulative: %d/%.0f (%.1f%%)",
            hour_start,
            hour_end,
            target_prod,
            actual_prod,
            achieve_pct,
            new_cum_actual,
            new_cum_target,
            cum_achieve_pct,
        )
        self._notify_hour_finalized(record)

    def register_hour_finalized_listener(self, listener: Callable[[HourlyProductionRecord], None]) -> None:
        """Register callback for when an hour bucket finalizes."""
        with self._lock:
            if listener not in self._hour_finalized_listeners:
                self._hour_finalized_listeners.append(listener)

    def _notify_hour_finalized(self, record: HourlyProductionRecord) -> None:
        for listener in list(self._hour_finalized_listeners):
            try:
                listener(record)
            except Exception as exc:
                logger.error("Error in hour finalized listener: %s", exc)

    def add_completed_hour_record(
        self,
        date_str: str,
        hour_start: str,
        hour_end: str,
        actual_production: int,
        hourly_target: Optional[float] = None,
        tact_time: float = 0.0,
        average_speed: Optional[float] = None,
    ) -> HourlyProductionRecord:
        """
        Directly record a completed hour. Useful for deterministic simulation,
        historical playback, and unit test scenarios.
        """
        with self._lock:
            target = hourly_target if hourly_target is not None else self.target_production_rate
            hourly_pct = self.calculate_hourly_achievement(actual_production, target)

            prev_target = sum(h.hourly_target for h in self._completed_hours)
            prev_actual = sum(h.actual_production for h in self._completed_hours)

            cum_target = prev_target + target
            cum_actual = prev_actual + actual_production
            cum_pct = self.calculate_cumulative_achievement(cum_actual, cum_target)

            record = HourlyProductionRecord(
                date=date_str,
                hour_start=hour_start,
                hour_end=hour_end,
                hourly_target=target,
                actual_production=actual_production,
                hourly_achievement_percent=hourly_pct,
                cumulative_target=cum_target,
                cumulative_actual=cum_actual,
                cumulative_achievement_percent=cum_pct,
                tact_time=tact_time,
                average_speed=average_speed,
            )
            self._completed_hours.append(record)
            self._notify_hour_finalized(record)
            return record

    def get_completed_hours(self) -> List[HourlyProductionRecord]:
        with self._lock:
            return list(self._completed_hours)

    def get_cumulative_metrics(self) -> Dict[str, Any]:
        """
        Compute total cumulative metrics across all finalized completed hours.
        """
        with self._lock:
            cum_target = sum(h.hourly_target for h in self._completed_hours)
            cum_actual = sum(h.actual_production for h in self._completed_hours)
            cum_pct = self.calculate_cumulative_achievement(cum_actual, cum_target)
            return {
                "completed_hours_count": len(self._completed_hours),
                "cumulative_target": cum_target,
                "cumulative_actual": cum_actual,
                "cumulative_achievement_percent": cum_pct,
            }

    @staticmethod
    def _parse_iso_or_now(ts_str: Optional[str]) -> datetime:
        if not ts_str:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
