"""
Industrial Downtime & Reliability Summary Card.
Displays Total Downtime, Number of Stops, Running Time, Average Stop Duration,
and Longest Stop duration directly derived from Phase 3 SQLite database services.
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


def format_seconds_hms(total_seconds: float) -> str:
    """Format seconds into HH:MM:SS string."""
    if total_seconds < 0:
        total_seconds = 0.0
    sec_int = int(total_seconds)
    hours = sec_int // 3600
    minutes = (sec_int % 3600) // 60
    seconds = sec_int % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_duration_compact(seconds: float) -> str:
    """Format short durations cleanly (e.g. 45s or 2m 15s)."""
    if seconds <= 0:
        return "0s"
    sec_int = int(seconds)
    if sec_int < 60:
        return f"{seconds:.1f}s"
    minutes = sec_int // 60
    rem_sec = sec_int % 60
    return f"{minutes}m {rem_sec}s"


class DowntimeCard(QFrame):
    """
    Control room downtime & operational reliability card.
    Renders metrics queried directly from the SQLite database repository layer.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DowntimeCard")
        self.setStyleSheet(f"""
            QFrame#DowntimeCard {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame#DowntimeCard:hover {{
                border-color: {IndustrialTheme.BORDER_FOCUS};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header: Title & Target Date
        header_row = QHBoxLayout()
        lbl_title = QLabel("TODAY'S DOWNTIME & RELIABILITY", self)
        lbl_title.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }}
        """)
        header_row.addWidget(lbl_title)

        header_row.addStretch(1)

        self.lbl_active_stops_tag = QLabel("NO ACTIVE STOPS", self)
        self.lbl_active_stops_tag.setStyleSheet(f"""
            QLabel {{
                background-color: {IndustrialTheme.COLOR_GREEN_BG};
                color: {IndustrialTheme.COLOR_GREEN};
                border: 1px solid {IndustrialTheme.COLOR_GREEN_BORDER};
                font-size: 9px;
                font-weight: bold;
                border-radius: 3px;
                padding: 2px 6px;
            }}
        """)
        header_row.addWidget(self.lbl_active_stops_tag)
        layout.addLayout(header_row)

        # Main Large Downtime readout
        main_readout_layout = QHBoxLayout()
        main_readout_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        main_readout_layout.setSpacing(8)

        self.lbl_total_downtime = QLabel("00:00:00", self)
        self.lbl_total_downtime.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 32px;
                font-weight: 900;
            }}
        """)
        main_readout_layout.addWidget(self.lbl_total_downtime)

        lbl_total_unit = QLabel("DOWNTIME (HH:MM:SS)", self)
        lbl_total_unit.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-size: 11px;
                font-weight: 600;
                margin-top: 10px;
            }}
        """)
        main_readout_layout.addWidget(lbl_total_unit)
        main_readout_layout.addStretch(1)
        layout.addLayout(main_readout_layout)

        # Sub-metrics Grid (Stops, Running Time, Avg Stop, Longest Stop)
        grid_container = QWidget(self)
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 4, 0, 0)
        grid_layout.setHorizontalSpacing(16)
        grid_layout.setVerticalSpacing(8)

        # Col 0: Total Stops
        self.lbl_stops_val = QLabel("0", self)
        self._style_metric_val(self.lbl_stops_val)
        lbl_stops_title = QLabel("STOPS TODAY", self)
        self._style_metric_lbl(lbl_stops_title)
        grid_layout.addWidget(lbl_stops_title, 0, 0)
        grid_layout.addWidget(self.lbl_stops_val, 1, 0)

        # Col 1: Running Time
        self.lbl_running_val = QLabel("00:00:00", self)
        self._style_metric_val(self.lbl_running_val)
        lbl_running_title = QLabel("RUNNING TIME", self)
        self._style_metric_lbl(lbl_running_title)
        grid_layout.addWidget(lbl_running_title, 0, 1)
        grid_layout.addWidget(self.lbl_running_val, 1, 1)

        # Col 2: Average Stop Duration
        self.lbl_avg_stop_val = QLabel("0.0s", self)
        self._style_metric_val(self.lbl_avg_stop_val)
        lbl_avg_title = QLabel("AVG STOP DURATION", self)
        self._style_metric_lbl(lbl_avg_title)
        grid_layout.addWidget(lbl_avg_title, 0, 2)
        grid_layout.addWidget(self.lbl_avg_stop_val, 1, 2)

        # Col 3: Longest Stop Duration
        self.lbl_longest_stop_val = QLabel("0.0s", self)
        self._style_metric_val(self.lbl_longest_stop_val)
        lbl_longest_title = QLabel("LONGEST STOP", self)
        self._style_metric_lbl(lbl_longest_title)
        grid_layout.addWidget(lbl_longest_title, 0, 3)
        grid_layout.addWidget(self.lbl_longest_stop_val, 1, 3)

        layout.addWidget(grid_container)

    def _style_metric_val(self, label: QLabel) -> None:
        label.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 16px;
                font-weight: 800;
            }}
        """)

    def _style_metric_lbl(self, label: QLabel) -> None:
        label.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }}
        """)

    def update_statistics(
        self,
        downtime_stats: Dict[str, Any],
        running_time_seconds: float = 0.0,
        active_stops_count: int = 0,
    ) -> None:
        """
        Update widget strictly using pre-calculated values from Phase 3 service layer.
        Does NOT recalculate or duplicate database logic in UI.
        """
        total_downtime = float(downtime_stats.get("total_downtime_seconds", 0.0))
        total_stops = int(downtime_stats.get("total_stops", 0))
        avg_stop = float(downtime_stats.get("average_stop_seconds", 0.0))
        longest_stop = float(downtime_stats.get("longest_stop_seconds", 0.0))

        self.lbl_total_downtime.setText(format_seconds_hms(total_downtime))
        self.lbl_stops_val.setText(str(total_stops))
        self.lbl_running_val.setText(format_seconds_hms(running_time_seconds))
        self.lbl_avg_stop_val.setText(format_duration_compact(avg_stop))
        self.lbl_longest_stop_val.setText(format_duration_compact(longest_stop))

        if active_stops_count > 0:
            self.lbl_active_stops_tag.setText(f"{active_stops_count} STOPPED WORKSTATION(S)")
            self.lbl_active_stops_tag.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_RED_BG};
                    color: #fca5a5;
                    border: 1px solid {IndustrialTheme.COLOR_RED_BORDER};
                    font-size: 9px;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 6px;
                }}
            """)
        else:
            self.lbl_active_stops_tag.setText("NO ACTIVE STOPS")
            self.lbl_active_stops_tag.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_GREEN_BG};
                    color: {IndustrialTheme.COLOR_GREEN};
                    border: 1px solid {IndustrialTheme.COLOR_GREEN_BORDER};
                    font-size: 9px;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 6px;
                }}
            """)
