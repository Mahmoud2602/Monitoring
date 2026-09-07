"""
Historical Analysis Filter Bar Widget.
Provides quick date presets (Today, Yesterday, Last 7/30 days, 3 months, Custom Range),
calendar date pickers, station selection, and refresh trigger.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from database.query_service import DatePreset
from ui.theme import IndustrialTheme


class FilterBar(QFrame):
    """
    Industrial Filter Bar for Historical Analytics.
    Emits `filter_changed` signal whenever date range, preset, or station selection changes.
    """
    # Signal: (preset: str, start_date_str: str, end_date_str: str, station_id: Optional[int])
    filter_changed = Signal(str, str, str, object)
    export_requested = Signal()

    PRESET_OPTIONS = [
        ("Today", DatePreset.TODAY.value),
        ("Yesterday", DatePreset.YESTERDAY.value),
        ("Last 7 Days", DatePreset.LAST_7_DAYS.value),
        ("Last 30 Days", DatePreset.LAST_30_DAYS.value),
        ("Last 3 Months", DatePreset.LAST_3_MONTHS.value),
        ("Custom Range", DatePreset.CUSTOM.value),
    ]

    def __init__(
        self,
        station_display_names: Optional[Dict[Any, str]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.station_names = station_display_names or {}
        self.setObjectName("HistoricalFilterBar")
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(f"""
            QFrame#HistoricalFilterBar {{
                background-color: {IndustrialTheme.BG_PANEL};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QLabel {{
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            QComboBox {{
                background-color: {IndustrialTheme.BG_CARD};
                color: {IndustrialTheme.TEXT_PRIMARY};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 5px 12px;
                min-height: 22px;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                border: 1px solid {IndustrialTheme.BORDER_FOCUS};
                background-color: {IndustrialTheme.BG_CARD_HOVER};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_PRIMARY};
                selection-background-color: {IndustrialTheme.COLOR_BLUE_BG};
                selection-color: {IndustrialTheme.TEXT_CYAN};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
            }}
            QDateEdit {{
                background-color: {IndustrialTheme.BG_CARD};
                color: {IndustrialTheme.TEXT_PRIMARY};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 5px 8px;
                min-height: 22px;
                font-family: {IndustrialTheme.FONT_FAMILY_MONO};
                font-size: 12px;
                font-weight: bold;
            }}
            QDateEdit:hover {{
                border: 1px solid {IndustrialTheme.BORDER_FOCUS};
            }}
            QPushButton#btnApply {{
                background-color: {IndustrialTheme.COLOR_BLUE_BG};
                color: {IndustrialTheme.TEXT_CYAN};
                border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}
            QPushButton#btnApply:hover {{
                background-color: {IndustrialTheme.COLOR_BLUE};
                color: #ffffff;
            }}
            QPushButton#btnExport {{
                background-color: {IndustrialTheme.BG_CARD};
                color: {IndustrialTheme.TEXT_PRIMARY};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#btnExport:hover {{
                background-color: {IndustrialTheme.BG_CARD_HOVER};
                border-color: {IndustrialTheme.TEXT_SECONDARY};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Top row: Controls (Preset, Custom Dates, Station, Apply Button, Export Button)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)

        # 1. Preset Combo
        preset_box = QVBoxLayout()
        preset_box.setSpacing(3)
        lbl_preset = QLabel("DATE PRESET")
        self.combo_preset = QComboBox(self)
        for label, val in self.PRESET_OPTIONS:
            self.combo_preset.addItem(label, val)
        self.combo_preset.setCurrentIndex(0)  # Default: Today
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        preset_box.addWidget(lbl_preset)
        preset_box.addWidget(self.combo_preset)
        controls_layout.addLayout(preset_box)

        # 2. Start Date
        start_box = QVBoxLayout()
        start_box.setSpacing(3)
        lbl_start = QLabel("START DATE")
        self.date_start = QDateEdit(self)
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate())
        self.date_start.setEnabled(False)
        start_box.addWidget(lbl_start)
        start_box.addWidget(self.date_start)
        controls_layout.addLayout(start_box)

        # 3. End Date
        end_box = QVBoxLayout()
        end_box.setSpacing(3)
        lbl_end = QLabel("END DATE")
        self.date_end = QDateEdit(self)
        self.date_end.setCalendarPopup(True)
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setEnabled(False)
        end_box.addWidget(lbl_end)
        end_box.addWidget(self.date_end)
        controls_layout.addLayout(end_box)

        # 4. Station Filter
        station_box = QVBoxLayout()
        station_box.setSpacing(3)
        lbl_station = QLabel("WORKSTATION FILTER")
        self.combo_station = QComboBox(self)
        self.combo_station.addItem("All Stations (1 - 10)", None)
        for st_id in range(1, 11):
            name = (
                self.station_names.get(str(st_id))
                or self.station_names.get(st_id)
                or f"Station {st_id}"
            )
            self.combo_station.addItem(f"Station {st_id:02d}: {name}", st_id)
        station_box.addWidget(lbl_station)
        station_box.addWidget(self.combo_station)
        controls_layout.addLayout(station_box)

        controls_layout.addStretch(1)

        # 5. Apply Button
        btn_apply_box = QVBoxLayout()
        btn_apply_box.setSpacing(3)
        lbl_empty = QLabel(" ")
        self.btn_apply = QPushButton("APPLY FILTERS", self)
        self.btn_apply.setObjectName("btnApply")
        self.btn_apply.clicked.connect(self.trigger_apply)
        btn_apply_box.addWidget(lbl_empty)
        btn_apply_box.addWidget(self.btn_apply)
        controls_layout.addLayout(btn_apply_box)

        # 6. Export Button
        btn_export_box = QVBoxLayout()
        btn_export_box.setSpacing(3)
        lbl_empty2 = QLabel(" ")
        self.btn_export = QPushButton("EXPORT JSON", self)
        self.btn_export.setObjectName("btnExport")
        self.btn_export.clicked.connect(self.export_requested.emit)
        btn_export_box.addWidget(lbl_empty2)
        btn_export_box.addWidget(self.btn_export)
        controls_layout.addLayout(btn_export_box)

        main_layout.addLayout(controls_layout)

        # Bottom info row: Active Range status summary
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        self.lbl_active_info = QLabel("ACTIVE PERIOD: Loading...", self)
        self.lbl_active_info.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_CYAN};
            font-size: 11px;
            font-weight: bold;
            font-family: {IndustrialTheme.FONT_FAMILY_MONO};
        """)
        info_row.addWidget(self.lbl_active_info)
        info_row.addStretch(1)

        self.lbl_update_time = QLabel("", self)
        self.lbl_update_time.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_MUTED};
            font-size: 11px;
        """)
        info_row.addWidget(self.lbl_update_time)

        main_layout.addLayout(info_row)

    def _on_preset_changed(self, index: int) -> None:
        val = self.combo_preset.currentData()
        is_custom = (val == DatePreset.CUSTOM.value)
        self.date_start.setEnabled(is_custom)
        self.date_end.setEnabled(is_custom)

        # Automatically trigger filter update when switching presets
        self.trigger_apply()

    def set_station_names(self, station_display_names: Dict[Any, str]) -> None:
        """Update station names dynamically if configuration changes."""
        self.station_names = station_display_names or {}
        cur_data = self.combo_station.currentData()
        self.combo_station.blockSignals(True)
        self.combo_station.clear()
        self.combo_station.addItem("All Stations (1 - 10)", None)
        for st_id in range(1, 11):
            name = (
                self.station_names.get(str(st_id))
                or self.station_names.get(st_id)
                or f"Station {st_id}"
            )
            self.combo_station.addItem(f"Station {st_id:02d}: {name}", st_id)

        # Restore selection
        idx = self.combo_station.findData(cur_data)
        if idx >= 0:
            self.combo_station.setCurrentIndex(idx)
        self.combo_station.blockSignals(False)

    def trigger_apply(self) -> None:
        """Collect current filter values and emit signal."""
        preset = str(self.combo_preset.currentData())
        start_date_str = self.date_start.date().toString("yyyy-MM-dd")
        end_date_str = self.date_end.date().toString("yyyy-MM-dd")
        station_id = self.combo_station.currentData()

        # Update status line
        now_str = datetime.now().strftime("%H:%M:%S")
        self.lbl_update_time.setText(f"Last Refreshed: {now_str}")

        self.filter_changed.emit(preset, start_date_str, end_date_str, station_id)

    def set_active_summary_text(self, text: str) -> None:
        """Set the active period text display."""
        self.lbl_active_info.setText(text)
