"""
Industrial Navigation Bar Widget.
Provides seamless tabbed navigation between Live Dashboard and Historical Analysis,
with extensible placeholders for future modules (Downtime, Alarms, Reports, Settings).
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ui.theme import IndustrialTheme


class NavigationBar(QFrame):
    """
    Control room navigation bar for switching views.
    Emits `page_selected(page_name: str, index: int)` signal.
    """
    page_selected = Signal(str, int)

    NAV_ITEMS = [
        ("DASHBOARD", "⏵ LIVE DASHBOARD", 0, True),
        ("HISTORICAL", "📊 HISTORICAL ANALYSIS", 1, True),
        ("DOWNTIME", "⏱️ DOWNTIME", 2, False),
        ("ALARMS", "⚠️ ALARMS", 3, False),
        ("REPORTS", "📑 REPORTS", 4, False),
        ("SETTINGS", "⚙️ SETTINGS", 5, False),
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("NavigationBar")
        self.buttons: List[QPushButton] = []
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(f"""
            QFrame#NavigationBar {{
                background-color: {IndustrialTheme.BG_PANEL};
                border-bottom: 1px solid {IndustrialTheme.BORDER_SUBTLE};
            }}
            QPushButton.nav-btn {{
                background-color: transparent;
                color: {IndustrialTheme.TEXT_SECONDARY};
                border: none;
                border-bottom: 3px solid transparent;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.8px;
            }}
            QPushButton.nav-btn:hover:enabled {{
                color: {IndustrialTheme.TEXT_PRIMARY};
                background-color: {IndustrialTheme.BG_CARD_HOVER};
            }}
            QPushButton.nav-btn:checked {{
                color: {IndustrialTheme.TEXT_CYAN};
                border-bottom: 3px solid {IndustrialTheme.COLOR_BLUE};
                background-color: {IndustrialTheme.BG_DARK};
            }}
            QPushButton.nav-btn:disabled {{
                color: {IndustrialTheme.TEXT_MUTED};
                font-weight: normal;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        for key, label, idx, enabled in self.NAV_ITEMS:
            btn = QPushButton(label, self)
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            btn.setEnabled(enabled)

            if not enabled:
                btn.setToolTip("Planned feature module")

            if idx == 0:
                btn.setChecked(True)

            btn.clicked.connect(lambda checked, k=key, i=idx: self._on_btn_clicked(k, i))
            self.btn_group.addButton(btn, idx)
            self.buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)

        # Right status indicator
        self.lbl_mode = QLabel("MODE: CONTINUOUS PRODUCTION LINE", self)
        self.lbl_mode.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_MUTED};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
            font-family: {IndustrialTheme.FONT_FAMILY_MONO};
            margin-right: 8px;
        """)
        layout.addWidget(self.lbl_mode)

    def _on_btn_clicked(self, key: str, index: int) -> None:
        self.page_selected.emit(key, index)

    def set_active_index(self, index: int) -> None:
        """Programmatically switch active tab."""
        btn = self.btn_group.button(index)
        if btn and btn.isEnabled():
            btn.setChecked(True)
