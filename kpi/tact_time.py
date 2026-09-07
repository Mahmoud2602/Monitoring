"""
Industrial PLC Production Monitor - Tact Time & Speed Engineering Module
Phase 2: Modular calculations for line speed scaling, engineering unit conversion,
tact time derivation, and target production rate alignment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SpeedScalingConfig:
    """
    Configuration for translating raw PLC registers into calibrated engineering units.
    """
    raw_address: str = "D450"
    scale_factor: float = 1.0
    engineering_unit: str = "m/min"  # Supported: "m/min", "m/s", "mm/s", "ft/min"
    product_pitch_meters: float = 0.75  # Distance between successive product fixtures on line

    def raw_to_engineering(self, raw_value: float) -> float:
        """Apply scaling factor to raw integer/float PLC value."""
        return float(raw_value) * float(self.scale_factor)


class TactTimeCalculator:
    """
    Dedicated calculation engine for Tact Time and Target Production Rates.
    Decoupled from specific PLC vendors or rigid line configurations.
    """

    def __init__(self, config: Optional[SpeedScalingConfig] = None) -> None:
        self.config = config or SpeedScalingConfig()

    @staticmethod
    def speed_to_meters_per_second(speed_value: float, unit: str = "m/min") -> float:
        """
        Normalize various industrial engineering speed units to SI standard (m/s).
        """
        clean_unit = unit.strip().lower()
        if clean_unit in ("m/min", "meters/min", "mpm"):
            return speed_value / 60.0
        elif clean_unit in ("m/s", "meters/sec", "mps"):
            return speed_value
        elif clean_unit in ("mm/s", "mm/sec"):
            return speed_value / 1000.0
        elif clean_unit in ("ft/min", "fpm"):
            return (speed_value * 0.3048) / 60.0
        else:
            # Default assumption: m/min
            return speed_value / 60.0

    def calculate_tact_time_from_speed(
        self,
        engineering_speed: float,
        pitch_meters: Optional[float] = None,
        speed_unit: Optional[str] = None,
    ) -> float:
        """
        Calculate tact time (seconds per part) from physical line parameters:
        Tact Time = Product Pitch / Line Speed (in m/s).
        Returns 0.0 if speed is non-positive to prevent division by zero.
        """
        pitch = pitch_meters if pitch_meters is not None else self.config.product_pitch_meters
        unit = speed_unit if speed_unit is not None else self.config.engineering_unit

        if engineering_speed <= 0.0 or pitch <= 0.0:
            return 0.0

        speed_m_per_s = self.speed_to_meters_per_second(engineering_speed, unit=unit)
        if speed_m_per_s <= 0.0:
            return 0.0

        tact_time_sec = pitch / speed_m_per_s
        return round(tact_time_sec, 2)

    @staticmethod
    def calculate_target_rate_from_tact_time(tact_time_seconds: float) -> float:
        """
        Derive hourly target production rate from tact time in seconds:
        Rate = 3600 / Tact Time.
        """
        if tact_time_seconds <= 0.0:
            return 0.0
        return round(3600.0 / tact_time_seconds, 2)

    @staticmethod
    def calculate_tact_time_from_target_rate(target_rate_pcs_per_hour: float) -> float:
        """
        Derive required tact time in seconds to achieve a target hourly rate:
        Tact Time = 3600 / Target Rate.
        """
        if target_rate_pcs_per_hour <= 0.0:
            return 0.0
        return round(3600.0 / target_rate_pcs_per_hour, 2)

    def process_raw_register(self, raw_value: float) -> dict:
        """
        Convenience pipeline: converts raw register -> engineering value -> tact time -> target rate.
        """
        eng_val = self.config.raw_to_engineering(raw_value)
        tact_time = self.calculate_tact_time_from_speed(eng_val)
        target_rate = self.calculate_target_rate_from_tact_time(tact_time)
        return {
            "raw_value": raw_value,
            "scale": self.config.scale_factor,
            "engineering_value": eng_val,
            "engineering_unit": self.config.engineering_unit,
            "pitch_meters": self.config.product_pitch_meters,
            "tact_time_seconds": tact_time,
            "derived_target_rate": target_rate,
        }
