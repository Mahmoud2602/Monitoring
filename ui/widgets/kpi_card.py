"""
Reusable Industrial KPI Card Component.
Designed for distance visibility, high-contrast typography, and clear process feedback.
Supports primary values, units, setpoint comparison, and visual progress meters.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme


class KPICard(QFrame):
    """
    Industrial metric card widget with large monospace values, units,
    secondary comparison values, and integrated progress meters.
    """

    def __init__(
        self,
        title: str,
        unit: str = "",
        accent_color: str = IndustrialTheme.COLOR_BLUE,
        show_progress: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.title_text = title
        self.unit_text = unit
        self.accent_color = accent_color
        self.show_progress = show_progress

        self.setObjectName("KPICard")
        self.setStyleSheet(f"""
            QFrame#KPICard {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame#KPICard:hover {{
                border-color: {IndustrialTheme.BORDER_FOCUS};
                background-color: {IndustrialTheme.BG_CARD_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Header Row: Title & Optional Trend/Tag
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel(self.title_text.upper(), self)
        self.lbl_title.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }}
        """)
        header_row.addWidget(self.lbl_title)

        header_row.addStretch(1)

        self.lbl_tag = QLabel("", self)
        self.lbl_tag.setStyleSheet(f"""
            QLabel {{
                color: {self.accent_color};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        header_row.addWidget(self.lbl_tag)

        layout.addLayout(header_row)

        # Value Row: Big Monospace Number + Unit
        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 2, 0, 2)
        value_row.setSpacing(6)
        value_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_value = QLabel("--", self)
        self.lbl_value.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 32px;
                font-weight: 900;
            }}
        """)
        value_row.addWidget(self.lbl_value)

        if self.unit_text:
            self.lbl_unit = QLabel(self.unit_text, self)
            self.lbl_unit.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.TEXT_MUTED};
                    font-size: 14px;
                    font-weight: 600;
                    margin-top: 10px;
                }}
            """)
            value_row.addWidget(self.lbl_unit)

        value_row.addStretch(1)
        layout.addLayout(value_row)

        # Progress bar (if enabled)
        if self.show_progress:
            self.progress_bar = QProgressBar(self)
            self.progress_bar.setFixedHeight(8)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    background-color: {IndustrialTheme.BG_DARK};
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {self.accent_color};
                    border-radius: 4px;
                }}
            """)
            layout.addWidget(self.progress_bar)

        # Subtitle / Details row
        self.lbl_details = QLabel("", self)
        self.lbl_details.setStyleSheet(f"""
            QLabel {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-size: 11px;
                font-weight: 500;
            }}
        """)
        layout.addWidget(self.lbl_details)

    def set_value(
        self,
        value_str: str,
        details: str = "",
        tag: str = "",
        progress_pct: Optional[float] = None,
        status_color: Optional[str] = None,
    ) -> None:
        """Update KPI card display values."""
        self.lbl_value.setText(value_str)

        if status_color:
            self.lbl_value.setStyleSheet(f"""
                QLabel {{
                    color: {status_color};
                    font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                    font-size: 32px;
                    font-weight: 900;
                }}
            """)
        else:
            self.lbl_value.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.TEXT_PRIMARY};
                    font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                    font-size: 32px;
                    font-weight: 900;
                }}
            """)

        if details:
            self.lbl_details.setText(details)

        if tag:
            self.lbl_tag.setText(tag)

        if self.show_progress and progress_pct is not None:
            clamped = max(0, min(100, int(progress_pct)))
            self.progress_bar.setValue(clamped)

            # Adapt progress bar chunk color dynamically
            color = IndustrialTheme.COLOR_GREEN
            if clamped < 70:
                color = IndustrialTheme.COLOR_RED
            elif clamped < 90:
                color = IndustrialTheme.COLOR_YELLOW

            self.progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    background-color: {IndustrialTheme.BG_DARK};
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)
