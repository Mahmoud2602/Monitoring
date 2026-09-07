"""
Historical Data Tables for Industrial Analysis.
Includes:
1. Downtime History Table (Date, Station ID, Station Name, Start Time, End Time, Duration, Alarm Code, Reason)
2. Alarm History Table (Timestamp, Station, Alarm Code, Alarm Message, Severity, Cleared At, Duration, Status)
With custom industrial dark styling, severity badges, and sorting.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme


class DowntimeTableWidget(QTableWidget):
    """Table widget presenting discrete station downtime events."""

    HEADERS = [
        "Date",
        "St ID",
        "Station Name",
        "Start Time",
        "End Time",
        "Duration",
        "Alarm ID",
        "Root Cause / Message",
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setShowGrid(True)
        self.setSortingEnabled(True)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {IndustrialTheme.BG_CARD};
                alternate-background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_PRIMARY};
                gridline-color: {IndustrialTheme.BORDER_DIVIDER};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 6px;
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-bottom: 2px solid {IndustrialTheme.BORDER_SUBTLE};
            }}
            QTableWidget::item:selected {{
                background-color: {IndustrialTheme.COLOR_BLUE_BG};
                color: {IndustrialTheme.TEXT_CYAN};
            }}
        """)

    def populate(self, rows: List[Dict[str, Any]]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))

        for row_idx, r in enumerate(rows):
            # 0: Date
            item_date = QTableWidgetItem(str(r.get("production_date", "")))
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_date.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 0, item_date)

            # 1: Station ID
            item_id = QTableWidgetItem(f"{r.get('station_id', 0):02d}")
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_id.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 1, item_id)

            # 2: Station Name
            item_name = QTableWidgetItem(str(r.get("station_name", "")))
            self.setItem(row_idx, 2, item_name)

            # 3: Start Time
            item_start = QTableWidgetItem(str(r.get("start_time", "")))
            item_start.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_start.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 3, item_start)

            # 4: End Time
            end_val = str(r.get("end_time", ""))
            item_end = QTableWidgetItem(end_val)
            item_end.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_end.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            if end_val == "ONGOING":
                item_end.setForeground(Qt.GlobalColor.red)
            self.setItem(row_idx, 4, item_end)

            # 5: Duration
            dur_str = str(r.get("duration_str", ""))
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_dur.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            if "ACTIVE" in dur_str:
                item_dur.setForeground(Qt.GlobalColor.red)
            self.setItem(row_idx, 5, item_dur)

            # 6: Alarm ID
            item_alarm = QTableWidgetItem(str(r.get("alarm_id", "--")))
            item_alarm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_alarm.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 6, item_alarm)

            # 7: Message
            item_msg = QTableWidgetItem(str(r.get("alarm_message", "")))
            self.setItem(row_idx, 7, item_msg)

        self.setSortingEnabled(True)


