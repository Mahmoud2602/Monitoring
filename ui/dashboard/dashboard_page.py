"""
Main Industrial Dashboard Page.
Coordinates the Alarm Bar, Line Status Banner, Continuous Production Line Visualization,
KPI Cards Grid, and SQLite-backed Downtime Reliability Card.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database.models import AlarmEventRecord
from kpi.models import KPISnapshot, LineStatus
from plc.plc_data import NormalizedPLCData
from ui.theme import IndustrialTheme
from ui.widgets.alarm_bar import AlarmBar
from ui.widgets.downtime_card import DowntimeCard
from ui.widgets.kpi_card import KPICard
from ui.widgets.line_status_banner import LineStatusBanner
from ui.widgets.production_line import ProductionLineWidget


class DashboardPage(QWidget):
    """
    Primary control room dashboard view.
    Receives real-time telemetry and KPI snapshots safely through Qt signals.
    """

    def __init__(
        self,
        line_name: str = "Assembly Line",
        station_display_names: Optional[Dict[str, str]] = None,
        speed_setpoint: float = 45.0,
        product_pitch_m: float = 0.75,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.line_name = line_name
        self.station_display_names = station_display_names or {}
        self.speed_setpoint = speed_setpoint
        self.product_pitch_m = product_pitch_m

        self._init_ui()

    def _init_ui(self) -> None:
        # Wrap content in a smooth scroll area for diverse resolution support
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setObjectName("DashboardContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        # 1. Top: High-Visibility Alarm Bar
        self.alarm_bar = AlarmBar(container)
        layout.addWidget(self.alarm_bar)

        # 2. Dominant Line Status Banner (LINE RUNNING / LINE STOPPED / PLC DISCONNECTED)
        self.line_status_banner = LineStatusBanner(container)
        layout.addWidget(self.line_status_banner)

        # 3. Main Continuous Production Line Visualization (Stations 1-10)
        self.production_line = ProductionLineWidget(
            line_name=self.line_name,
            station_display_names=self.station_display_names,
            parent=container,
        )
        layout.addWidget(self.production_line)

        # 4. KPI Cards Grid (5 Core Industrial KPI Cards)
        kpi_container = QWidget(container)
        kpi_layout = QGridLayout(kpi_container)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setHorizontalSpacing(12)
        kpi_layout.setVerticalSpacing(12)

        # Card 1: Production (Current / Target / Remaining / %)
        self.card_production = KPICard(
            title="DAILY PRODUCTION",
            unit="pcs",
            accent_color=IndustrialTheme.COLOR_GREEN,
            show_progress=True,
            parent=kpi_container,
        )
        kpi_layout.addWidget(self.card_production, 0, 0)

        # Card 2: Current Speed
        self.card_speed = KPICard(
            title="CONVEYOR SPEED",
            unit="m/min",
            accent_color=IndustrialTheme.COLOR_BLUE,
            show_progress=False,
            parent=kpi_container,
        )
        kpi_layout.addWidget(self.card_speed, 0, 1)

        # Card 3: Tact Time
        self.card_tact = KPICard(
            title="TACT TIME",
            unit="sec/pc",
            accent_color=IndustrialTheme.TEXT_CYAN,
            show_progress=False,
            parent=kpi_container,
        )
        kpi_layout.addWidget(self.card_tact, 0, 2)

        # Card 4: Hourly Achievement
        self.card_hourly = KPICard(
            title="HOURLY ACHIEVEMENT",
            unit="%",
            accent_color=IndustrialTheme.COLOR_GREEN,
            show_progress=True,
            parent=kpi_container,
        )
        kpi_layout.addWidget(self.card_hourly, 0, 3)

        # Card 5: Cumulative Achievement
        self.card_cumulative = KPICard(
            title="CUMULATIVE ACHIEVEMENT",
            unit="%",
            accent_color=IndustrialTheme.COLOR_GREEN,
            show_progress=True,
            parent=kpi_container,
        )
        kpi_layout.addWidget(self.card_cumulative, 0, 4)

        # Allow columns to expand proportionally
        for col in range(5):
            kpi_layout.setColumnStretch(col, 1)

        layout.addWidget(kpi_container)

        # 5. SQLite-Backed Downtime & Reliability Card
        self.card_downtime = DowntimeCard(container)
        layout.addWidget(self.card_downtime)

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    def set_line_name(self, name: str) -> None:
        """Update line name on child widgets."""
        self.line_name = name
        self.production_line.set_line_name(name)

    def set_station_names(self, mapping: Dict[str, str]) -> None:
        """Update station names dynamically."""
        self.station_display_names = mapping
        self.production_line.update_station_names(mapping)

    def update_telemetry(self, data: NormalizedPLCData) -> None:
        """
        Handle raw PLC telemetry.
        Updates station nodes along the continuous production line.
        """
        self.production_line.update_telemetry(data)

    def update_kpi(self, kpi: KPISnapshot) -> None:
        """
        Update KPI cards and line status banner from processed KPISnapshot.
        """
        # 1. Update Line Status Banner
        if kpi.line_status == LineStatus.RUNNING:
            self.line_status_banner.set_running(speed_m_per_min=kpi.engineering_speed)
        else:
            stopped_names = [s.display_name for s in kpi.stopped_stations]
            self.line_status_banner.set_stopped(stopped_names)

        # 2. Production Card (Authoritative daily production accumulated during current production day)
        daily_prod = kpi.daily_production
        daily_tgt = kpi.daily_target
        rem_tgt = max(0, daily_tgt - daily_prod)
        pct = kpi.daily_achievement_percent

        self.card_production.set_value(
            value_str=f"{daily_prod:,}",
            details=f"Target: {daily_tgt:,} pcs • Remaining: {rem_tgt:,} pcs (Raw D452: {kpi.production_counter_raw:,})",
            tag=f"{pct:.1f}%",
            progress_pct=min(100.0, pct),
        )

        # 3. Speed Card
        speed = kpi.engineering_speed
        delta = speed - self.speed_setpoint
        delta_str = f"{delta:+.1f} m/min" if abs(delta) > 0.1 else "Nominal"
        speed_color = IndustrialTheme.TEXT_PRIMARY
        if speed < 1.0:
            speed_color = IndustrialTheme.COLOR_RED
        elif abs(delta) > 5.0:
            speed_color = IndustrialTheme.COLOR_YELLOW

        self.card_speed.set_value(
            value_str=f"{speed:.1f}",
            details=f"Setpoint: {self.speed_setpoint:.1f} m/min • Delta: {delta_str}",
            tag="RUNNING" if speed > 1.0 else "STOPPED",
            status_color=speed_color,
        )

        # 4. Tact Time Card
        tact = kpi.tact_time_seconds
        if tact > 0 and speed > 0.5:
            self.card_tact.set_value(
                value_str=f"{tact:.1f}",
                details=f"Pitch: {self.product_pitch_m:.2f}m • Instantaneous",
                tag="NOMINAL",
            )
        else:
            # Mandated requirement: TACT TIME: -- if unavailable/zero
            self.card_tact.set_value(
                value_str="--",
                details=f"Pitch: {self.product_pitch_m:.2f}m • Conveyor Idle",
                tag="IDLE",
            )

        # 5. Hourly Achievement Card (Strictly distinct from daily %)
        hr_rec = kpi.current_hour
        hr_pct = hr_rec.hourly_achievement_percent
        self.card_hourly.set_value(
            value_str=f"{hr_pct:.1f}",
            details=f"Actual: {hr_rec.actual_production} / Expected: {int(hr_rec.hourly_target)} pcs",
            tag=f"[{hr_rec.hour_start} - {hr_rec.hour_end}]",
            progress_pct=hr_pct,
        )

        # 6. Cumulative Achievement Card (Strictly distinct from hourly %)
        cum_pct = hr_rec.cumulative_achievement_percent
        self.card_cumulative.set_value(
            value_str=f"{cum_pct:.1f}",
            details=f"Cum Actual: {hr_rec.cumulative_actual} / Expected: {int(hr_rec.cumulative_target)} pcs",
            tag="DAY-TO-DATE",
            progress_pct=cum_pct,
        )

    def update_downtime_stats(
        self,
        stats: Dict[str, Any],
        running_time_s: float,
        active_stops: int,
    ) -> None:
        """Update downtime & reliability card with Phase 3 SQLite database stats."""
        self.card_downtime.update_statistics(
            downtime_stats=stats,
            running_time_seconds=running_time_s,
            active_stops_count=active_stops,
        )

    def update_alarms(self, active_alarms: List[AlarmEventRecord]) -> None:
        """Update top alarm banner with live active alarms."""
        if not active_alarms:
            self.alarm_bar.clear_alarm()
        else:
            # Find the most prominent alarm
            first = active_alarms[0]
            count = len(active_alarms)
            msg = f"ALARM: Station {first.station_id} ({first.station_name}) - {first.alarm_type}"
            details = f"Active Alarms: {count} • Started: {first.start_time}"
            self.alarm_bar.set_alarm(
                message=msg,
                details=details,
                severity=first.severity,
            )

    def set_disconnected(self) -> None:
        """Set all indicators to safe disconnected/offline state."""
        self.line_status_banner.set_disconnected()
        self.production_line.set_disconnected()
        self.card_speed.set_value(
            value_str="--",
            details="PLC Offline • Communication Lost",
            tag="OFFLINE",
            status_color=IndustrialTheme.COLOR_GRAY,
        )
        self.card_tact.set_value(
            value_str="--",
            details="Telemetry Stale",
            tag="OFFLINE",
        )
