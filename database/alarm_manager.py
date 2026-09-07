"""
Industrial PLC Production Monitor - Alarm Event Manager
Phase 3: Real-time alarm lifecycle management, active alarms registry,
severity triage, and historical alarm persistence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Callable, Dict, List, Optional

from database.models import AlarmEventRecord
from database.repositories import AlarmRepository
from utils.logger import get_logger

logger = get_logger("database.alarm")


class AlarmManager:
    """
    Dedicated industrial alarm management engine.
    Supports:
    - Raising new alarms with severity levels (INFO, WARNING, CRITICAL)
    - Active alarm tracking and deduplication
    - Clearing active alarms individually or by code
    - Calculating alarm active durations
    - Multiple simultaneous active alarms across stations
    - Event listener notifications for UI/monitoring subscribers
    """

    def __init__(
        self,
        alarm_repo: AlarmRepository,
        production_day_start: str = "08:00",
    ) -> None:
        self.alarm_repo = alarm_repo
        self.production_day_start = production_day_start
        self._lock = threading.RLock()

        # Cache of active alarms: (alarm_code, station_id) -> AlarmEventRecord
        self._active_alarms: Dict[tuple[str, Optional[int]], AlarmEventRecord] = {}

        # Alarm listeners: (action: "RAISED"|"CLEARED", alarm: AlarmEventRecord)
        self._listeners: List[Callable[[str, AlarmEventRecord], None]] = []

        # Load active alarms from database on startup
        self._load_active_alarms()

    def _load_active_alarms(self) -> None:
        with self._lock:
            try:
                active_db = self.alarm_repo.get_active_alarms()
                for rec in active_db:
                    key = (rec.alarm_code, rec.station_id)
                    self._active_alarms[key] = rec
                if active_db:
                    logger.info("Loaded %d active alarm(s) from database.", len(active_db))
            except Exception as exc:
                logger.error("Failed to load active alarms from database: %s", exc)

    def register_alarm_listener(self, listener: Callable[..., None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def register_listener(self, listener: Callable[..., None]) -> None:
        """Alias for register_alarm_listener, supporting both (alarm) and (action, alarm) callbacks."""
        self.register_alarm_listener(listener)

    def unregister_alarm_listener(self, listener: Callable[..., None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def unregister_listener(self, listener: Callable[..., None]) -> None:
        self.unregister_alarm_listener(listener)

    def _notify(self, action: str, alarm: AlarmEventRecord) -> None:
        for listener in list(self._listeners):
            try:
                try:
                    listener(action, alarm)
                except TypeError:
                    listener(alarm)
            except Exception as exc:
                logger.error("Error executing alarm listener: %s", exc)

    def raise_alarm(
        self,
        alarm_code: str,
        alarm_message: str,
        severity: str = "WARNING",
        station_id: Optional[int] = None,
        station_name: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        production_date: Optional[str] = None,
    ) -> AlarmEventRecord:
        """
        Raise an industrial alarm. If the exact alarm is already active for this station,
        returns the existing active alarm to prevent duplicate alarm flooding.
        """
        now = timestamp or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        from core.production_day import get_production_date
        prod_date = production_date or get_production_date(now, self.production_day_start)

        key = (alarm_code, station_id)
        with self._lock:
            existing = self._active_alarms.get(key)
            if existing is not None:
                # Alarm already active
                return existing

            alarm_id = self.alarm_repo.create_alarm(
                timestamp=now_iso,
                alarm_code=alarm_code,
                alarm_message=alarm_message,
                severity=severity.upper(),
                station_id=station_id,
                station_name=station_name,
                production_date=prod_date,
            )

            record = AlarmEventRecord(
                id=alarm_id,
                timestamp=now_iso,
                alarm_code=alarm_code,
                alarm_message=alarm_message,
                severity=severity.upper(),
                station_id=station_id,
                station_name=station_name,
                active=True,
                cleared_at=None,
                duration_seconds=None,
                production_date=prod_date,
            )
            self._active_alarms[key] = record

            logger.warning(
                "ALARM RAISED [%s] Code: %s, Station: %s, Message: %s",
                severity.upper(),
                alarm_code,
                f"Station {station_id}" if station_id is not None else "Line",
                alarm_message,
            )

            self._notify("RAISED", record)
            return record

    def clear_alarm(
        self,
        alarm_code: str,
        station_id: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[AlarmEventRecord]:
        """
        Clear an active alarm condition by code and station.
        Calculates exact active duration in seconds and updates database.
        """
        now = timestamp or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        key = (alarm_code, station_id)
        with self._lock:
            record = self._active_alarms.pop(key, None)
            if record is None:
                # Check if it was without station_id
                if station_id is not None:
                    record = self._active_alarms.pop((alarm_code, None), None)

            if record is not None and record.id is not None:
                try:
                    st = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                    en = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
                    dur = max(0.0, round((en - st).total_seconds(), 2))
                except Exception:
                    dur = 0.0

                self.alarm_repo.clear_alarm(record.id, now_iso, dur)
                record.active = False
                record.cleared_at = now_iso
                record.duration_seconds = dur

                logger.info(
                    "ALARM CLEARED Code: %s, Station: %s (Duration: %.1fs)",
                    alarm_code,
                    f"Station {station_id}" if station_id is not None else "Line",
                    dur,
                )
                self._notify("CLEARED", record)
                return record

            return None

    def get_active_alarms(self) -> List[AlarmEventRecord]:
        """Return list of all currently active alarms."""
        with self._lock:
            return list(self._active_alarms.values())

    def get_alarm_history(
        self,
        start_date: str,
        end_date: str,
        severity: Optional[str] = None,
        station_id: Optional[int] = None,
    ) -> List[AlarmEventRecord]:
        """Query historical alarm events across a date range."""
        return self.alarm_repo.get_alarms_by_date_range(
            start_date=start_date,
            end_date=end_date,
            severity=severity,
            station_id=station_id,
        )
