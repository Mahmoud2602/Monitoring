"""
Industrial PLC Production Monitor - Downtime Event Manager
Phase 3: State-change detection, continuous stop duration calculation,
safe restart recovery, and independent multi-station stoppage tracking.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from database.models import DowntimeEventRecord, StationStatusRecord
from database.repositories import DowntimeRepository, StationStatusRepository
from utils.logger import get_logger

logger = get_logger("database.downtime")


class DowntimeManager:
    """
    Manages downtime event lifecycles:
    - Transitions RUNNING -> STOPPED: Initiates a new downtime event
    - Transitions STOPPED -> RUNNING: Concludes the active downtime event with exact duration
    - Avoids duplicate records during steady running or continuous stopping
    - Tracks multiple stations stopping independently
    - Safely recovers existing open events across application restarts
    """

    def __init__(
        self,
        downtime_repo: DowntimeRepository,
        status_repo: StationStatusRepository,
        production_day_start: str = "08:00",
    ) -> None:
        self.downtime_repo = downtime_repo
        self.status_repo = status_repo
        self.production_day_start = production_day_start
        self._lock = threading.RLock()

        # Cache of current station states: station_id -> bool (True=RUNNING, False=STOPPED)
        self._station_states: Dict[int, bool] = {}

        # Active in-progress downtime events: station_id -> DowntimeEventRecord
        self._active_events: Dict[int, DowntimeEventRecord] = {}

        # Listeners for event start/end callbacks
        self._event_listeners: List[Callable[[str, DowntimeEventRecord], None]] = []

        # Perform initial recovery of open events from database
        self._recover_open_events_on_startup()

    def _recover_open_events_on_startup(self) -> None:
        """
        Query database on startup for unclosed downtime events.
        Maintains open events in memory so that when stations restart or resume,
        the existing events are cleanly closed without duplication or corruption.
        """
        with self._lock:
            try:
                open_events = self.downtime_repo.get_open_events()
                for event in open_events:
                    self._active_events[event.station_id] = event
                    # Initially mark station as stopped until verified by first telemetry scan
                    self._station_states[event.station_id] = False
                    logger.info(
                        "Recovered open downtime event #%d for Station %d (%s) started at %s",
                        event.id,
                        event.station_id,
                        event.station_name,
                        event.start_time,
                    )
                if open_events:
                    logger.info("Successfully recovered %d active downtime event(s) from database.", len(open_events))
            except Exception as exc:
                logger.error("Failed to recover open downtime events on startup: %s", exc)

    def register_event_listener(self, listener: Callable[[str, DowntimeEventRecord], None]) -> None:
        """Register listener for ("START"|"END", DowntimeEventRecord) notifications."""
        with self._lock:
            if listener not in self._event_listeners:
                self._event_listeners.append(listener)

    def unregister_event_listener(self, listener: Callable[[str, DowntimeEventRecord], None]) -> None:
        with self._lock:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

    def _notify(self, action: str, record: DowntimeEventRecord) -> None:
        for listener in list(self._event_listeners):
            try:
                listener(action, record)
            except Exception as exc:
                logger.error("Error in downtime event listener: %s", exc)

    def process_station_states(
        self,
        station_states: Dict[int, Tuple[str, str, bool]],
        timestamp: Optional[datetime] = None,
        production_date: Optional[str] = None,
    ) -> List[DowntimeEventRecord]:
        """
        Evaluate a telemetry scan for state transitions across all workstations.
        station_states format: {station_id: (station_name, plc_address, is_running)}
        
        Returns any newly started or closed downtime events processed during this tick.
        """
        now = timestamp or datetime.now(timezone.utc)
        now_iso = now.isoformat()
        current_prod_date = production_date or self.get_production_date(now)

        processed_events: List[DowntimeEventRecord] = []

        with self._lock:
            for station_id, (name, plc_addr, is_running) in station_states.items():
                prev_state = self._station_states.get(station_id)

                if prev_state is None:
                    # First observation of this station
                    self._station_states[station_id] = is_running
                    # Check if we recovered an open event for this station
                    existing_open = self._active_events.get(station_id)

                    if not is_running:
                        # Station is STOPPED on startup
                        if existing_open is None:
                            # Brand new stop
                            event_id = self.downtime_repo.create_event(
                                station_id=station_id,
                                station_name=name,
                                start_time=now_iso,
                                production_date=current_prod_date,
                            )
                            new_event = DowntimeEventRecord(
                                id=event_id,
                                station_id=station_id,
                                station_name=name,
                                start_time=now_iso,
                                end_time=None,
                                duration_seconds=None,
                                production_date=current_prod_date,
                            )
                            self._active_events[station_id] = new_event
                            self.status_repo.record_transition(
                                timestamp=now_iso,
                                station_id=station_id,
                                station_name=name,
                                status="STOPPED",
                                plc_address=plc_addr,
                            )
                            processed_events.append(new_event)
                            self._notify("START", new_event)
                            logger.warning(
                                "Downtime event started: Station %d (%s) STOPPED at %s",
                                station_id,
                                name,
                                now_iso,
                            )
                    else:
                        # Station is RUNNING on startup
                        if existing_open is not None:
                            # Recovered open event resolved while system was offline
                            dur = self._calc_duration_seconds(existing_open.start_time, now_iso)
                            self.downtime_repo.close_event(existing_open.id, now_iso, dur)
                            existing_open.end_time = now_iso
                            existing_open.duration_seconds = dur
                            del self._active_events[station_id]
                            self.status_repo.record_transition(
                                timestamp=now_iso,
                                station_id=station_id,
                                station_name=name,
                                status="RUNNING",
                                plc_address=plc_addr,
                            )
                            processed_events.append(existing_open)
                            self._notify("END", existing_open)
                            logger.info(
                                "Resolved orphaned downtime event #%d for Station %d on startup (Duration: %.1fs)",
                                existing_open.id,
                                station_id,
                                dur,
                            )
                    continue

                # Normal cycle state transition detection
                if prev_state is True and is_running is False:
                    # Transition: RUNNING -> STOPPED (Downtime Event Starts)
                    self._station_states[station_id] = False
                    event_id = self.downtime_repo.create_event(
                        station_id=station_id,
                        station_name=name,
                        start_time=now_iso,
                        production_date=current_prod_date,
                    )
                    new_event = DowntimeEventRecord(
                        id=event_id,
                        station_id=station_id,
                        station_name=name,
                        start_time=now_iso,
                        end_time=None,
                        duration_seconds=None,
                        production_date=current_prod_date,
                    )
                    self._active_events[station_id] = new_event

                    # Log meaningful state transition
                    self.status_repo.record_transition(
                        timestamp=now_iso,
                        station_id=station_id,
                        station_name=name,
                        status="STOPPED",
                        plc_address=plc_addr,
                    )
                    processed_events.append(new_event)
                    self._notify("START", new_event)
                    logger.warning(
                        "Downtime event started: Station %d (%s) STOPPED at %s (Event #%d)",
                        station_id,
                        name,
                        now_iso,
                        event_id,
                    )

                elif prev_state is False and is_running is True:
                    # Transition: STOPPED -> RUNNING (Downtime Event Concludes)
                    self._station_states[station_id] = True
                    active_event = self._active_events.pop(station_id, None)

                    if active_event is not None and active_event.id is not None:
                        dur = self._calc_duration_seconds(active_event.start_time, now_iso)
                        self.downtime_repo.close_event(active_event.id, now_iso, dur)
                        active_event.end_time = now_iso
                        active_event.duration_seconds = dur
                        processed_events.append(active_event)
                        self._notify("END", active_event)
                        logger.info(
                            "Downtime event ended: Station %d (%s) RUNNING at %s (Duration: %.1fs, Event #%d)",
                            station_id,
                            name,
                            now_iso,
                            dur,
                            active_event.id,
                        )
                    else:
                        # Fallback: check DB for any unclosed open event for this station
                        db_open = self.downtime_repo.get_open_event_for_station(station_id)
                        if db_open and db_open.id:
                            dur = self._calc_duration_seconds(db_open.start_time, now_iso)
                            self.downtime_repo.close_event(db_open.id, now_iso, dur)
                            db_open.end_time = now_iso
                            db_open.duration_seconds = dur
                            processed_events.append(db_open)
                            self._notify("END", db_open)

                    # Log meaningful state transition
                    self.status_repo.record_transition(
                        timestamp=now_iso,
                        station_id=station_id,
                        station_name=name,
                        status="RUNNING",
                        plc_address=plc_addr,
                    )

                # Continuous state (RUNNING==RUNNING or STOPPED==STOPPED): NO DUPLICATES CREATED!

        return processed_events

    def get_active_downtime_duration(
        self,
        station_id: int,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Dynamically calculate active downtime duration in seconds for an open stoppage.
        Returns None if station is currently RUNNING.
        """
        with self._lock:
            event = self._active_events.get(station_id)
            if not event:
                return None
            curr_time = (now or datetime.now(timezone.utc)).isoformat()
            return self._calc_duration_seconds(event.start_time, curr_time)

    def get_active_events(self) -> List[DowntimeEventRecord]:
        """Return list of all currently active downtime records."""
        with self._lock:
            return list(self._active_events.values())

    get_active_downtime_events = get_active_events

    def is_station_stopped(self, station_id: int) -> bool:
        with self._lock:
            return station_id in self._active_events

    def get_total_active_downtime_seconds(self, now: Optional[datetime] = None) -> float:
        """Sum active seconds across all currently stopped stations."""
        with self._lock:
            total = 0.0
            curr_iso = (now or datetime.now(timezone.utc)).isoformat()
            for event in self._active_events.values():
                total += self._calc_duration_seconds(event.start_time, curr_iso)
            return round(total, 2)

    @staticmethod
    def _calc_duration_seconds(start_iso: str, end_iso: str) -> float:
        """Parse ISO timestamps and calculate elapsed duration in seconds."""
        try:
            st = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            en = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            diff = (en - st).total_seconds()
            return max(0.0, round(diff, 2))
        except Exception:
            return 0.0

    def get_production_date(self, dt: datetime) -> str:
        """
        Resolve industrial production date based on configurable shift start (e.g. "08:00").
        If time is before day start, date belongs to previous calendar day.
        """
        from core.production_day import get_production_date
        return get_production_date(dt, self.production_day_start)
