"""
Industrial PLC Production Monitor - Export & Reporting Subsystem
Supports exporting historical datasets to CSV and formatted Daily Production Reports.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from database.database_manager import DatabaseManager
from database.query_service import DatePreset, HistoricalQueryService
from database.summary_service import DailySummaryService
from utils.logger import get_logger

logger = get_logger("database.export")


class ExportService:
    """
    Handles CSV and text exports for historical production analysis,
    downtime logs, alarm histories, station breakdowns, and executive daily reports.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        query_service: Optional[HistoricalQueryService] = None,
        summary_service: Optional[DailySummaryService] = None,
    ) -> None:
        self.db = db_manager
        self.query_service = query_service or HistoricalQueryService(db_manager)
        self.summary_service = summary_service or DailySummaryService(db_manager)

    def export_historical_to_csv(
        self,
        preset: Union[DatePreset, str] = DatePreset.TODAY,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        station_id: Optional[int] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
        output_dir: str = "exports",
    ) -> Dict[str, str]:
        """
        Generate separate standardized CSV files for:
        - hourly_production.csv
        - downtime_events.csv
        - alarm_events.csv
        - station_downtime_analysis.csv

        Returns dictionary of file paths created.
        """
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        created_files: Dict[str, str] = {}

        dataset = self.query_service.get_export_dataset(
            preset=preset,
            start_date=start_date,
            end_date=end_date,
            station_id=station_id,
            station_display_names=station_display_names,
        )

        # 1. Hourly Production Trend CSV
        hourly_file = os.path.join(output_dir, f"hourly_production_{ts}.csv")
        prod_trend = dataset.get("production_trend", {})
        hours = prod_trend.get("hours", [])
        actuals = prod_trend.get("actual_production", [])
        targets = prod_trend.get("hourly_target", [])
        achieves = dataset.get("achievement_trend", {}).get("hourly_achievement", [])

        with open(hourly_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Hour", "Target (pcs)", "Actual Production (pcs)", "Achievement (%)"])
            for h, act, tgt, ach in zip(hours, actuals, targets, achieves):
                writer.writerow([h, tgt, act, ach])
        created_files["hourly_production"] = hourly_file

        # 2. Downtime Events CSV
        dt_file = os.path.join(output_dir, f"downtime_events_{ts}.csv")
        dt_events = dataset.get("downtime_events", [])
        with open(dt_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Event ID",
                "Start Time",
                "End Time",
                "Station ID",
                "Station Name",
                "PLC Address",
                "Duration (s)",
                "Reason",
                "Status",
            ])
            for d in dt_events:
                writer.writerow([
                    d.get("id", ""),
                    d.get("start_time", ""),
                    d.get("end_time", ""),
                    d.get("station_id", ""),
                    d.get("station_name", ""),
                    d.get("plc_address", ""),
                    d.get("duration_seconds", ""),
                    d.get("stop_reason", ""),
                    d.get("status", ""),
                ])
        created_files["downtime_events"] = dt_file

        # 3. Alarm Events CSV
        alarm_file = os.path.join(output_dir, f"alarm_events_{ts}.csv")
        alarms = dataset.get("alarm_events", [])
        with open(alarm_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Alarm ID",
                "Timestamp",
                "Station ID",
                "Station Name",
                "Alarm Code",
                "Message",
                "Severity",
                "Duration (s)",
                "Status",
            ])
            for a in alarms:
                writer.writerow([
                    a.get("id", ""),
                    a.get("timestamp", ""),
                    a.get("station_id", ""),
                    a.get("station_name", ""),
                    a.get("alarm_code", ""),
                    a.get("alarm_message", ""),
                    a.get("severity", ""),
                    a.get("duration_seconds", ""),
                    a.get("status", ""),
                ])
        created_files["alarm_events"] = alarm_file

        # 4. Station Analysis CSV
        station_file = os.path.join(output_dir, f"station_analysis_{ts}.csv")
        st_dt = dataset.get("station_downtime", {})
        names = st_dt.get("station_names", [])
        dts = st_dt.get("downtime_seconds", [])
        stops = dataset.get("station_stops", {}).get("stop_counts", [])

        with open(station_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Station Name", "Total Downtime (s)", "Stop Count"])
            for name, d_sec, st_cnt in zip(names, dts, stops):
                writer.writerow([name, d_sec, st_cnt])
        created_files["station_analysis"] = station_file

        logger.info("Exported historical datasets to CSV: %s", created_files)
        return created_files

    def generate_daily_report(
        self,
        line_name: str,
        production_date: str,
        daily_target: Optional[float] = None,
        station_display_names: Optional[Dict[Any, str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive Daily Production Report dictionary for production review.
        """
        # Ensure daily summary is up to date
        summary_rec = self.summary_service.generate_daily_summary(
            production_date=production_date,
            daily_target=daily_target,
        )

        # Retrieve hourly breakdown and find best/worst hours
        hourly_records = self.query_service.prod_repo.get_by_date(production_date)
        best_hour = "--"
        worst_hour = "--"
        best_prod = -1
        worst_prod = 9999999

        for r in hourly_records:
            if r.actual_production > best_prod:
                best_prod = r.actual_production
                best_hour = f"{r.hour_start}-{r.hour_end} ({r.actual_production} pcs)"
            if r.actual_production < worst_prod:
                worst_prod = r.actual_production
                worst_hour = f"{r.hour_start}-{r.hour_end} ({r.actual_production} pcs)"

        if best_prod == -1:
            best_hour = "No Data"
        if worst_prod == 9999999:
            worst_hour = "No Data"

        # Station downtime summary for this date
        st_dt = self.query_service.get_downtime_by_station_full(
            preset=production_date,
            start_date=production_date,
            end_date=production_date,
            station_display_names=station_display_names,
        )
        st_stops = self.query_service.get_stop_count_by_station_full(
            preset=production_date,
            start_date=production_date,
            end_date=production_date,
            station_display_names=station_display_names,
        )

        station_summary: List[Dict[str, Any]] = []
        for name, dur, stops in zip(
            st_dt.get("station_names", []),
            st_dt.get("downtime_seconds", []),
            st_stops.get("stop_counts", []),
        ):
            station_summary.append({
                "station_name": name,
                "downtime_seconds": dur,
                "stop_count": stops,
            })

        return {
            "line_name": line_name,
            "production_date": production_date,
            "target": summary_rec.daily_target,
            "actual": summary_rec.total_production,
            "achievement_percent": summary_rec.cumulative_achievement_percent,
            "total_downtime_seconds": summary_rec.total_downtime_seconds,
            "running_time_seconds": summary_rec.running_time_seconds,
            "number_of_stops": summary_rec.total_stops,
            "average_speed": summary_rec.average_speed,
            "average_tact_time": summary_rec.average_tact_time,
            "best_hour": best_hour,
            "worst_hour": worst_hour,
            "station_downtime_summary": station_summary,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def export_daily_report_csv(
        self,
        report: Dict[str, Any],
        output_file: Optional[str] = None,
    ) -> str:
        """Export daily report to CSV format."""
        if not output_file:
            os.makedirs("exports", exist_ok=True)
            p_date = report.get("production_date", "unknown")
            output_file = f"exports/daily_production_report_{p_date}.csv"

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["DAILY PRODUCTION REPORT"])
            writer.writerow(["Line Name", report.get("line_name", "")])
            writer.writerow(["Production Date", report.get("production_date", "")])
            writer.writerow(["Daily Target (pcs)", report.get("target", 0)])
            writer.writerow(["Actual Production (pcs)", report.get("actual", 0)])
            writer.writerow(["Achievement (%)", f"{report.get('achievement_percent', 0.0):.2f}"])
            writer.writerow(["Total Downtime (s)", report.get("total_downtime_seconds", 0.0)])
            writer.writerow(["Running Time (s)", report.get("running_time_seconds", 0.0)])
            writer.writerow(["Total Stops", report.get("number_of_stops", 0)])
            writer.writerow(["Average Speed (m/min)", f"{report.get('average_speed', 0.0):.2f}"])
            writer.writerow(["Average Tact Time (s)", f"{report.get('average_tact_time', 0.0):.2f}"])
            writer.writerow(["Best Hour", report.get("best_hour", "")])
            writer.writerow(["Worst Hour", report.get("worst_hour", "")])
            writer.writerow([])
            writer.writerow(["STATION DOWNTIME BREAKDOWN"])
            writer.writerow(["Station Name", "Downtime (s)", "Stop Count"])
            for st in report.get("station_downtime_summary", []):
                writer.writerow([st.get("station_name"), st.get("downtime_seconds"), st.get("stop_count")])

        logger.info("Exported daily production report to: %s", output_file)
        return output_file
