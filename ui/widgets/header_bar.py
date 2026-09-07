"""
Industrial Header Bar displaying company logos, centered configurable line name,
real-time clock, simulation indicator, and detailed PLC connectivity status.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme
from ui.widgets.logo_widget import LogoWidget


class HeaderBar(QFrame):
    """
    Control room header bar component with prominent line name and live PLC status indicator.
    """

    def __init__(
        self,
        line_name: str = "Assembly Line",
        company_logo_path: Optional[str] = None,
        customer_logo_path: Optional[str] = None,
        simulation_mode: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.line_name = line_name
        self.simulation_mode = simulation_mode

        self.setObjectName("HeaderBar")
        self.setStyleSheet(f"""
            QFrame#HeaderBar {{
                background-color: {IndustrialTheme.BG_PANEL};
                border-bottom: 2px solid {IndustrialTheme.BORDER_SUBTLE};
                padding: 6px 14px;
            }}
        """)

        # Main Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(16)

        # 1. Left: Company Logo Widget
        self.company_logo = LogoWidget(
            logo_path=company_logo_path,
            fallback_text="MONITOR",
            fallback_subtext="AUTOMATION SYSTEMS",
            accent_color=IndustrialTheme.COLOR_BLUE,
            parent=self,
        )
        layout.addWidget(self.company_logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 2. Center: Configurable Line Name (prominent and readable from distance)
        center_container = QWidget(self)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        self.lbl_line_name = QLabel(self.line_name.upper(), center_container)
        self.lbl_line_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_line_name.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                font-size: 22px;
                font-weight: 800;
                letter-spacing: 2.0px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)

        self.lbl_sub_header = QLabel("REAL-TIME PRODUCTION & QUALITY MONITOR", center_container)
        self.lbl_sub_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_header.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1.2px;
            }}
        """)

        center_layout.addWidget(self.lbl_line_name)
        center_layout.addWidget(self.lbl_sub_header)
        layout.addWidget(center_container, stretch=1, alignment=Qt.AlignmentFlag.AlignCenter)

        # 3. Right: Status details + Customer Logo
        right_container = QWidget(self)
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        # Telemetry & Connectivity Badges
        status_box = QWidget(right_container)
        status_box_layout = QVBoxLayout(status_box)
        status_box_layout.setContentsMargins(0, 0, 0, 0)
        status_box_layout.setSpacing(3)

        top_pills_layout = QHBoxLayout()
        top_pills_layout.setSpacing(6)
        top_pills_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Simulation mode pill
        self.lbl_sim_pill = QLabel(status_box)
        self.set_simulation_mode(simulation_mode)
        top_pills_layout.addWidget(self.lbl_sim_pill)

        # PLC Connection status pill
        self.lbl_plc_pill = QLabel("PLC DISCONNECTED", status_box)
        self._style_plc_pill(connected=False)
        top_pills_layout.addWidget(self.lbl_plc_pill)

        status_box_layout.addLayout(top_pills_layout)

        # Timestamp & Scan Latency details
        bottom_meta_layout = QHBoxLayout()
        bottom_meta_layout.setSpacing(10)
        bottom_meta_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_scan_time = QLabel("Scan: -- ms", status_box)
        self.lbl_scan_time.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_CYAN};
                font-size: 11px;
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-weight: 600;
            }}
        """)
        bottom_meta_layout.addWidget(self.lbl_scan_time)

        self.lbl_clock = QLabel("--:--:-- UTC", status_box)
        self.lbl_clock.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-size: 11px;
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-weight: 600;
            }}
        """)
        bottom_meta_layout.addWidget(self.lbl_clock)

        status_box_layout.addLayout(bottom_meta_layout)
        right_layout.addWidget(status_box, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Customer Logo Widget
        self.customer_logo = LogoWidget(
            logo_path=customer_logo_path,
            fallback_text="CUSTOMER",
            fallback_subtext="FACILITY PLANT",
            accent_color=IndustrialTheme.COLOR_GREEN,
            parent=self,
        )
        right_layout.addWidget(self.customer_logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(right_container, alignment=Qt.AlignmentFlag.AlignRight)

        # Clock timer (updates every second)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def set_line_name(self, name: str) -> None:
        """Update line name display."""
        self.line_name = name or "Assembly Line"
        self.lbl_line_name.setText(self.line_name.upper())

    def set_simulation_mode(self, enabled: bool) -> None:
        """Update simulation indicator badge."""
        self.simulation_mode = enabled
        if enabled:
            self.lbl_sim_pill.setText("SIMULATION MODE")
            self.lbl_sim_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_YELLOW_BG};
                    color: {IndustrialTheme.COLOR_YELLOW};
                    border: 1px solid {IndustrialTheme.COLOR_YELLOW_BORDER};
                    border-radius: 4px;
                    padding: 2px 7px;
                    font-size: 10px;
                    font-weight: bold;
                    letter-spacing: 0.5px;
                }}
            """)
        else:
            self.lbl_sim_pill.setText("HARDWARE PLC")
            self.lbl_sim_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_BLUE_BG};
                    color: {IndustrialTheme.TEXT_CYAN};
                    border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                    border-radius: 4px;
                    padding: 2px 7px;
                    font-size: 10px;
                    font-weight: bold;
                    letter-spacing: 0.5px;
                }}
            """)

    def set_connection_status(
        self,
        connected: bool,
        endpoint_info: str = "",
        scan_time_ms: float = 0.0,
    ) -> None:
        """Update connection badge and scan latency."""
        self._style_plc_pill(connected, endpoint_info)
        if connected:
            self.lbl_scan_time.setText(f"Scan: {scan_time_ms:.1f}ms")
        else:
            self.lbl_scan_time.setText("Scan: OFFLINE")

    def _style_plc_pill(self, connected: bool, endpoint_info: str = "") -> None:
        if connected:
            text = f"● PLC CONNECTED" + (f" ({endpoint_info})" if endpoint_info else "")
            self.lbl_plc_pill.setText(text)
            self.lbl_plc_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_GREEN_BG};
                    color: {IndustrialTheme.COLOR_GREEN};
                    border: 1px solid {IndustrialTheme.COLOR_GREEN_BORDER};
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: bold;
                    letter-spacing: 0.5px;
                }}
            """)
        else:
            text = "● PLC DISCONNECTED"
            self.lbl_plc_pill.setText(text)
            self.lbl_plc_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_RED_BG};
                    color: {IndustrialTheme.COLOR_RED};
                    border: 1px solid {IndustrialTheme.COLOR_RED_BORDER};
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: bold;
                    letter-spacing: 0.5px;
                }}
            """)

    def _update_clock(self) -> None:
        utc_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        self.lbl_clock.setText(utc_str)
