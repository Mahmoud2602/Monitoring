"""
Industrial PLC Production Monitor - Simulated PLC Driver

Generates realistic industrial physics, conveyor speeds, part production counters,
and intermittent station stop events for testing and development without physical hardware.
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from plc.base_driver import BasePLCDriver, PLCConnectionError
from utils.logger import get_logger

logger = get_logger("plc.simulator")


class SimulatedPLCDriver(BasePLCDriver):
    """
    In-memory simulation driver emulating an industrial dual-conveyor assembly line.
    Simulates:
      - Line speed (fluctuating realistically around setpoint)
      - Dynamic speed reduction if any conveyor station encounters a stoppage
      - Part counter progression based on actual throughput
      - Intermittent station stops (M550..M559) for alarm/downtime validation
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 502,
        timeout: float = 2.0,
        driver_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(host, port, timeout, driver_params)
        self._connected = False

        # Simulation parameters from driver_params or defaults
        self._base_setpoint = float(self.driver_params.get("base_speed", 45.0))
        self._speed_fluctuation = float(self.driver_params.get("speed_fluctuation", 1.2))
        self._daily_target = int(self.driver_params.get("daily_target", 1000))
        self._production_counter = float(self.driver_params.get("initial_counter", 1284.0))

        # Station stop simulation configuration
        self._stop_probability = float(self.driver_params.get("station_stop_probability", 0.06))
        self._stop_duration_cycles = int(self.driver_params.get("station_stop_duration_cycles", 6))

        # State tracking
        self._current_speed = self._base_setpoint
        self._last_tick_time = time.time()
        self._cycle_count = 0

        # M-bit station active statuses (True = Healthy/Running, False = Stopped/Jam)
        self._station_addresses = [
            "M550", "M551", "M552", "M553", "M554",  # Conveyor 1: Stations 1-5
            "M555", "M556", "M557", "M558", "M559",  # Conveyor 2: Stations 1-5
        ]
        self._station_status: Dict[str, bool] = {addr: True for addr in self._station_addresses}
        self._station_stop_countdown: Dict[str, int] = {addr: 0 for addr in self._station_addresses}

        # Simulated failure injection hook for unit tests
        self.force_connection_failure: bool = False
        self.force_read_error: bool = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        if self.force_connection_failure:
            self._connected = False
            raise PLCConnectionError(f"Simulated connection failure to {self.host}:{self.port}")

        # Mimic brief network handshake delay
        time.sleep(0.02)
        self._connected = True
        self._last_tick_time = time.time()
        logger.info("Connected to Simulated PLC at %s:%d", self.host, self.port)
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("Disconnected from Simulated PLC at %s:%d", self.host, self.port)

    def _tick_physics(self) -> None:
        """
        Advance internal physics, conveyor kinematics, and station stop timers.
        """
        now = time.time()
        dt = max(0.01, now - self._last_tick_time)
        self._last_tick_time = now
        self._cycle_count += 1

        # 1. Update station stop states
        any_station_stopped = False
        for addr in self._station_addresses:
            if self._station_stop_countdown[addr] > 0:
                self._station_stop_countdown[addr] -= 1
                if self._station_stop_countdown[addr] == 0:
                    self._station_status[addr] = True
                    logger.info("SIMULATOR: Station %s cleared stop state and resumed normal operation.", addr)
                else:
                    self._station_status[addr] = False
                    any_station_stopped = True
            else:
                # Random chance to induce station stoppage
                if random.random() < self._stop_probability:
                    self._station_status[addr] = False
                    self._station_stop_countdown[addr] = self._stop_duration_cycles
                    any_station_stopped = True
                    logger.warning(
                        "SIMULATOR: Station %s experienced an unexpected stoppage / alarm event! (Duration: %d cycles)",
                        addr,
                        self._stop_duration_cycles,
                    )

        # 2. Adjust line speed based on station statuses
        if any_station_stopped:
            # Line throttles down significantly during station stoppages
            target_speed = max(0.0, self._base_setpoint * 0.15)
        else:
            # Normal realistic fluctuation around setpoint (Gaussian noise)
            noise = random.gauss(0, self._speed_fluctuation * 0.4)
            target_speed = max(0.0, self._base_setpoint + noise)

        # Smooth conveyor acceleration/deceleration dampening
        alpha = min(1.0, dt * 2.5)
        self._current_speed += alpha * (target_speed - self._current_speed)

        # 3. Increment production counter based on speed
        # At 45 m/min, ~0.75 m/sec; assuming 1 part produced every 1.5 meters:
        parts_per_second = (self._current_speed / 60.0) * 0.65
        self._production_counter += parts_per_second * dt

    def read_bits(self, addresses: List[str]) -> Dict[str, bool]:
        if not self._connected:
            raise PLCConnectionError("Cannot read bits: PLC is not connected.")
        if self.force_read_error:
            raise PLCConnectionError("Simulated read error reading bits.")

        self._tick_physics()
        results: Dict[str, bool] = {}
        for addr in addresses:
            # Return current simulated status or default to True
            results[addr] = self._station_status.get(addr, True)
        return results

    def read_registers(self, addresses: List[str]) -> Dict[str, Any]:
        if not self._connected:
            raise PLCConnectionError("Cannot read registers: PLC is not connected.")
        if self.force_read_error:
            raise PLCConnectionError("Simulated read error reading registers.")

        self._tick_physics()
        results: Dict[str, Any] = {}
        for addr in addresses:
            # Match standard register addresses
            if addr == "D450":
                results[addr] = round(self._current_speed, 2)
            elif addr == "D451":
                results[addr] = round(self._base_setpoint, 2)
            elif addr == "D452":
                results[addr] = int(self._production_counter)
            elif addr == "D453":
                results[addr] = int(self._daily_target)
            else:
                # Fallback for arbitrary D registers
                results[addr] = 0
        return results
