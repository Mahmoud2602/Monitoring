"""
Industrial UI Theme & Stylesheet definitions for PySide6.
Professional, high-contrast dark industrial control room aesthetic.
Designed for distance legibility, clean visual hierarchy, and minimal clutter.
"""
from __future__ import annotations

from typing import Dict


class IndustrialTheme:
    """Color palette and layout tokens for the industrial dashboard."""

    # Canvas & Backgrounds
    BG_DARK = "#0b0f19"         # Deepest canvas background
    BG_PANEL = "#111827"        # Secondary container surface
    BG_CARD = "#1f2937"         # Primary card background
    BG_CARD_HOVER = "#283548"   # Interactive card hover
    BG_CARD_ELEVATED = "#1e293b"# Highlighted card background
    
    # Borders & Dividers
    BORDER_SUBTLE = "#374151"   # Standard card border
    BORDER_FOCUS = "#4b5563"    # Focused or active border
    BORDER_DIVIDER = "#1e293b"  # Internal separators

    # Typography & Monospace
    TEXT_PRIMARY = "#f9fafb"    # Bright white/light gray
    TEXT_SECONDARY = "#9ca3af"  # Subdued gray for labels
    TEXT_MUTED = "#6b7280"      # Dim gray for secondary footnotes
    TEXT_CYAN = "#38bdf8"       # Technical readouts & telemetry

    # Machine & Process States
    COLOR_GREEN = "#22c55e"     # Running / Healthy / Synchronized
    COLOR_GREEN_BG = "#052e16"  # Subtle green glow/badge
    COLOR_GREEN_BORDER = "#15803d"

    COLOR_RED = "#ef4444"       # Stopped / Fault / Critical Alarm
    COLOR_RED_BG = "#450a0a"    # Active alarm background
    COLOR_RED_BORDER = "#b91c1c"

    COLOR_YELLOW = "#f59e0b"    # Warning / Attention / Degraded
    COLOR_YELLOW_BG = "#451a03"
    COLOR_YELLOW_BORDER = "#d97706"

    COLOR_GRAY = "#6b7280"      # Unknown / Disconnected / Offline
    COLOR_GRAY_BG = "#1f2937"
    COLOR_GRAY_BORDER = "#4b5563"

    COLOR_BLUE = "#0ea5e9"      # Info / System setpoints
    COLOR_BLUE_BG = "#0c4a6e"
    COLOR_BLUE_BORDER = "#0284c7"

    # Font stacks
    FONT_FAMILY_UI = "Segoe UI, -apple-system, Roboto, Helvetica Neue, sans-serif"
    FONT_FAMILY_MONO = "Consolas, SFMono-Regular, Menlo, Monaco, DejaVu Sans Mono, monospace"


def get_application_stylesheet() -> str:
    """Return the global QSS stylesheet for the native industrial desktop app."""
    return f"""
    QMainWindow {{
        background-color: {IndustrialTheme.BG_DARK};
        color: {IndustrialTheme.TEXT_PRIMARY};
    }}

    QWidget {{
        background-color: transparent;
        color: {IndustrialTheme.TEXT_PRIMARY};
        font-family: {IndustrialTheme.FONT_FAMILY_UI};
    }}

    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        border: none;
        background: {IndustrialTheme.BG_PANEL};
        width: 10px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background: {IndustrialTheme.BORDER_SUBTLE};
        min-height: 25px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {IndustrialTheme.BORDER_FOCUS};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        border: none;
        background: none;
    }}

    QProgressBar {{
        border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
        border-radius: 4px;
        background-color: {IndustrialTheme.BG_DARK};
        text-align: center;
        color: {IndustrialTheme.TEXT_PRIMARY};
        font-size: 11px;
        font-weight: bold;
    }}

    QProgressBar::chunk {{
        background-color: {IndustrialTheme.COLOR_GREEN};
        border-radius: 3px;
    }}

    QToolTip {{
        background-color: {IndustrialTheme.BG_CARD_ELEVATED};
        color: {IndustrialTheme.TEXT_PRIMARY};
        border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
    }}
    """
