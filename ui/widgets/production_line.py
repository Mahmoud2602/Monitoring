"""
Main Production Line Visualization Widget.
Displays the assembly line as ONE continuous visual production line across 10 stations,
divided only by a narrow physical transfer coupler between Station 5 and Station 6.
Enforces strict station status independence: when one station stops, ONLY that station turns RED.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from plc.plc_data import NormalizedPLCData
from ui.theme import IndustrialTheme
from ui.widgets.station_node import StationNode


class ProductionLineWidget(QFrame):
    """
    Renders the continuous 10-station industrial conveyor system.
    Conveyor 1 spans Stations 1-5, Conveyor 2 spans Stations 6-10.
    They visually align into one single, uninterrupted factory line.
    """

    def __init__(
        self,
        line_name: str = "Assembly Line",
        station_display_names: Optional[Dict[str, str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.line_name = line_name
        self.station_display_names = station_display_names or {}
        self.station_nodes: Dict[int, StationNode] = {}

        self.setObjectName("ProductionLineWidget")
        self.setStyleSheet(f"""
            QFrame#ProductionLineWidget {{
                background-color: {IndustrialTheme.BG_PANEL};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
                padding: 12px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. Top Section: Centered Line Title & Process Flow Indicator
        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 4, 0)

        lbl_infeed = QLabel("◀ INFEED (RAW PARTS)", self)
        lbl_infeed.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        header_row.addWidget(lbl_infeed)

        header_row.addStretch(1)

        self.lbl_title = QLabel(self.line_name.upper(), self)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 1.5px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)
        header_row.addWidget(self.lbl_title)

        header_row.addStretch(1)

        lbl_outfeed = QLabel("OUTFEED (FINISHED PRODUCTS) ▶", self)
        lbl_outfeed.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        header_row.addWidget(lbl_outfeed)

        main_layout.addLayout(header_row)

        # 2. Main Continuous Assembly Line (Stations 1 to 10 with narrow bridge)
        self.line_container = QFrame(self)
        self.line_container.setStyleSheet(f"""
            QFrame {{
                background-color: {IndustrialTheme.BG_DARK};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        line_layout = QHBoxLayout(self.line_container)
        line_layout.setContentsMargins(8, 8, 8, 8)
        line_layout.setSpacing(6)

        # Default standard PLC mapping address lookups
        plc_tags = {
            1: "M550", 2: "M551", 3: "M552", 4: "M553", 5: "M554",
            6: "M555", 7: "M556", 8: "M557", 9: "M558", 10: "M559"
        }

        # Build Stations 1 to 5 (Conveyor 1)
        for st_id in range(1, 6):
            name = self.station_display_names.get(str(st_id), f"Station {st_id}")
            node = StationNode(
                station_id=st_id,
                display_name=name,
                plc_address=plc_tags.get(st_id, ""),
                parent=self.line_container,
            )
            self.station_nodes[st_id] = node
            line_layout.addWidget(node, stretch=1)

        # Transfer Bridge / Gap between Conveyor 1 and Conveyor 2
        # VERY SMALL physical gap as mandated by requirements
        self.bridge_widget = QFrame(self.line_container)
        self.bridge_widget.setFixedWidth(24)
        self.bridge_widget.setStyleSheet(f"""
            QFrame {{
                background-color: {IndustrialTheme.BG_PANEL};
                border-left: 2px dashed {IndustrialTheme.BORDER_FOCUS};
                border-right: 2px dashed {IndustrialTheme.BORDER_FOCUS};
                border-top: none;
                border-bottom: none;
            }}
        """)
        bridge_layout = QVBoxLayout(self.bridge_widget)
        bridge_layout.setContentsMargins(0, 0, 0, 0)
        lbl_bridge = QLabel("⮞", self.bridge_widget)
        lbl_bridge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_bridge.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_CYAN};
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        bridge_layout.addWidget(lbl_bridge)
        line_layout.addWidget(self.bridge_widget)

        # Build Stations 6 to 10 (Conveyor 2)
        for st_id in range(6, 11):
            name = self.station_display_names.get(str(st_id), f"Station {st_id}")
            node = StationNode(
                station_id=st_id,
                display_name=name,
                plc_address=plc_tags.get(st_id, ""),
                parent=self.line_container,
            )
            self.station_nodes[st_id] = node
            line_layout.addWidget(node, stretch=1)

        main_layout.addWidget(self.line_container)

        # 3. Conveyor Track Bed Underneath (Indicating Conveyor 1 & Conveyor 2)
        track_row = QHBoxLayout()
        track_row.setContentsMargins(4, 0, 4, 0)
        track_row.setSpacing(6)

        # Conveyor 1 Bed Indicator
        self.conv1_bar = QFrame(self)
        self.conv1_bar.setStyleSheet(f"""
            QFrame {{
                background-color: #1e293b;
                border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                border-radius: 4px;
                padding: 3px 8px;
            }}
        """)
        conv1_layout = QHBoxLayout(self.conv1_bar)
        conv1_layout.setContentsMargins(4, 2, 4, 2)
        self.lbl_conv1_status = QLabel("CONVEYOR 1 (Stations 01–05) • ACTIVE", self.conv1_bar)
        self.lbl_conv1_status.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_CYAN};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        conv1_layout.addWidget(self.lbl_conv1_status)
        conv1_layout.addStretch(1)
        lbl_c1_arrows = QLabel("➔ ➔ ➔ ➔", self.conv1_bar)
        lbl_c1_arrows.setStyleSheet(f"color: {IndustrialTheme.BORDER_FOCUS}; font-size: 10px;")
        conv1_layout.addWidget(lbl_c1_arrows)
        track_row.addWidget(self.conv1_bar, stretch=1)

        # Small spacer matching bridge
        track_spacer = QFrame(self)
        track_spacer.setFixedWidth(24)
        track_row.addWidget(track_spacer)

        # Conveyor 2 Bed Indicator
        self.conv2_bar = QFrame(self)
        self.conv2_bar.setStyleSheet(f"""
            QFrame {{
                background-color: #1e293b;
                border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                border-radius: 4px;
                padding: 3px 8px;
            }}
        """)
        conv2_layout = QHBoxLayout(self.conv2_bar)
        conv2_layout.setContentsMargins(4, 2, 4, 2)
        self.lbl_conv2_status = QLabel("CONVEYOR 2 (Stations 06–10) • ACTIVE", self.conv2_bar)
        self.lbl_conv2_status.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_CYAN};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        conv2_layout.addWidget(self.lbl_conv2_status)
        conv2_layout.addStretch(1)
        lbl_c2_arrows = QLabel("➔ ➔ ➔ ➔", self.conv2_bar)
        lbl_c2_arrows.setStyleSheet(f"color: {IndustrialTheme.BORDER_FOCUS}; font-size: 10px;")
        conv2_layout.addWidget(lbl_c2_arrows)
        track_row.addWidget(self.conv2_bar, stretch=1)

        main_layout.addLayout(track_row)

    def set_line_name(self, name: str) -> None:
        """Update centered title label."""
        self.line_name = name or "Assembly Line"
        self.lbl_title.setText(self.line_name.upper())

    def update_station_names(self, mapping: Dict[str, str]) -> None:
        """Dynamically update station display names from config."""
        self.station_display_names = mapping
        for st_id, node in self.station_nodes.items():
            if str(st_id) in mapping:
                node.update_display_name(mapping[str(st_id)])

    def update_telemetry(
        self,
        data: NormalizedPLCData,
        stoppage_durations: Optional[Dict[int, float]] = None,
    ) -> None:
        """
        Update each station's independent status strictly from PLC telemetry.
        CRITICAL: If Station 7 stops, ONLY Station 7 turns RED.
        All other stations remain GREEN.
        """
        if stoppage_durations is None:
            stoppage_durations = {}

        # Station statuses dictionary from PLC data (support stations dict, station_status attr, or details)
        raw_stations = getattr(data, "stations", None)
        if raw_stations is None:
            raw_stations = getattr(data, "station_status", {}) or {}

        c1_any_stopped = False
        c2_any_stopped = False

        for st_id in range(1, 11):
            node = self.station_nodes.get(st_id)
            if not node:
                continue

            # Check various key formats (int, str, 'station_X', 'conv1_stationX', 'M55X')
            plc_addr = f"M55{st_id-1}"
            conv_idx = st_id if st_id <= 5 else (st_id - 5)
            conv_prefix = "conv1" if st_id <= 5 else "conv2"
            conv_key = f"{conv_prefix}_station{conv_idx}"

            is_running = True
            if st_id in raw_stations:
                is_running = bool(raw_stations[st_id])
            elif str(st_id) in raw_stations:
                is_running = bool(raw_stations[str(st_id)])
            elif f"station_{st_id}" in raw_stations:
                is_running = bool(raw_stations[f"station_{st_id}"])
            elif conv_key in raw_stations:
                is_running = bool(raw_stations[conv_key])
            elif plc_addr in raw_stations:
                is_running = bool(raw_stations[plc_addr])

            dur = stoppage_durations.get(st_id, 0.0)

            node.set_status(is_running=is_running, is_connected=True, stoppage_seconds=dur)

            if not is_running:
                if st_id <= 5:
                    c1_any_stopped = True
                else:
                    c2_any_stopped = True

        # Update conveyor track status banners
        if c1_any_stopped:
            self.lbl_conv1_status.setText("CONVEYOR 1 (Stations 01–05) • INTERRUPTED")
            self.conv1_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: #3b0707;
                    border: 1px solid {IndustrialTheme.COLOR_RED_BORDER};
                    border-radius: 4px;
                    padding: 3px 8px;
                }}
            """)
        else:
            self.lbl_conv1_status.setText("CONVEYOR 1 (Stations 01–05) • ACTIVE")
            self.conv1_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: #1e293b;
                    border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                    border-radius: 4px;
                    padding: 3px 8px;
                }}
            """)

        if c2_any_stopped:
            self.lbl_conv2_status.setText("CONVEYOR 2 (Stations 06–10) • INTERRUPTED")
            self.conv2_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: #3b0707;
                    border: 1px solid {IndustrialTheme.COLOR_RED_BORDER};
                    border-radius: 4px;
                    padding: 3px 8px;
                }}
            """)
        else:
            self.lbl_conv2_status.setText("CONVEYOR 2 (Stations 06–10) • ACTIVE")
            self.conv2_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: #1e293b;
                    border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                    border-radius: 4px;
                    padding: 3px 8px;
                }}
            """)

    def set_disconnected(self) -> None:
        """Render all station nodes as OFFLINE/UNKNOWN when PLC connection is lost."""
        for node in self.station_nodes.values():
            node.set_status(is_running=False, is_connected=False, stoppage_seconds=0.0)

        self.lbl_conv1_status.setText("CONVEYOR 1 • OFFLINE")
        self.conv1_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 3px 8px;
            }}
        """)
        self.lbl_conv2_status.setText("CONVEYOR 2 • OFFLINE")
        self.conv2_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 3px 8px;
            }}
        """)
