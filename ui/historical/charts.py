"""
PyQtGraph Interactive Charts for Industrial Historical Analysis.
Provides:
1. Production & Target Trend Chart
2. Conveyor Speed vs Setpoint Chart
3. Downtime Trend Chart
4. Station Downtime Bar Chart (Stations 1-10 with bottleneck highlight)
5. Station Stop Count Bar Chart (Stations 1-10)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import IndustrialTheme

# Configure global PyQtGraph defaults for industrial dark theme
pg.setConfigOption("background", IndustrialTheme.BG_CARD)
pg.setConfigOption("foreground", IndustrialTheme.TEXT_PRIMARY)
pg.setConfigOption("antialias", True)


class ChartCard(QFrame):
    """
    Standardized container card framing a PyQtGraph PlotWidget.
    Includes an industrial title bar, subtitle/legend notes, and empty data overlay.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("ChartCard")
        self._init_ui(title, subtitle)

    def _init_ui(self, title: str, subtitle: str) -> None:
        self.setStyleSheet(f"""
            QFrame#ChartCard {{
                background-color: {IndustrialTheme.BG_CARD};
                border: 1px solid {IndustrialTheme.BORDER_SUBTLE};
                border-radius: 8px;
            }}
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(6)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header_row.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel(title.upper(), self)
        lbl_title.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_PRIMARY};
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.8px;
        """)
        header_row.addWidget(lbl_title)

        if subtitle:
            lbl_sub = QLabel(f"({subtitle})", self)
            lbl_sub.setStyleSheet(f"""
                color: {IndustrialTheme.TEXT_MUTED};
                font-size: 11px;
                font-weight: 600;
            """)
            header_row.addWidget(lbl_sub)

        header_row.addStretch(1)

        self.lbl_status = QLabel("", self)
        self.lbl_status.setStyleSheet(f"""
            color: {IndustrialTheme.TEXT_CYAN};
            font-size: 10px;
            font-weight: bold;
            font-family: {IndustrialTheme.FONT_FAMILY_MONO};
        """)
        header_row.addWidget(self.lbl_status)

        self.layout.addLayout(header_row)

        # PyQtGraph Plot Widget
        self.plot_widget = pg.PlotWidget(self)
        self.plot_widget.setBackground(IndustrialTheme.BG_CARD)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.layout.addWidget(self.plot_widget, stretch=1)

        # Style plot axes
        for axis_name in ("bottom", "left"):
            ax = self.plot_widget.getAxis(axis_name)
            ax.setPen(pg.mkPen(IndustrialTheme.BORDER_SUBTLE, width=1))
            ax.setTextPen(pg.mkPen(IndustrialTheme.TEXT_SECONDARY))

        # Empty data overlay text item
        self.empty_text_item = pg.TextItem(
            text="NO HISTORICAL DATA FOR SELECTED PERIOD",
            color=IndustrialTheme.TEXT_MUTED,
            anchor=(0.5, 0.5),
        )
        f = QFont(IndustrialTheme.FONT_FAMILY_UI, 11)
        f.setBold(True)
        self.empty_text_item.setFont(f)
        self.empty_text_item.setVisible(False)
        self.plot_widget.addItem(self.empty_text_item)

    def show_empty_state(self, is_empty: bool) -> None:
        """Toggle empty state message when no data is returned."""
        self.empty_text_item.setVisible(is_empty)
        if is_empty:
            self.plot_widget.setRange(xRange=[-1, 1], yRange=[-1, 1])
            self.empty_text_item.setPos(0, 0)
            self.lbl_status.setText("NO RECORDS")
        else:
            self.lbl_status.setText("")


