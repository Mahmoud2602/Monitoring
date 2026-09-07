"""
Industrial PLC Production Monitor - Core Application Layer
"""
from core.production_day import (
    get_production_date,
    get_production_day_range,
    is_same_production_day,
)

__all__ = [
    "DataManager",
    "get_production_date",
    "get_production_day_range",
    "is_same_production_day",
]


def __getattr__(name: str):
    if name == "DataManager":
        from core.data_manager import DataManager
        return DataManager
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
