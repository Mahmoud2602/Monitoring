"""
Historical KPI Summary Bar.
Displays 9 core historical performance metrics:
1. Total Production
2. Total Target
3. Achievement %
4. Total Downtime
5. Number of Stops
6. Average Stop Duration
7. Longest Stop
8. Average Speed
9. Average Tact Time
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme


class HistoricalKPICard(QFrame):
    """Individual industrial KPI card widget for historical metrics."""

    def __init__(
        self,
        title: str,
        initial_value: str = "--",
        unit: str = "",
        accent_color: str = IndustrialTheme.TEXT_PRIMARY,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.accent_color = accent_color
        self._init_ui(title, initial_value, unit)

    def _init_ui(self, title: str, initial_value: str, unit: str) -> None:
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Title Label
        self.lbl_title = QLabel(title.upper(), self)
        self.lbl_title.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_SECONDARY};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.8px;
        """)
        layout.addWidget(self.lbl_title)

        # Value & Unit Row
        val_row = QHBoxLayout()
        val_row.setSpacing(4)
        val_row.setContentsMargins(0, 0, 0, 0)

        self.lbl_value = QLabel(initial_value, self)
        self.lbl_value.setStyleSheet(f"""
            color: {self.accent_color};
            font-family: {IndustrialTheme.FONT_FAMILY_MONO};
            font-size: 20px;
            font-weight: 800;
        """)
        val_row.addWidget(self.lbl_value)

        if unit:
            self.lbl_unit = QLabel(unit, self)
            self.lbl_unit.setStyleSheet(f"""
                color: {IndustrialTheme.TEXT_MUTED};
                font-size: 11px;
                font-weight: 600;
                margin-top: 5px;
            """)
            val_row.addWidget(self.lbl_unit)

        val_row.addStretch(1)
        layout.addLayout(val_row)

    def set_value(self, value: str, color: Optional[str] = None) -> None:
        """Update displayed value and optional override color."""
        self.lbl_value.setText(value)
        if color:
            self.lbl_value.setStyleSheet(f"""
                color: {color};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 20px;
                font-weight: 800;
            """)


class KPISummaryBar(QFrame):
    """
    Container grid holding all 9 historical KPI overview cards.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("HistoricalKPISummaryBar")
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("QFrame#HistoricalKPISummaryBar { background-color: transparent; border: none; }")

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        # Row 0: Production metrics (3 cards)
        self.card_actual = HistoricalKPICard(
            title="Total Production",
            initial_value="0",
            unit="pcs",
            accent_color=IndustrialTheme.COLOR_GREEN,
            parent=self,
        )
        self.card_target = HistoricalKPICard(
            title="Total Target",
            initial_value="0",
            unit="pcs",
            accent_color=IndustrialTheme.TEXT_CYAN,
            parent=self,
        )
        self.card_achievement = HistoricalKPICard(
            title="Achievement Rate",
            initial_value="0.0%",
            unit="",
            accent_color=IndustrialTheme.COLOR_GREEN,
            parent=self,
        )

        grid.addWidget(self.card_actual, 0, 0)
        grid.addWidget(self.card_target, 0, 1)
        grid.addWidget(self.card_achievement, 0, 2)

        # Row 1: Downtime & Reliability (4 cards)
        self.card_downtime = HistoricalKPICard(
            title="Total Downtime",
            initial_value="00:00:00",
            unit="h:m:s",
            accent_color=IndustrialTheme.COLOR_RED,
            parent=self,
        )
        self.card_stops = HistoricalKPICard(
            title="Number of Stops",
            initial_value="0",
            unit="events",
            accent_color=IndustrialTheme.COLOR_YELLOW,
            parent=self,
        )
        self.card_avg_stop = HistoricalKPICard(
            title="Avg Stop Duration",
            initial_value="0s",
            unit="",
            accent_color=IndustrialTheme.TEXT_PRIMARY,
            parent=self,
        )
        self.card_longest_stop = HistoricalKPICard(
            title="Longest Stop",
            initial_value="0s",
            unit="",
            accent_color=IndustrialTheme.COLOR_RED,
            parent=self,
        )

        grid.addWidget(self.card_downtime, 0, 3)
        grid.addWidget(self.card_stops, 0, 4)
        grid.addWidget(self.card_avg_stop, 1, 0)
        grid.addWidget(self.card_longest_stop, 1, 1)

        # Row 2: Speed & Tact (2 cards)
        self.card_avg_speed = HistoricalKPICard(
            title="Average Speed",
            initial_value="0.0",
            unit="m/min",
            accent_color=IndustrialTheme.TEXT_CYAN,
            parent=self,
        )
        self.card_avg_tact = HistoricalKPICard(
            title="Average Tact Time",
            initial_value="0.0",
            unit="s/pc",
            accent_color=IndustrialTheme.TEXT_PRIMARY,
            parent=self,
        )

        grid.addWidget(self.card_avg_speed, 1, 2)
        grid.addWidget(self.card_avg_tact, 1, 3)

        # Add a stretch placeholder in 1, 4 to align grid nicely
        placeholder = QFrame(self)
        placeholder.setStyleSheet(f"""
            QFrame {{
                background-color: {IndustrialTheme.BG_PANEL};
                border: 1px dashed {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        lbl_info = QLabel("HISTORICAL AUDIT", placeholder)
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_MUTED};
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        p_layout = QVBoxLayout(placeholder)
        p_layout.addWidget(lbl_info)
        grid.addWidget(placeholder, 1, 4)

    def update_metrics(self, summary: Dict[str, Any]) -> None:
        """Populate cards with resolved historical summary data."""
        actual = summary.get("total_production", 0)
        target = summary.get("total_target", 0.0)
        achieve = summary.get("achievement_percent", 0.0)
        dt_str = summary.get("total_downtime_str", "00:00:00")
        stops = summary.get("total_stops", 0)
        avg_stop = summary.get("average_stop_str", "0s")
        longest_stop = summary.get("longest_stop_str", "0s")
        speed = summary.get("average_speed", 0.0)
        tact = summary.get("average_tact_time", 0.0)

        self.card_actual.set_value(f"{actual:,}")
        self.card_target.set_value(f"{int(target):,}")

        # Color-coded achievement rate
        if achieve >= 100.0:
            achieve_color = IndustrialTheme.COLOR_GREEN
        elif achieve >= 90.0:
            achieve_color = IndustrialTheme.TEXT_CYAN
        elif achieve >= 75.0:
            achieve_color = IndustrialTheme.COLOR_YELLOW
        else:
            achieve_color = IndustrialTheme.COLOR_RED
        self.card_achievement.set_value(f"{achieve:.1f}%", achieve_color)

        self.card_downtime.set_value(dt_str)
        self.card_stops.set_value(str(stops))
        self.card_avg_stop.set_value(avg_stop)
        self.card_longest_stop.set_value(longest_stop)
        self.card_avg_speed.set_value(f"{speed:.1f}")
        self.card_avg_tact.set_value(f"{tact:.1f}")