class ProductionTrendChart(ChartCard):
    """
    Production Trend Chart:
    - Actual Production (Green bars or curve)
    - Hourly/Daily Target (Cyan line)
    - Target Reference
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            title="Production Trend",
            subtitle="Actual vs Target (pcs)",
            parent=parent,
        )
        self.plot_widget.addLegend(offset=(10, 10), brush=pg.mkBrush("#111827cc"), pen=pg.mkPen(IndustrialTheme.BORDER_SUBTLE))
        self.plot_widget.setLabel("left", "Production", units="pcs")
        self.plot_widget.setLabel("bottom", "Time / Date")

    def update_data(self, data_list: List[Dict[str, Any]]) -> None:
        self.plot_widget.clear()
        # Re-add legend
        self.plot_widget.addLegend(offset=(10, 10), brush=pg.mkBrush("#111827cc"), pen=pg.mkPen(IndustrialTheme.BORDER_SUBTLE))
        self.plot_widget.addItem(self.empty_text_item)

        if not data_list:
            self.show_empty_state(True)
            return
        self.show_empty_state(False)

        x_indices = np.arange(len(data_list))
        labels = [str(d.get("time_label", "")) for d in data_list]
        actuals = np.array([float(d.get("actual", 0.0)) for d in data_list])
        targets = np.array([float(d.get("target", 0.0)) for d in data_list])

        # Bottom axis formatting
        ax_bottom = self.plot_widget.getAxis("bottom")
        step = max(1, len(labels) // 12)
        ticks = [(i, labels[i]) for i in range(0, len(labels), step)]
        ax_bottom.setTicks([ticks])

        # 1. Bar chart for Actual Production
        bar_item = pg.BarGraphItem(
            x=x_indices,
            height=actuals,
            width=0.55,
            brush=pg.mkBrush("#22c55e"),
            pen=pg.mkPen("#15803d", width=1),
            name="Actual (pcs)",
        )
        self.plot_widget.addItem(bar_item)

        # 2. Line curve for Target
        target_pen = pg.mkPen(color="#38bdf8", width=2, style=Qt.PenStyle.DashLine)
        target_curve = self.plot_widget.plot(
            x_indices,
            targets,
            pen=target_pen,
            symbol="o",
            symbolSize=6,
            symbolBrush="#38bdf8",
            name="Target (pcs)",
        )

        max_val = max(float(np.max(actuals)) if len(actuals) else 0.0, float(np.max(targets)) if len(targets) else 0.0)
        self.plot_widget.setYRange(0, max(max_val * 1.15, 10))
        self.plot_widget.setXRange(-0.5, len(labels) - 0.5)


class SpeedTrendChart(ChartCard):
    """
    Speed Trend Chart:
    - Actual Conveyor Speed (m/min)
    - Speed Setpoint (dashed amber line)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            title="Conveyor Speed Trend",
            subtitle="Actual vs Setpoint (m/min)",
            parent=parent,
        )
        self.plot_widget.addLegend(offset=(10, 10), brush=pg.mkBrush("#111827cc"), pen=pg.mkPen(IndustrialTheme.BORDER_SUBTLE))
        self.plot_widget.setLabel("left", "Speed", units="m/min")
        self.plot_widget.setLabel("bottom", "Time / Date")

    def update_data(self, data_list: List[Dict[str, Any]], default_setpoint: float = 45.0) -> None:
        self.plot_widget.clear()
        self.plot_widget.addLegend(offset=(10, 10), brush=pg.mkBrush("#111827cc"), pen=pg.mkPen(IndustrialTheme.BORDER_SUBTLE))
        self.plot_widget.addItem(self.empty_text_item)

        if not data_list:
            self.show_empty_state(True)
            return
        self.show_empty_state(False)

        x_indices = np.arange(len(data_list))
        labels = [str(d.get("time_label", "")) for d in data_list]
        speeds = np.array([float(d.get("actual_speed", 0.0)) for d in data_list])
        setpoints = np.array([float(d.get("speed_setpoint", default_setpoint)) for d in data_list])

        ax_bottom = self.plot_widget.getAxis("bottom")
        step = max(1, len(labels) // 12)
        ticks = [(i, labels[i]) for i in range(0, len(labels), step)]
        ax_bottom.setTicks([ticks])

        # Target Setpoint Line
        setpoint_pen = pg.mkPen(color="#f59e0b", width=2, style=Qt.PenStyle.DashLine)
        self.plot_widget.plot(
            x_indices,
            setpoints,
            pen=setpoint_pen,
            name="Setpoint (m/min)",
        )

        # Actual Speed Line with fill
        speed_pen = pg.mkPen(color="#38bdf8", width=2)
        self.plot_widget.plot(
            x_indices,
            speeds,
            pen=speed_pen,
            symbol="s",
            symbolSize=5,
            symbolBrush="#38bdf8",
            name="Actual Speed",
        )

        max_speed = max(float(np.max(speeds)) if len(speeds) else 0.0, float(np.max(setpoints)) if len(setpoints) else 0.0)
        self.plot_widget.setYRange(0, max(max_speed * 1.2, 50.0))
        self.plot_widget.setXRange(-0.5, len(labels) - 0.5)


class DowntimeTrendChart(ChartCard):
    """
    Downtime Trend Chart:
    - Downtime duration (minutes) over timeline
    - Highlight high-impact downtime periods
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            title="Downtime Trend",
            subtitle="Duration (Minutes) & Stops",
            parent=parent,
        )
        self.plot_widget.addLegend(offset=(10, 10), brush=pg.mkBrush("#111827cc"), pen=pg.mkPen(IndustrialTheme.BORDER_SUBTLE))
        self.plot_widget.setLabel("left", "Downtime", units="min")
        self.plot_widget.setLabel("bottom", "Time / Date")

    def update_data(self, data_list: List[Dict[str, Any]]) -> None:
        self.plot_widget.clear()
        self.plot_widget.addLegend(offset=(10, 10), brush=pg.mkBrush("#111827cc"), pen=pg.mkPen(IndustrialTheme.BORDER_SUBTLE))
        self.plot_widget.addItem(self.empty_text_item)

        if not data_list:
            self.show_empty_state(True)
            return
        self.show_empty_state(False)

        x_indices = np.arange(len(data_list))
        labels = [str(d.get("time_label", "")) for d in data_list]
        dt_mins = np.array([float(d.get("downtime_minutes", 0.0)) for d in data_list])

        ax_bottom = self.plot_widget.getAxis("bottom")
        step = max(1, len(labels) // 12)
        ticks = [(i, labels[i]) for i in range(0, len(labels), step)]
        ax_bottom.setTicks([ticks])

        # Red bars for downtime duration
        bar_item = pg.BarGraphItem(
            x=x_indices,
            height=dt_mins,
            width=0.55,
            brush=pg.mkBrush("#ef4444"),
            pen=pg.mkPen("#b91c1c", width=1),
            name="Downtime (min)",
        )
        self.plot_widget.addItem(bar_item)

        max_dt = float(np.max(dt_mins)) if len(dt_mins) else 0.0
        self.plot_widget.setYRange(0, max(max_dt * 1.25, 10.0))
        self.plot_widget.setXRange(-0.5, len(labels) - 0.5)


class StationDowntimeChart(ChartCard):
    """
    Station Downtime Analysis:
    - Bar chart for Stations 1 to 10
    - Configurable station names
    - Automatically highlights the top bottleneck station with a distinct alert color
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            title="Station Downtime Analysis",
            subtitle="Duration by Station (Minutes)",
            parent=parent,
        )
        self.plot_widget.setLabel("left", "Total Downtime", units="min")
        self.plot_widget.setLabel("bottom", "Workstation")

    def update_data(self, station_data_list: List[Dict[str, Any]]) -> None:
        self.plot_widget.clear()
        self.plot_widget.addItem(self.empty_text_item)

        if not station_data_list:
            self.show_empty_state(True)
            return
        self.show_empty_state(False)

        x_indices = np.arange(len(station_data_list))
        labels = [f"St {s.get('station_id')}\n{s.get('station_name', '')[:10]}" for s in station_data_list]
        mins = np.array([float(s.get("total_downtime_minutes", 0.0)) for s in station_data_list])

        # Find max bottleneck
        max_idx = int(np.argmax(mins)) if len(mins) > 0 and np.max(mins) > 0 else -1

        ax_bottom = self.plot_widget.getAxis("bottom")
        ticks = [(i, labels[i]) for i in range(len(labels))]
        ax_bottom.setTicks([ticks])

        # Draw individual bars so bottleneck is distinctively highlighted
        for i, val in enumerate(mins):
            is_bottleneck = (i == max_idx and val > 0)
            color = "#ef4444" if is_bottleneck else "#f59e0b"
            border = "#b91c1c" if is_bottleneck else "#d97706"
            bar = pg.BarGraphItem(
                x=[i],
                height=[val],
                width=0.6,
                brush=pg.mkBrush(color),
                pen=pg.mkPen(border, width=1.5 if is_bottleneck else 1.0),
            )
            self.plot_widget.addItem(bar)

        max_val = float(np.max(mins)) if len(mins) else 0.0
        self.plot_widget.setYRange(0, max(max_val * 1.25, 5.0))
        self.plot_widget.setXRange(-0.5, len(labels) - 0.5)

        if max_idx >= 0 and max_val > 0:
            bottleneck_name = station_data_list[max_idx].get("station_name", f"Station {max_idx+1}")
            self.lbl_status.setText(f"BOTTLENECK: St {max_idx+1} ({bottleneck_name}) - {max_val:.1f}m")
        else:
            self.lbl_status.setText("ALL STATIONS OPERATIONAL")


