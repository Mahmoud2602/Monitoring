"""
Industrial PLC Production Monitor - Isolated PLC Client

Manages communication lifecycle, connection state machine, automatic retries,
and asynchronous polling loops. Isolates the rest of the application from low-level PLC details.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional

from plc.base_driver import BasePLCDriver, PLCConnectionError, PLCConnectionTimeoutError, PLCError
from plc.plc_data import ConnectionState, NormalizedPLCData, PLCMappingConfig
from utils.logger import get_logger

logger = get_logger("plc.client")

# Callback signature for data subscribers
DataListener = Callable[[NormalizedPLCData], None]


class PLCClient:
    """
    Industrial PLC Client encapsulating transport lifecycle, cyclic polling,
    and automatic reconnection.
    """

    def __init__(
        self,
        driver: BasePLCDriver,
        mapping: PLCMappingConfig,
        cycle_time_ms: int = 500,
        retry_interval_seconds: float = 3.0,
        max_retries: Optional[int] = None,
    ) -> None:
        self._driver = driver
        self._mapping = mapping
        self._cycle_time_seconds = max(0.05, cycle_time_ms / 1000.0)
        self._retry_interval_seconds = max(0.5, retry_interval_seconds)
        self._max_retries = max_retries

        # State management
        self._state = ConnectionState.DISCONNECTED
        self._retry_count = 0
        self._latest_data: NormalizedPLCData = NormalizedPLCData.create_empty(self._state)
        self._data_lock = threading.Lock()

        # Polling thread control
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._listeners: List[DataListener] = []

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    def register_listener(self, listener: DataListener) -> None:
        """Register a callback to be invoked with every new normalized data snapshot."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unregister_listener(self, listener: DataListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def get_latest_data(self) -> NormalizedPLCData:
        """Retrieve thread-safe copy of the latest normalized snapshot."""
        with self._data_lock:
            return self._latest_data

    def _set_state(self, new_state: ConnectionState, reason: str = "") -> None:
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            if reason:
                logger.info("PLC State change: %s -> %s (Reason: %s)", old_state.value, new_state.value, reason)
            else:
                logger.info("PLC State change: %s -> %s", old_state.value, new_state.value)

    def connect(self) -> bool:
        """
        Attempt to establish transport connection to the PLC.
        Handles timeout and connection errors without raising exceptions.
        """
        self._set_state(ConnectionState.CONNECTING, f"Connecting to {self._driver.host}:{self._driver.port}")
        try:
            success = self._driver.connect()
            if success:
                self._retry_count = 0
                self._set_state(ConnectionState.CONNECTED, "Link established successfully")
                return True
            else:
                self._set_state(ConnectionState.ERROR, "Driver returned unsuccessful connection status")
                return False
        except PLCConnectionTimeoutError as exc:
            self._set_state(ConnectionState.ERROR, f"Connection timeout: {exc}")
            logger.error("Connection timeout attempting to reach PLC at %s:%s: %s", self._driver.host, self._driver.port, exc)
            return False
        except (PLCConnectionError, PLCError) as exc:
            self._set_state(ConnectionState.ERROR, f"Connection failure: {exc}")
            logger.error("Failed to connect to PLC at %s:%s: %s", self._driver.host, self._driver.port, exc)
            return False
        except Exception as exc:
            self._set_state(ConnectionState.ERROR, f"Unexpected error during connect: {exc}")
            logger.exception("Unexpected error during PLC connect: %s", exc)
            return False

    def disconnect(self) -> None:
        """Disconnect driver and transition state."""
        try:
            self._driver.disconnect()
        except Exception as exc:
            logger.warning("Error during driver disconnect: %s", exc)
        finally:
            self._set_state(ConnectionState.DISCONNECTED, "Application requested disconnection")
            with self._data_lock:
                self._latest_data = NormalizedPLCData.create_empty(self._state)

    def read_cycle(self) -> NormalizedPLCData:
        """
        Execute a single synchronous scan cycle:
          1. Verify connection (attempt auto-reconnect if needed)
          2. Read mapped D-registers
          3. Read mapped M-bits
          4. Map raw results into NormalizedPLCData
          5. Update internal state and return snapshot
        """
        # Ensure connection
        if not self._driver.is_connected:
            self._set_state(ConnectionState.RECONNECTING, f"Attempting connection retry #{self._retry_count + 1}")
            self._retry_count += 1
            if not self.connect():
                err_msg = f"PLC not connected (Retry #{self._retry_count})"
                safe_data = NormalizedPLCData.create_empty(self._state, error_message=err_msg)
                with self._data_lock:
                    self._latest_data = safe_data
                return safe_data

        t_start = time.perf_counter()
        reg_addrs = self._mapping.register_addresses
        station_addrs = self._mapping.station_addresses

        try:
            # Low-level reads via isolated driver
            raw_registers = self._driver.read_registers(reg_addrs)
            raw_bits = self._driver.read_bits(station_addrs)

            scan_time_ms = (time.perf_counter() - t_start) * 1000.0

            # Normalize telemetry using configured schema
            normalized = self._mapping.map_raw_telemetry(
                raw_registers=raw_registers,
                raw_bits=raw_bits,
                connection_state=self._state,
                scan_time_ms=scan_time_ms,
                error_message=None,
            )

            # Reset retry counter upon successful cycle
            self._retry_count = 0

            with self._data_lock:
                self._latest_data = normalized

            return normalized

        except PLCConnectionTimeoutError as exc:
            scan_time_ms = (time.perf_counter() - t_start) * 1000.0
            logger.warning("PLC Read Timeout after %.1fms: %s", scan_time_ms, exc)
            self._handle_communication_failure(f"Read timeout: {exc}")
            return self.get_latest_data()

        except (PLCConnectionError, PLCError) as exc:
            logger.warning("PLC Communication error during read cycle: %s", exc)
            self._handle_communication_failure(f"Communication error: {exc}")
            return self.get_latest_data()

        except Exception as exc:
            logger.exception("Unexpected exception during PLC read cycle: %s", exc)
            self._handle_communication_failure(f"Unexpected error: {exc}")
            return self.get_latest_data()

    def _handle_communication_failure(self, error_message: str) -> None:
        """Handle link degradation or read fault gracefully without crashing."""
        self._retry_count += 1
        logger.warning(
            "PLC Communication fault detected (#%d). Entering RECONNECTING state. Reason: %s",
            self._retry_count,
            error_message,
        )
        self._set_state(ConnectionState.RECONNECTING, error_message)

        # Force driver disconnect to clean socket handles
        try:
            self._driver.disconnect()
        except Exception:
            pass

        safe_data = NormalizedPLCData.create_empty(self._state, error_message=error_message)
        with self._data_lock:
            self._latest_data = safe_data

        self._notify_listeners(safe_data)

    def _notify_listeners(self, data: NormalizedPLCData) -> None:
        for listener in list(self._listeners):
            try:
                listener(data)
            except Exception as exc:
                logger.error("Error invoking data listener callback: %s", exc)

    def _poll_worker(self) -> None:
        """Background worker thread for continuous cyclic polling."""
        logger.info("PLC cyclic polling thread started (Cycle time: %.0fms)", self._cycle_time_seconds * 1000)
        while self._running:
            cycle_start = time.time()
            data = self.read_cycle()
            self._notify_listeners(data)

            # Sleep remaining cycle duration
            elapsed = time.time() - cycle_start
            sleep_duration = self._cycle_time_seconds - elapsed

            if not self.is_connected:
                # When disconnected, throttle polling rate to retry_interval to avoid network flooding
                sleep_duration = max(self._retry_interval_seconds, sleep_duration)

            if sleep_duration > 0 and self._running:
                time.sleep(sleep_duration)

        logger.info("PLC cyclic polling thread stopped.")

    def start(self) -> None:
        """Start the cyclic polling background thread."""
        if self._running:
            logger.warning("PLCClient is already running.")
            return

        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_worker, name="PLC-Polling-Worker", daemon=True)
        self._poll_thread.start()

    def stop(self) -> None:
        """Stop cyclic polling and release driver resources."""
        if not self._running:
            return

        logger.info("Stopping PLCClient polling...")
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=3.0)
        self.disconnect()
