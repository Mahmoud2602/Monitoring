"""
Industrial PLC Production Monitor - Authoritative Production Day Logic

Single source of truth for plant production day calculations.
Handles shift start boundary calculations across midnight and arbitrary
configurable day start times (e.g., "08:00", "06:00", "07:30", "12:00").

Example with production_day_start = "08:00":
- 2026-09-07 07:59:59 -> Production date: 2026-09-06 (belongs to previous day's shift)
- 2026-09-07 08:00:00 -> Production date: 2026-09-07 (start of new production day)
- 2026-09-07 23:59:59 -> Production date: 2026-09-07
- 2026-09-08 00:00:00 -> Production date: 2026-09-07
- 2026-09-08 07:59:59 -> Production date: 2026-09-07
- 2026-09-08 08:00:00 -> Production date: 2026-09-08
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple, Union


def parse_day_start(day_start_str: str) -> Tuple[int, int]:
    """
    Parse a "HH:MM" or "HH:MM:SS" time string into (hour, minute) integers.
    Defaults to (8, 0) if invalid or empty.
    """
    if not day_start_str:
        return 8, 0
    try:
        parts = str(day_start_str).strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h, m
    except (ValueError, IndexError):
        return 8, 0


def get_production_date(
    timestamp_or_day_start: Union[datetime, str, None] = None,
    day_start_or_timestamp: Union[datetime, str, None] = None,
) -> str:
    """
    Determine the authoritative industrial production date string (YYYY-MM-DD).
    
    Supports both argument conventions for backwards compatibility:
      1. get_production_date(timestamp, day_start="08:00")
      2. get_production_date(day_start="08:00", timestamp=dt)
    
    If timestamp is None, current UTC time is used.
    """
    dt: Optional[datetime] = None
    day_start: str = "08:00"

    # Argument resolution to support both (dt, day_start) and (day_start, dt)
    if isinstance(timestamp_or_day_start, datetime):
        dt = timestamp_or_day_start
        if isinstance(day_start_or_timestamp, str):
            day_start = day_start_or_timestamp
    elif isinstance(timestamp_or_day_start, str):
        # Could be an ISO timestamp "2026-09-07T07:59:00" or a time string "08:00"
        s = timestamp_or_day_start.strip()
        if "T" in s or (len(s) >= 10 and s.count("-") == 2):
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                dt = None
            if isinstance(day_start_or_timestamp, str):
                day_start = day_start_or_timestamp
        else:
            # It's day_start like "08:00"
            day_start = s
            if isinstance(day_start_or_timestamp, datetime):
                dt = day_start_or_timestamp
            elif isinstance(day_start_or_timestamp, str):
                try:
                    dt = datetime.fromisoformat(day_start_or_timestamp.replace("Z", "+00:00"))
                except ValueError:
                    dt = None
    elif timestamp_or_day_start is None:
        if isinstance(day_start_or_timestamp, str):
            day_start = day_start_or_timestamp

    if dt is None:
        dt = datetime.now(timezone.utc)

    # Convert to local time or naive for calculation if timezone-aware
    target_time = dt.time()
    start_h, start_m = parse_day_start(day_start)
    threshold = time(start_h, start_m, 0)

    # Boundary check: If the time of day is strictly BEFORE the production day start,
    # the event belongs to the PREVIOUS calendar day's production cycle.
    if target_time < threshold:
        prod_dt = dt - timedelta(days=1)
    else:
        prod_dt = dt

    return prod_dt.strftime("%Y-%m-%d")


def get_production_day_range(
    production_date_str: str,
    day_start: str = "08:00",
) -> Tuple[datetime, datetime]:
    """
    Return the exact (start_datetime, end_datetime) range for a production date.
    Start is inclusive; end is inclusive up to the microsecond before next day's start.
    
    Example with "2026-09-07" and "08:00":
    Start: 2026-09-07 08:00:00
    End:   2026-09-08 07:59:59.999999
    """
    cal_date = datetime.strptime(production_date_str, "%Y-%m-%d")
    start_h, start_m = parse_day_start(day_start)
    
    start_dt = cal_date.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    next_day = cal_date + timedelta(days=1)
    end_dt = next_day.replace(hour=start_h, minute=start_m, second=0, microsecond=0) - timedelta(microseconds=1)
    
    return start_dt, end_dt


def is_same_production_day(
    dt1: datetime,
    dt2: datetime,
    day_start: str = "08:00",
) -> bool:
    """Check whether two datetimes belong to the same industrial production day."""
    return get_production_date(dt1, day_start) == get_production_date(dt2, day_start)


def get_hourly_bucket_label(
    dt: Optional[datetime] = None,
) -> Tuple[str, str]:
    """Return (hour_start_str, hour_end_str) for the hour containing dt, e.g. ('08:00', '09:00')."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    h = dt.hour
    h_start = f"{h:02d}:00"
    h_end = f"{(h + 1) % 24:02d}:00"
    return h_start, h_end


# Clean aliases
get_production_day_window = get_production_day_range
parse_time_string = parse_day_start