class StationStopsChart(ChartCard):
    """
    Station Stop Count Breakdown:
    - Frequency of stoppages per station across Stations 1 to 10
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            title="Station Stop Count Analysis",
            subtitle="Frequency of Stops by Station",
            parent=parent,
        )
        self.plot_widget.setLabel("left", "Stop Count", units="stops")
        self.plot_widget.setLabel("bottom", "Workstation")

    def update_data(self, station_data_list: List[Dict[str, Any]]) -> None:
        self.plot_widget.clear()
        self.plot_widget.addItem(self.empty_text_item)

        if not station_data_list:
            self.show_empty_state(True)
            return
        self.show_empty_state(False)

        x_indices = np.arange(len(station_data_list))
        labels = [f"St {s.get('station_id')}" for s in station_data_list]
        stops = np.array([int(s.get("stop_count", 0)) for s in station_data_list])

        ax_bottom = self.plot_widget.getAxis("bottom")
        ticks = [(i, labels[i]) for i in range(len(labels))]
        ax_bottom.setTicks([ticks])

        # Cyan/blue bars for frequency
        bar = pg.BarGraphItem(
            x=x_indices,
            height=stops,
            width=0.6,
            brush=pg.mkBrush("#0ea5e9"),
            pen=pg.mkPen("#0284c7", width=1),
        )
        self.plot_widget.addItem(bar)

        max_stops = int(np.max(stops)) if len(stops) else 0
        self.plot_widget.setYRange(0, max(max_stops * 1.25, 5))
        self.plot_widget.setXRange(-0.5, len(labels) - 0.5)
