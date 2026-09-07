"""
Large Line Status Banner indicating operational status of the entire production line:
LINE RUNNING, LINE STOPPED, or PLC DISCONNECTED, with root-cause stoppage details.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme


class LineStatusBanner(QFrame):
    """
    Dominant line status indicator showing overall system state and active stoppage causes.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("LineStatusBanner")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(16)

        # Large Beacon Dot
        self.lbl_beacon = QLabel("●", self)
        self.lbl_beacon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_beacon.setFixedWidth(36)

        # Status & Reason Text
        text_box = QWidget(self)
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        self.lbl_status = QLabel("LINE RUNNING", text_box)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.lbl_subtext = QLabel("All stations synchronized and operational", text_box)
        self.lbl_subtext.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        text_layout.addWidget(self.lbl_status)
        text_layout.addWidget(self.lbl_subtext)

        layout.addWidget(self.lbl_beacon)
        layout.addWidget(text_box, stretch=1)

        # Default state
        self.set_running(speed_m_per_min=45.0)

    def set_running(self, speed_m_per_min: float = 0.0) -> None:
        """Render LINE RUNNING state."""
        self.setStyleSheet(f"""
            QFrame#LineStatusBanner {{
                background-color: #064e3b;
                border: 2px solid {IndustrialTheme.COLOR_GREEN};
                border-radius: 8px;
            }}
        """)
        self.lbl_beacon.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.COLOR_GREEN};
                font-size: 32px;
            }}
        """)
        self.lbl_status.setText("LINE RUNNING")
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                color: #ffffff;
                font-size: 26px;
                font-weight: 900;
                letter-spacing: 2.0px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)
        speed_text = f" • Current Speed: {speed_m_per_min:.1f} m/min" if speed_m_per_min > 0 else ""
        self.lbl_subtext.setText(f"All 10 Workstations Active & Synchronized{speed_text}")
        self.lbl_subtext.setStyleSheet(f"""
            QLabel {{
                color: #a7f3d0;
                font-size: 13px;
                font-weight: 600;
            }}
        """)

    def set_stopped(
        self,
        stopped_station_names: List[str],
        stoppage_duration_s: float = 0.0,
    ) -> None:
        """Render LINE STOPPED state with exact stoppage cause."""
        self.setStyleSheet(f"""
            QFrame#LineStatusBanner {{
                background-color: #7f1d1d;
                border: 2px solid {IndustrialTheme.COLOR_RED};
                border-radius: 8px;
            }}
        """)
        self.lbl_beacon.setStyleSheet(f"""
            QLabel {{
                color: #fca5a5;
                font-size: 32px;
            }}
        """)
        self.lbl_status.setText("LINE STOPPED")
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                color: #ffffff;
                font-size: 26px;
                font-weight: 900;
                letter-spacing: 2.0px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)

        if stopped_station_names:
            stations_str = ", ".join(stopped_station_names)
            dur_str = f" • Duration: {stoppage_duration_s:.0f}s" if stoppage_duration_s > 0 else ""
            msg = f"Fault Source: {stations_str}{dur_str}"
        else:
            msg = "Production halted by safety interlock or zero-speed condition"

        self.lbl_subtext.setText(msg)
        self.lbl_subtext.setStyleSheet(f"""
            QLabel {{
                color: #fecaca;
                font-size: 13px;
                font-weight: 700;
            }}
        """)

    def set_disconnected(self, last_update_info: str = "") -> None:
        """Render PLC DISCONNECTED state."""
        self.setStyleSheet(f"""
            QFrame#LineStatusBanner {{
                background-color: #374151;
                border: 2px solid {IndustrialTheme.COLOR_YELLOW};
                border-radius: 8px;
            }}
        """)
        self.lbl_beacon.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.COLOR_YELLOW};
                font-size: 32px;
            }}
        """)
        self.lbl_status.setText("PLC DISCONNECTED")
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                color: #fef08a;
                font-size: 26px;
                font-weight: 900;
                letter-spacing: 2.0px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)
        msg = "Communication with PLC lost • Stale telemetry data • Auto-reconnecting in background..."
        if last_update_info:
            msg += f" (Last live: {last_update_info})"
        self.lbl_subtext.setText(msg)
        self.lbl_subtext.setStyleSheet(f"""
            QLabel {{
                color: #e5e7eb;
                font-size: 13px;
                font-weight: 600;
            }}
        """)
