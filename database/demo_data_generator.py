"""
Industrial PLC Production Monitor - Demo Historical Data Generator
Populates realistic 7-day multi-shift historical records for immediate
testing and verification of charts, filters, metrics, and exports.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database.database_manager import DatabaseManager
from database.models import AlarmEventRecord, DowntimeEventRecord, ProductionDataRecord
from database.repositories import (
    AlarmRepository,
    DailySummaryRepository,
    DowntimeRepository,
    ProductionDataRepository,
)
from database.summary_service import DailySummaryService
from kpi.constants import PHYSICAL_STATION_MAP
from utils.logger import get_logger

logger = get_logger("database.demo_generator")


def generate_demo_historical_data(
    db_manager: DatabaseManager,
    days: int = 7,
    hourly_target: float = 100.0,
    daily_target: float = 1000.0,
    station_display_names: Optional[Dict[Any, str]] = None,
) -> Dict[str, int]:
    """
    Populate realistic historical records for the past `days` days.
    Generates:
      - Hourly production data records
      - Realistic closed downtime events with varied root causes
      - Alarm events correlated with downtime
      - Daily summary records

    Returns a summary dictionary with counts of generated records.
    """
    logger.info("Generating demo historical data for past %d days...", days)
    prod_repo = ProductionDataRepository(db_manager)
    dt_repo = DowntimeRepository(db_manager)
    alarm_repo = AlarmRepository(db_manager)
    summary_service = DailySummaryService(db_manager)

    disp_names = station_display_names or {}
    now = datetime.now(timezone.utc)

    records_count = {
        "production_records": 0,
        "downtime_records": 0,
        "alarm_records": 0,
        "daily_summaries": 0,
    }

    # Stop reasons for realistic industrial events
    stop_reasons = [
        "Part Feed Jam",
        "Sensor Misalignment",
        "Pneumatic Pressure Low",
        "Inspection Reject Spike",
        "Operator Manual Pause",
        "Feeder Empty",
        "Vision Camera Glare",
        "Guide Rail Obstruction",
    ]

    # Hours in a standard 08:00 - 18:00 manufacturing day
    operating_hours = [
        ("08:00", "09:00"),
        ("09:00", "10:00"),
        ("10:00", "11:00"),
        ("11:00", "12:00"),
        ("12:00", "13:00"),
        ("13:00", "14:00"),
        ("14:00", "15:00"),
        ("15:00", "16:00"),
        ("16:00", "17:00"),
        ("17:00", "18:00"),
    ]

    # Iterate over past days
    for day_offset in range(days - 1, -1, -1):
        target_date = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        cum_actual = 0
        cum_target = 0.0

        for idx, (h_start, h_end) in enumerate(operating_hours):
            # Realistic production variation: 88 to 108 parts
            # Lower output if downtime occurred
            has_downtime = (random.random() < 0.28)
            dt_duration = random.randint(30, 420) if has_downtime else 0

            if has_downtime:
                actual_prod = max(20, int(hourly_target * (1.0 - (dt_duration / 3600.0)) + random.randint(-6, 4)))
            else:
                actual_prod = int(hourly_target + random.randint(-7, 9))

            cum_actual += actual_prod
            cum_target += hourly_target

            hourly_achieve = round((actual_prod / hourly_target) * 100.0, 2)
            cum_achieve = round((cum_actual / cum_target) * 100.0, 2)
            avg_speed = round(random.uniform(43.0, 47.0), 2)
            tact = round(60.0 / (avg_speed / 0.75), 2) if avg_speed > 0 else 1.0

            prod_rec = ProductionDataRecord(
                id=None,
                production_date=target_date,
                hour_start=h_start,
                hour_end=h_end,
                hourly_target=hourly_target,
                actual_production=actual_prod,
                hourly_achievement_percent=hourly_achieve,
                cumulative_target=cum_target,
                cumulative_actual=cum_actual,
                cumulative_achievement_percent=cum_achieve,
                tact_time=tact,
                average_speed=avg_speed,
                created_at=f"{target_date}T{h_end}:00Z",
            )
            prod_repo.upsert(prod_rec)
            records_count["production_records"] += 1

            # Insert downtime & alarm if occurred
            if has_downtime:
                station_id = random.randint(1, 10)
                plc_addr = PHYSICAL_STATION_MAP[station_id][0]
                station_name = (
                    disp_names.get(str(station_id))
                    or disp_names.get(station_id)
                    or f"Station {station_id}"
                )
                reason = random.choice(stop_reasons)
                start_minute = random.randint(5, 45)
                start_iso = f"{target_date}T{h_start[:2]}:{start_minute:02d}:00Z"
                end_sec = (start_minute * 60) + dt_duration
                end_iso = f"{target_date}T{h_start[:2]}:{end_sec // 60:02d}:{end_sec % 60:02d}Z"

                dt_rec = DowntimeEventRecord(
                    id=None,
                    station_id=station_id,
                    station_name=station_name,
                    plc_address=plc_addr,
                    start_time=start_iso,
                    end_time=end_iso,
                    duration_seconds=float(dt_duration),
                    stop_reason=reason,
                    production_date=target_date,
                )
                dt_repo.insert(dt_rec)
                records_count["downtime_records"] += 1

                alarm_rec = AlarmEventRecord(
                    id=None,
                    timestamp=start_iso,
                    alarm_code=f"ALM_S{station_id}_{reason.split()[0].upper()}",
                    alarm_message=f"{station_name} Stop: {reason}",
                    severity="WARNING" if dt_duration < 180 else "CRITICAL",
                    station_id=station_id,
                    station_name=station_name,
                    plc_address=plc_addr,
                    active=False,
                    cleared_at=end_iso,
                    duration_seconds=float(dt_duration),
                    production_date=target_date,
                )
                alarm_repo.insert(alarm_rec)
                records_count["alarm_records"] += 1

        # Generate rolled up daily summary
        summary_service.generate_daily_summary(
            production_date=target_date,
            daily_target=daily_target,
        )
        records_count["daily_summaries"] += 1

    logger.info("Demo data generation complete: %s", records_count)
    return records_count
