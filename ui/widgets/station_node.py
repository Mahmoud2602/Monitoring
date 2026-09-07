"""
Individual Station Node Widget.
Displays station number, configurable display name, PLC register tag,
operational status beacon, and active stoppage duration.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme


class StationNode(QFrame):
    """
    Visual component for a single workstation on the production line.
    Has completely independent status rendering.
    """

    def __init__(
        self,
        station_id: int,
        display_name: str,
        plc_address: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.station_id = station_id
        self.display_name = display_name
        self.plc_address = plc_address
        self.is_running = True
        self.is_connected = True
        self.stoppage_seconds: float = 0.0

        self.setObjectName(f"StationNode_{station_id}")
        self.setMinimumWidth(110)
        self.setMaximumWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header: ID Badge & PLC Register Tag
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        self.lbl_id_badge = QLabel(f"ST-{station_id:02d}", self)
        self.lbl_id_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {IndustrialTheme.BG_DARK};
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 10px;
                font-weight: bold;
                border-radius: 3px;
                padding: 1px 4px;
            }}
        """)
        top_row.addWidget(self.lbl_id_badge)

        self.lbl_plc_tag = QLabel(plc_address or f"M55{station_id-1}", self)
        self.lbl_plc_tag.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 9px;
            }}
        """)
        self.lbl_plc_tag.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.lbl_plc_tag)

        layout.addLayout(top_row)

        # Status Beacon Circle
        beacon_row = QHBoxLayout()
        beacon_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_beacon = QLabel("●", self)
        self.lbl_beacon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_beacon.setFixedSize(32, 32)
        beacon_row.addWidget(self.lbl_beacon)

        layout.addLayout(beacon_row)

        # Station Display Name
        self.lbl_name = QLabel(self.display_name, self)
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 700;
                line-height: 1.2;
            }}
        """)
        layout.addWidget(self.lbl_name)

        # Status Pill / Duration
        self.lbl_status_pill = QLabel("RUNNING", self)
        self.lbl_status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status_pill)

        # Initialize to healthy running state
        self.set_status(is_running=True, is_connected=True, stoppage_seconds=0.0)

    def update_display_name(self, name: str) -> None:
        """Dynamically update station display name without modifying station ID."""
        self.display_name = name
        self.lbl_name.setText(name)

    def set_status(
        self,
        is_running: bool,
        is_connected: bool = True,
        stoppage_seconds: float = 0.0,
    ) -> None:
        """
        Update the visual state of this specific workstation.
        Critical: Changes ONLY this station's styling.
        """
        self.is_running = is_running
        self.is_connected = is_connected
        self.stoppage_seconds = stoppage_seconds

        if not is_connected:
            # OFFLINE / DISCONNECTED STATE
            self.setStyleSheet(f"""
                QFrame#StationNode_{self.station_id} {{
                    background-color: {IndustrialTheme.BG_CARD};
                    border: 1px dashed {IndustrialTheme.COLOR_GRAY};
                    border-radius: 6px;
                }}
            """)
            self.lbl_beacon.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.COLOR_GRAY};
                    font-size: 24px;
                }}
            """)
            self.lbl_status_pill.setText("OFFLINE")
            self.lbl_status_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.BG_DARK};
                    color: {IndustrialTheme.TEXT_MUTED};
                    font-size: 9px;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 4px;
                }}
            """)

        elif is_running:
            # RUNNING / HEALTHY STATE
            self.setStyleSheet(f"""
                QFrame#StationNode_{self.station_id} {{
                    background-color: {IndustrialTheme.BG_CARD};
                    border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                    border-radius: 6px;
                }}
                QFrame#StationNode_{self.station_id}:hover {{
                    border: 1px solid {IndustrialTheme.COLOR_GREEN};
                }}
            """)
            self.lbl_beacon.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.COLOR_GREEN};
                    font-size: 26px;
                }}
            """)
            self.lbl_status_pill.setText("RUNNING")
            self.lbl_status_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_GREEN_BG};
                    color: {IndustrialTheme.COLOR_GREEN};
                    border: 1px solid {IndustrialTheme.COLOR_GREEN_BORDER};
                    font-size: 9px;
                    font-weight: bold;
                    border-radius: 3px;
                    padding: 2px 4px;
                }}
            """)

        else:
            # STOPPED / FAULT STATE
            dur_str = f" ({int(stoppage_seconds)}s)" if stoppage_seconds > 0 else ""
            self.setStyleSheet(f"""
                QFrame#StationNode_{self.station_id} {{
                    background-color: #3b0707;
                    border: 2px solid {IndustrialTheme.COLOR_RED};
                    border-radius: 6px;
                }}
            """)
            self.lbl_beacon.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.COLOR_RED};
                    font-size: 28px;
                }}
            """)
            self.lbl_status_pill.setText(f"STOPPED{dur_str}")
            self.lbl_status_pill.setStyleSheet(f"""
                QLabel {{
                    background-color: {IndustrialTheme.COLOR_RED_BG};
                    color: #fca5a5;
                    border: 1px solid {IndustrialTheme.COLOR_RED_BORDER};
                    font-size: 9px;
                    font-weight: 800;
                    border-radius: 3px;
                    padding: 2px 4px;
                }}
            """)
