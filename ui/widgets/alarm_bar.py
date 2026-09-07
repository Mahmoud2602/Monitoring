"""
High-Visibility Industrial Alarm Banner.
Instantly communicates active machine faults, line stoppages, and plant alarm states.
Visible from a distance with high contrast state shifts.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.theme import IndustrialTheme


class AlarmBar(QFrame):
    """
    Control room alarm banner that visually transitions between calm healthy state
    and high-contrast critical stoppage/alarm alert.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlarmBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # Left: Big Icon/Beacon symbol
        self.lbl_icon = QLabel("✓", self)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setFixedWidth(28)

        # Main message text
        self.lbl_message = QLabel("NO ACTIVE ALARMS", self)
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Right: Secondary details / timestamp
        self.lbl_details = QLabel("System Healthy", self)
        self.lbl_details.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_message, stretch=1)
        layout.addWidget(self.lbl_details)

        # Initialize in healthy state
        self.clear_alarm()

    def clear_alarm(self) -> None:
        """Render calm, healthy industrial state."""
        self.setStyleSheet(f"""
            QFrame#AlarmBar {{
                background-color: #0b2216;
                border: 1px solid {IndustrialTheme.COLOR_GREEN_BORDER};
                border-radius: 6px;
            }}
        """)
        self.lbl_icon.setText("✓")
        self.lbl_icon.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.COLOR_GREEN};
                font-size: 18px;
                font-weight: bold;
            }}
        """)
        self.lbl_message.setText("NO ACTIVE ALARMS")
        self.lbl_message.setStyleSheet(f"""
            QLabel {{
                color: #86efac;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 1.0px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)
        self.lbl_details.setText("All automated workstations nominal")
        self.lbl_details.setStyleSheet(f"""
            QLabel {{
                color: #4ade80;
                font-size: 12px;
                font-weight: 500;
            }}
        """)

    def set_alarm(
        self,
        message: str,
        details: str = "",
        severity: str = "CRITICAL",
    ) -> None:
        """
        Render urgent high-contrast alert state.
        Visible across the factory control room floor.
        """
        is_critical = severity.upper() in ("CRITICAL", "HIGH", "FAULT", "STOPPED")
        bg_color = "#7f1d1d" if is_critical else "#78350f"
        border_color = IndustrialTheme.COLOR_RED if is_critical else IndustrialTheme.COLOR_YELLOW
        text_color = "#fef2f2" if is_critical else "#fffbeb"
        icon_color = "#fca5a5" if is_critical else "#fde047"
        icon_char = "⚠"

        self.setStyleSheet(f"""
            QFrame#AlarmBar {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 6px;
            }}
        """)
        self.lbl_icon.setText(icon_char)
        self.lbl_icon.setStyleSheet(f"""
            QLabel {{
                color: {icon_color};
                font-size: 20px;
                font-weight: bold;
            }}
        """)
        self.lbl_message.setText(message.upper())
        self.lbl_message.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-size: 15px;
                font-weight: 900;
                letter-spacing: 1.0px;
                font-family: {IndustrialTheme.FONT_FAMILY_UI};
            }}
        """)
        self.lbl_details.setText(details)
        self.lbl_details.setStyleSheet(f"""
            QLabel {{
                color: #fecaca if is_critical else #fef08a;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
