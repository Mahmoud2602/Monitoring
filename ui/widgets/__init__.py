"""
Widgets package for Industrial Monitor PySide6 UI.
"""
from __future__ import annotations

__all__ = [
    "AlarmBar",
    "DowntimeCard",
    "HeaderBar",
    "KPICard",
    "LineStatusBanner",
    "LogoWidget",
    "ProductionLineWidget",
    "StationNode",
]

from ui.widgets.alarm_bar import AlarmBar
from ui.widgets.downtime_card import DowntimeCard
from ui.widgets.header_bar import HeaderBar
from ui.widgets.kpi_card import KPICard
from ui.widgets.line_status_banner import LineStatusBanner
from ui.widgets.logo_widget import LogoWidget
from ui.widgets.production_line import ProductionLineWidget
from ui.widgets.station_node import StationNode
