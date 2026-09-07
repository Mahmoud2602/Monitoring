"""
Industrial PLC Production Monitor - Core Data Manager
Phase 2: Coordinates between PLC communication layer, KPI & production analytics engine,
and application presentation / telemetry subscribers.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from database.alarm_manager import AlarmManager
from database.database_manager import DatabaseManager
from database.downtime_manager import DowntimeManager
from database.models import (
    AlarmEventRecord,
    DailySummaryRecord,
    DowntimeEventRecord,
    ProductionDataRecord,
    StationStatusRecord,
)
from database.query_service import HistoricalQueryService
from database.repositories import (
    AlarmRepository,
    DailySummaryRepository,
    DowntimeRepository,
    ProductionDataRepository,
    StationStatusRepository,
)
from database.summary_service import DailySummaryService
from kpi.kpi_engine import KPIEngine
from kpi.models import HourlyProductionRecord, KPISnapshot
from kpi.tact_time import SpeedScalingConfig
from plc.base_driver import BasePLCDriver
from plc.ethernet_driver import EthernetPLCDriver
from plc.plc_client import PLCClient
from plc.plc_data import NormalizedPLCData, PLCMappingConfig
from plc.simulated_driver import SimulatedPLCDriver
from utils.logger import get_logger

logger = get_logger("core.data_manager")


class DataManager:
    """
    Central business coordinator for the industrial production monitoring system.
    Phase 3: Integrates the SQLite historical layer, downtime event manager,
    alarm engine, summary service, and analytics query API.
    """

    def __init__(
        self,
        settings_path: str = "config/settings.json",
        mapping_path: str = "config/plc_mapping.json",
        custom_driver: Optional[BasePLCDriver] = None,
        db_path: Optional[str] = None,
        simulation_mode: Optional[bool] = None,
    ) -> None:
        self.settings_path = settings_path
        self.mapping_path = mapping_path

        # 1. Load Configurations
        self.settings = self._load_json(settings_path)
        self.mapping_config = PLCMappingConfig.from_file(mapping_path)

        # 2. Extract PLC & Polling settings
        plc_cfg = self.settings.get("plc", {})
        polling_cfg = self.settings.get("polling", {})
        if simulation_mode is not None:
            self.simulation_mode = bool(simulation_mode)
        else:
            self.simulation_mode = bool(self.settings.get("simulation_mode", True))
        self.cycle_time_ms: int = int(polling_cfg.get("cycle_time_ms", 500))
        self.plc_ip: str = str(plc_cfg.get("ip_address", "192.168.1.10"))
        self.plc_port: int = int(plc_cfg.get("port", 502))
        self.timeout_sec: float = float(plc_cfg.get("timeout_seconds", 2.0))
        self.retry_interval_sec: float = float(plc_cfg.get("retry_interval_seconds", 3.0))
        self.max_retries: Optional[int] = plc_cfg.get("max_retries", 5)

        # 3. Instantiate Driver (Simulation or Real/Custom)
        if custom_driver is not None:
            self.driver = custom_driver
            logger.info("Using custom user-provided PLC driver: %s", type(self.driver).__name__)
        elif self.simulation_mode:
            sim_params = self.settings.get("simulation_settings", {})
            self.driver = SimulatedPLCDriver(
                host=self.plc_ip,
                port=self.plc_port,
                timeout=self.timeout_sec,
                driver_params=sim_params,
            )
            logger.info("Operating in SIMULATION MODE with SimulatedPLCDriver.")
        else:
            logger.info("Operating in REAL PLC HARDWARE MODE targeting %s:%d", self.plc_ip, self.plc_port)
            driver_params = plc_cfg.get("driver_params", {})
            self.driver = EthernetPLCDriver(
                host=self.plc_ip,
                port=self.plc_port,
                timeout=self.timeout_sec,
                driver_params=driver_params,
            )

        # 4. Instantiate Isolated PLC Client
        self.client = PLCClient(
            driver=self.driver,
            mapping=self.mapping_config,
            cycle_time_ms=self.cycle_time_ms,
            retry_interval_seconds=self.retry_interval_sec,
            max_retries=self.max_retries,
        )

        # 5. Instantiate Production Data & KPI Engine (Phase 2)
        line_cfg = self.settings.get("assembly_line", {})
        station_names_cfg = self.settings.get("station_display_names", {})

        speed_scaling_raw = line_cfg.get("speed_scaling", {})
        speed_scaling = SpeedScalingConfig(
            raw_address=speed_scaling_raw.get("raw_address", "D450"),
            scale_factor=float(speed_scaling_raw.get("scale_factor", 1.0)),
            engineering_unit=str(speed_scaling_raw.get("engineering_unit", "m/min")),
            product_pitch_meters=float(line_cfg.get("product_pitch_meters", 0.75)),
        )

        self.production_day_start = str(line_cfg.get("production_day_start", "08:00"))
        self.kpi_engine = KPIEngine(
            assembly_line_name=str(line_cfg.get("name", "Assembly Line")),
            station_display_names=station_names_cfg,
            production_day_start=self.production_day_start,
            target_production_rate=float(line_cfg.get("target_rate_pcs_per_hour", 100.0)),
            speed_scaling=speed_scaling,
        )

        # 6. Database Layer & Services (Phase 3)
        db_cfg = self.settings.get("database", {})
        self.db_path = db_path or str(db_cfg.get("db_path", "production_monitor.db"))
        self.db_manager = DatabaseManager(self.db_path)

        self.prod_repo = ProductionDataRepository(self.db_manager)
        self.downtime_repo = DowntimeRepository(self.db_manager)
        self.alarm_repo = AlarmRepository(self.db_manager)
        self.status_repo = StationStatusRepository(self.db_manager)
        self.summary_repo = DailySummaryRepository(self.db_manager)

        self.downtime_manager = DowntimeManager(
            downtime_repo=self.downtime_repo,
            status_repo=self.status_repo,
            production_day_start=self.production_day_start,
        )
        self.alarm_manager = AlarmManager(
            alarm_repo=self.alarm_repo,
            production_day_start=self.production_day_start,
        )
        self.summary_service = DailySummaryService(self.db_manager)
        self.query_service = HistoricalQueryService(
            self.db_manager,
            production_day_start=self.production_day_start,
        )

        # Auto-persist finalized hour records to database
        self.kpi_engine.register_hour_finalized_listener(self._on_hour_finalized)

        # Hydrate KPI engine with today's completed production hours from database
        try:
            from core.production_day import get_production_date
            current_prod_date = get_production_date(self.production_day_start)
            self.kpi_engine.hydrate_from_database(self.prod_repo, current_prod_date)
        except Exception as exc:
            logger.warning("Could not hydrate KPI engine on startup: %s", exc)

        # 7. Internal cache and listeners
        self._external_listeners: List[Callable[[NormalizedPLCData], None]] = []
        self._kpi_listeners: List[Callable[[KPISnapshot], None]] = []
        self._latest_kpi: Optional[KPISnapshot] = None
        self.client.register_listener(self._on_plc_data_received)

    @staticmethod
    def _load_json(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def _on_plc_data_received(self, data: NormalizedPLCData) -> None:
        """Internal callback invoked whenever the PLC client completes a scan."""
        # Step 1: Real-time calculation through KPI engine
        snapshot: Optional[KPISnapshot] = None
        try:
            snapshot = self.kpi_engine.process_data(data)
            self._latest_kpi = snapshot
            for listener in list(self._kpi_listeners):
                try:
                    listener(snapshot)
                except Exception as exc:
                    logger.error("Error in external KPI listener: %s", exc)
        except Exception as exc:
            logger.error("Error processing telemetry in KPI engine: %s", exc)

        # Step 2: Historical Downtime and Station Status event detection (Phase 3)
        # CRITICAL STABILIZATION: Only record machine downtime if PLC is actively CONNECTED.
        # Communication drops or disconnects must NEVER be treated as machine stoppage!
        if snapshot and data.is_connected and data.connection_state.value == "CONNECTED":
            try:
                station_states: Dict[int, Tuple[str, str, bool]] = {}
                for sid in range(1, 11):
                    st = snapshot.stations.get(f"station_{sid}")
                    if st:
                        station_states[sid] = (st.display_name, st.plc_address, st.status)
                if station_states:
                    self.downtime_manager.process_station_states(station_states)
            except Exception as exc:
                logger.error("Error processing downtime event detection: %s", exc)

        # Step 3: Handle alarms from PLC error flags if any
        if data.error_message:
            try:
                self.alarm_manager.raise_alarm(
                    alarm_code="PLC_ERR",
                    alarm_message=data.error_message,
                    severity="WARNING",
                )
            except Exception as exc:
                logger.error("Error processing alarm telemetry: %s", exc)

        # Step 4: Notify raw telemetry listeners
        for listener in list(self._external_listeners):
            try:
                listener(data)
            except Exception as exc:
                logger.error("Error in external data listener: %s", exc)

    def _on_hour_finalized(self, record: HourlyProductionRecord) -> None:
        """Callback triggered whenever an hourly production bucket completes."""
        try:
            prod_rec = ProductionDataRecord(
                id=None,
                timestamp=f"{record.date}T{record.hour_end}:00",
                production_date=record.date,
                hour_start=record.hour_start,
                hour_end=record.hour_end,
                hourly_target=record.hourly_target,
                actual_production=record.actual_production,
                hourly_achievement_percent=record.hourly_achievement_percent,
                cumulative_target=record.cumulative_target,
                cumulative_actual=record.cumulative_actual,
                cumulative_achievement_percent=record.cumulative_achievement_percent,
                tact_time=record.tact_time,
                average_speed=record.average_speed,
                production_counter=record.cumulative_actual,
            )
            self.prod_repo.upsert(prod_rec)
            # Update daily summary rollup
            daily_target = float(self.settings.get("simulation_settings", {}).get("daily_target", 1000))
            self.summary_service.generate_daily_summary(record.date, daily_target=daily_target)
        except Exception as exc:
            logger.error("Failed to persist finalized hourly production record: %s", exc)

    def register_data_listener(self, listener: Callable[[NormalizedPLCData], None]) -> None:
        """Register a subscriber callback to receive normalized telemetry packets."""
        if listener not in self._external_listeners:
            self._external_listeners.append(listener)

    def unregister_data_listener(self, listener: Callable[[NormalizedPLCData], None]) -> None:
        if listener in self._external_listeners:
            self._external_listeners.remove(listener)

    def register_kpi_listener(self, listener: Callable[[KPISnapshot], None]) -> None:
        """Register a subscriber callback to receive computed real-time KPI snapshots."""
        if listener not in self._kpi_listeners:
            self._kpi_listeners.append(listener)

    def unregister_kpi_listener(self, listener: Callable[[KPISnapshot], None]) -> None:
        if listener in self._kpi_listeners:
            self._kpi_listeners.remove(listener)

    def start(self) -> None:
        """Start the PLC data acquisition loop."""
        logger.info(
            "Starting DataManager for line '%s' (Cycle: %dms, Simulation: %s, PLC IP: %s)",
            self.kpi_engine.assembly_line_name,
            self.cycle_time_ms,
            self.simulation_mode,
            self.plc_ip,
        )
        self.client.start()

    def stop(self) -> None:
        """Gracefully stop data acquisition and close persistent database resources."""
        logger.info("Stopping DataManager...")
        self.client.stop()
        self.db_manager.close()

    def get_latest_data(self) -> NormalizedPLCData:
        """Return the most recent normalized snapshot."""
        return self.client.get_latest_data()

    def get_latest_data_dict(self, include_metadata: bool = False) -> Dict[str, Any]:
        """Return the most recent normalized snapshot as a plain dictionary."""
        return self.client.get_latest_data().to_dict(include_metadata=include_metadata)

    def get_latest_kpi(self) -> Optional[KPISnapshot]:
        """Return the most recent real-time KPI snapshot."""
        return self._latest_kpi

    def get_latest_kpi_dict(self) -> Optional[Dict[str, Any]]:
        """Return the most recent KPI snapshot as a plain dictionary."""
        return self._latest_kpi.to_dict() if self._latest_kpi else None

    def is_connected(self) -> bool:
        return self.client.is_connected

    # Service accessors for historical layer (Phase 3)
    def get_database_manager(self) -> DatabaseManager:
        return self.db_manager

    def get_downtime_manager(self) -> DowntimeManager:
        return self.downtime_manager

    def get_alarm_manager(self) -> AlarmManager:
        return self.alarm_manager

    def get_summary_service(self) -> DailySummaryService:
        return self.summary_service

    def get_query_service(self) -> HistoricalQueryService:
        return self.query_service