class AlarmTableWidget(QTableWidget):
    """Table widget presenting historical industrial alarms."""

    HEADERS = [
        "Timestamp",
        "St ID",
        "Station Name",
        "Code",
        "Alarm Message",
        "Severity",
        "Cleared At",
        "Duration",
        "Status",
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setShowGrid(True)
        self.setSortingEnabled(True)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {IndustrialTheme.BG_CARD};
                alternate-background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_PRIMARY};
                gridline-color: {IndustrialTheme.BORDER_DIVIDER};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 6px;
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-bottom: 2px solid {IndustrialTheme.BORDER_SUBTLE};
            }}
            QTableWidget::item:selected {{
                background-color: {IndustrialTheme.COLOR_BLUE_BG};
                color: {IndustrialTheme.TEXT_CYAN};
            }}
        """)

    def populate(self, rows: List[Dict[str, Any]]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))

        for row_idx, r in enumerate(rows):
            # 0: Timestamp
            item_ts = QTableWidgetItem(str(r.get("timestamp", "")))
            item_ts.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_ts.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 0, item_ts)

            # 1: Station ID
            st_id = r.get("station_id")
            st_text = f"{st_id:02d}" if st_id is not None else "--"
            item_id = QTableWidgetItem(st_text)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_id.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 1, item_id)

            # 2: Station Name
            item_name = QTableWidgetItem(str(r.get("station_name", "")))
            self.setItem(row_idx, 2, item_name)

            # 3: Alarm Code
            item_code = QTableWidgetItem(str(r.get("alarm_code", "")))
            item_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_code.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 3, item_code)

            # 4: Alarm Message
            item_msg = QTableWidgetItem(str(r.get("alarm_message", "")))
            self.setItem(row_idx, 4, item_msg)

            # 5: Severity Badge
            sev = str(r.get("severity", "WARNING")).upper()
            item_sev = QTableWidgetItem(sev)
            item_sev.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if sev == "CRITICAL":
                item_sev.setForeground(Qt.GlobalColor.red)
            elif sev == "WARNING":
                item_sev.setForeground(Qt.GlobalColor.yellow)
            else:
                item_sev.setForeground(Qt.GlobalColor.cyan)
            self.setItem(row_idx, 5, item_sev)

            # 6: Cleared At
            item_clear = QTableWidgetItem(str(r.get("cleared_at", "--")))
            item_clear.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_clear.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 6, item_clear)

            # 7: Duration
            item_dur = QTableWidgetItem(str(r.get("duration_str", "")))
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_dur.setFont(IndustrialTheme.FONT_FAMILY_MONO)
            self.setItem(row_idx, 7, item_dur)

            # 8: Status
            status = str(r.get("status", "CLEARED")).upper()
            item_stat = QTableWidgetItem(status)
            item_stat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "ACTIVE":
                item_stat.setForeground(Qt.GlobalColor.red)
            else:
                item_stat.setForeground(Qt.GlobalColor.green)
            self.setItem(row_idx, 8, item_stat)

        self.setSortingEnabled(True)


class HistoricalTablesCard(QFrame):
    """
    Tabbed container holding Downtime History and Alarm History tables,
    with severity filters and export triggers.
    """
    severity_filter_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("HistoricalTablesCard")
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(f"""
            QFrame#HistoricalTablesCard {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_SECONDARY};
                padding: 6px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {IndustrialTheme.COLOR_BLUE_BG};
                color: {IndustrialTheme.TEXT_CYAN};
                border: 1px solid {IndustrialTheme.COLOR_BLUE_BORDER};
                border-bottom: none;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {IndustrialTheme.BG_CARD_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        lbl_title = QLabel("HISTORICAL AUDIT LOGS", self)
        lbl_title.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_PRIMARY};
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.8px;
        """)
        header_row.addWidget(lbl_title)

        header_row.addStretch(1)

        # Severity Filter for Alarms
        lbl_sev = QLabel("Alarm Severity:", self)
        lbl_sev.setStyleSheet(f"color: {IndustrialTheme.TEXT_MUTED}; font-size: 11px; font-weight: 600;")
        self.combo_severity = QComboBox(self)
        self.combo_severity.addItems(["All", "CRITICAL", "WARNING", "INFO"])
        self.combo_severity.setStyleSheet(f"""
            QComboBox {{
                background-color: {IndustrialTheme.BG_PANEL};
                color: {IndustrialTheme.TEXT_PRIMARY};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
        """)
        self.combo_severity.currentTextChanged.connect(self.severity_filter_changed.emit)

        header_row.addWidget(lbl_sev)
        header_row.addWidget(self.combo_severity)

        self.lbl_record_count = QLabel("0 records", self)
        self.lbl_record_count.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_CYAN};
            font-family: {IndustrialTheme.FONT_FAMILY_MONO};
            font-size: 11px;
            font-weight: bold;
        """)
        header_row.addWidget(self.lbl_record_count)

        layout.addLayout(header_row)

        # Tab Widget
        self.tab_widget = QTabWidget(self)

        self.downtime_table = DowntimeTableWidget(self)
        self.alarm_table = AlarmTableWidget(self)

        self.tab_widget.addTab(self.downtime_table, "Downtime Events History")
        self.tab_widget.addTab(self.alarm_table, "Alarm & Faults Audit Log")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget, stretch=1)

        self._current_dt_count = 0
        self._current_alarm_count = 0

    def _on_tab_changed(self, index: int) -> None:
        if index == 0:
            self.lbl_record_count.setText(f"{self._current_dt_count} downtime events")
        else:
            self.lbl_record_count.setText(f"{self._current_alarm_count} alarm events")

    def update_downtime_data(self, rows: List[Dict[str, Any]]) -> None:
        self._current_dt_count = len(rows)
        self.downtime_table.populate(rows)
        if self.tab_widget.currentIndex() == 0:
            self.lbl_record_count.setText(f"{len(rows)} downtime events")

    def update_alarm_data(self, rows: List[Dict[str, Any]]) -> None:
        self._current_alarm_count = len(rows)
        self.alarm_table.populate(rows)
        if self.tab_widget.currentIndex() == 1:
            self.lbl_record_count.setText(f"{len(rows)} alarm events")
