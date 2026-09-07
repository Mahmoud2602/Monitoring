"""
Industrial Logo Widget supporting configured image assets or graceful fallback placeholders.
Never crashes on missing or corrupted image assets.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QFrame

from ui.theme import IndustrialTheme


class LogoWidget(QFrame):
    """
    Renders an image from file path or falls back to a clean industrial monogram badge.
    """

    def __init__(
        self,
        logo_path: Optional[str] = None,
        fallback_text: str = "COMPANY",
        fallback_subtext: str = "AUTOMATION",
        accent_color: str = IndustrialTheme.COLOR_BLUE,
        max_height: int = 46,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.logo_path = logo_path
        self.fallback_text = fallback_text
        self.fallback_subtext = fallback_subtext
        self.accent_color = accent_color
        self.max_height = max_height

        self.setObjectName("LogoWidget")
        self.setStyleSheet("background: transparent; border: none;")

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        self._build_ui()

    def set_logo_path(self, path: Optional[str]) -> None:
        """Update logo file path dynamically."""
        self.logo_path = path
        # Clear existing layout items
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._build_ui()

    def _build_ui(self) -> None:
        # Check if file exists and can be loaded
        loaded_pixmap: Optional[QPixmap] = None
        if self.logo_path and os.path.isfile(self.logo_path):
            try:
                pix = QPixmap(self.logo_path)
                if not pix.isNull():
                    loaded_pixmap = pix.scaledToHeight(
                        self.max_height, Qt.TransformationMode.SmoothTransformation
                    )
            except Exception:
                loaded_pixmap = None

        if loaded_pixmap:
            img_label = QLabel(self)
            img_label.setPixmap(loaded_pixmap)
            img_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._layout.addWidget(img_label)
        else:
            # Render a clean, high-contrast industrial monogram badge
            badge = QFrame(self)
            badge.setFixedSize(36, 36)
            badge.setStyleSheet(f"""
                QFrame {{
                    background-color: {self.accent_color};
                    border-radius: 6px;
                }}
            """)
            badge_layout = QVBoxLayout(badge)
            badge_layout.setContentsMargins(0, 0, 0, 0)

            initial = self.fallback_text[0].upper() if self.fallback_text else "P"
            badge_lbl = QLabel(initial, badge)
            badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_lbl.setStyleSheet(f"""
                QLabel {{
                    color: #ffffff;
                    font-size: 16px;
                    font-weight: 800;
                    font-family: {IndustrialTheme.FONT_FAMILY_UI};
                }}
            """)
            badge_layout.addWidget(badge_lbl)
            self._layout.addWidget(badge)

            # Text labels
            text_container = QWidget(self)
            text_layout = QVBoxLayout(text_container)
            text_layout.setContentsMargins(0, 2, 0, 2)
            text_layout.setSpacing(1)

            lbl_title = QLabel(self.fallback_text.upper(), text_container)
            lbl_title.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.TEXT_PRIMARY};
                    font-size: 12px;
                    font-weight: 800;
                    letter-spacing: 0.5px;
                }}
            """)

            lbl_sub = QLabel(self.fallback_subtext.upper(), text_container)
            lbl_sub.setStyleSheet(f"""
                QLabel {{
                    color: {IndustrialTheme.TEXT_MUTED};
                    font-size: 9px;
                    font-weight: 600;
                    letter-spacing: 0.3px;
                }}
            """)

            text_layout.addWidget(lbl_title)
            text_layout.addWidget(lbl_sub)
            self._layout.addWidget(text_container)
