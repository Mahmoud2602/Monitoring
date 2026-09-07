"""
Industrial Real-Time Production Monitor - Main Entry Point
Phase 3: Real-time acquisition, KPI Engine, SQLite Historical Layer,
Downtime Event Tracking, Alarm Management, and Analytics Reports.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from typing import Any, Optional

from core.data_manager import DataManager
from database.query_service import DatePreset
from kpi.models import KPISnapshot
from plc.plc_data import NormalizedPLCData
from utils.logger import setup_logger, get_logger


def render_phase3_dashboard(
    data: NormalizedPLCData,
    kpi: Optional[KPISnapshot],
    manager: Optional[DataManager] = None,
) -> None:
    """Render a clean, formatted real-time terminal view of production telemetry, KPIs, and downtime."""
    status_symbol = "🟢 ONLINE" if data.connected else "🔴 OFFLINE"

    line_name = kpi.assembly_line_name if kpi else "Assembly Line"
    line_status_str = "🟢 RUNNING"
    if kpi and kpi.line_status.value == "STOPPED":
        stopped_details = []
        for s in kpi.stopped_stations:
            dur_str = ""
            if manager:
                active_dur = manager.downtime_manager.get_active_downtime_duration(s.station_id)
                if active_dur is not None:
                    dur_str = f" [{active_dur:0.1f}s]"
            stopped_details.append(f"{s.display_name} ({s.plc_address}){dur_str}")
        line_status_str = f"🔴 STOPPED (Fault: {', '.join(stopped_details)})"

    # Conveyor 1 & 2 Station renderers with user-configured display names
    c1_strings = []
    c2_strings = []

    if kpi:
        for sid in range(1, 6):
            st = kpi.stations.get(f"station_{sid}")
            name = st.display_name if st else f"S{sid}"
            addr = st.plc_address if st else f"M{550 + sid - 1}"
            dur_txt = ""
            if st and not st.status and manager:
                dur = manager.downtime_manager.get_active_downtime_duration(sid)
                if dur is not None:
                    dur_txt = f" ({dur:.0f}s)"
            state = "[ RUN ]" if (st and st.status) else f"[STOP!{dur_txt}]"
            c1_strings.append(f"{name[:14]:<14} {addr}: {state}")

        for sid in range(6, 11):
            st = kpi.stations.get(f"station_{sid}")
            name = st.display_name if st else f"S{sid}"
            addr = st.plc_address if st else f"M{555 + sid - 6}"
            dur_txt = ""
            if st and not st.status and manager:
                dur = manager.downtime_manager.get_active_downtime_duration(sid)
                if dur is not None:
                    dur_txt = f" ({dur:.0f}s)"
            state = "[ RUN ]" if (st and st.status) else f"[STOP!{dur_txt}]"
            c2_strings.append(f"{name[:14]:<14} {addr}: {state}")
    else:
        for i in range(1, 6):
            c1_strings.append(f"S{i} M{549+i}: {'[ RUN ]' if data.stations.get(f'conv1_station{i}', False) else '[STOP!]'}")
            c2_strings.append(f"S{i+5} M{554+i}: {'[ RUN ]' if data.stations.get(f'conv2_station{i}', False) else '[STOP!]'}")

    print("\n" + "=" * 80)
    print(f"  {line_name.upper():<35} | Link: {status_symbol:<10} | Scan: {data.scan_time_ms:5.1f}ms")
    print(f"  Line Operating Status: {line_status_str}")
    print(f"  Timestamp (UTC): {data.timestamp}")
    print("-" * 80)
    print(f"  Line Speed:          {data.speed:5.1f} m/min  (Setpoint: {data.speed_setpoint:5.1f} m/min)")
    print(f"  Production Counter:  {data.production_counter:5d} pcs    (Daily Target: {data.daily_target:5d} pcs)")

    if kpi:
        curr_hour = kpi.current_hour
        print("-" * 80)
        print("  PRODUCTION DATA & KPI ENGINE:")
        print(f"  Target Rate:         {kpi.target_production_rate:5.1f} pcs/hr | Tact Time: {kpi.tact_time_seconds:5.1f} sec/pc")
        print(f"  Active Hour Bucket:  [{curr_hour.hour_start} - {curr_hour.hour_end}]")
        print(f"  Hourly Target:       {curr_hour.hourly_target:5.0f} pcs    | Actual: {curr_hour.actual_production:5d} pcs | Hourly Achieve: {curr_hour.hourly_achievement_percent:5.1f}%")
        print(f"  Cumulative Target:   {curr_hour.cumulative_target:5.0f} pcs    | Actual: {curr_hour.cumulative_actual:5d} pcs | Cumul. Achieve: {curr_hour.cumulative_achievement_percent:5.1f}%")
        if kpi.completed_hours:
            print(f"  Completed Hours:     {len(kpi.completed_hours)} hour(s) recorded in shift")

    if manager:
        active_alarms = manager.alarm_manager.get_active_alarms()
        active_stops = manager.downtime_manager.get_active_events()
        if active_stops or active_alarms:
            print("-" * 80)
            print("  ACTIVE EVENTS & ALARMS (PHASE 3):")
            for st in active_stops:
                dur = manager.downtime_manager.get_active_downtime_duration(st.station_id) or 0.0
                print(f"    • ⚠️ Station {st.station_id} ({st.station_name}): STOPPED since {st.start_time[11:19]} ({dur:.1f}s)")
            for al in active_alarms:
                print(f"    • 🚨 Alarm [{al.severity}] {al.alarm_code}: {al.alarm_message} (Raised: {al.timestamp[11:19]})")

    print("-" * 80)
    print("  CONVEYOR 1 (Stations 1-5):")
    for s_line in c1_strings:
        print(f"    • {s_line}")
    print("  CONVEYOR 2 (Stations 6-10):")
    for s_line in c2_strings:
        print(f"    • {s_line}")

    if data.error_message:
        print(f"  ALERTS: {data.error_message}")
    print("=" * 80)


def print_historical_report(manager: DataManager, preset_str: str) -> None:
    """Format and print an analytics report for the specified date preset."""
    query_svc = manager.get_query_service()
    preset_map = {
        "today": DatePreset.TODAY,
        "yesterday": DatePreset.YESTERDAY,
        "week": DatePreset.LAST_7_DAYS,
        "month": DatePreset.LAST_30_DAYS,
        "3months": DatePreset.LAST_3_MONTHS,
    }
    preset = preset_map.get(preset_str.lower(), DatePreset.TODAY)
    s_date, e_date = query_svc.resolve_date_range(preset)

    print("\n" + "=" * 80)
    print(f"  HISTORICAL PRODUCTION & DOWNTIME REPORT [{preset.value}]")
    print(f"  Range: {s_date} -> {e_date}")
    print("=" * 80)

    # 1. Daily summaries / Production by day
    daily_prod = query_svc.get_production_by_day(preset)
    print("\n  [DAILY PRODUCTION SUMMARY]")
    if daily_prod:
        print(f"  {'Date':<12} | {'Actual':<8} | {'Target':<8} | {'Achieve %':<10} | {'Hours':<6} | {'Avg Speed':<10}")
        print("  " + "-" * 70)
        for dp in daily_prod:
            print(
                f"  {dp['production_date']:<12} | {dp['actual_production']:<8d} | {dp['target_production']:<8.0f} | "
                f"{dp['achievement_percent']:<9.1f}% | {dp['hours_recorded']:<6d} | {dp['average_speed']:<8.1f} m/min"
            )
    else:
        print("  No production records found for this period.")

    # 2. Downtime statistics
    dt_stats = query_svc.get_downtime_statistics(preset)
    print("\n  [DOWNTIME OVERVIEW]")
    print(f"  Total Stops:         {dt_stats['total_stops']} events")
    print(f"  Total Downtime:      {dt_stats['total_downtime_seconds']:.1f} seconds")
    print(f"  Average Duration:    {dt_stats['average_stop_seconds']:.1f} seconds")
    print(f"  Longest Stoppage:    {dt_stats['longest_stop_seconds']:.1f} seconds")

    # 3. Downtime by station
    dt_by_st = query_svc.get_downtime_by_station(preset)
    print("\n  [DOWNTIME BY STATION]")
    if dt_by_st:
        print(f"  {'Station':<22} | {'Stops':<6} | {'Total Time':<12} | {'Avg Duration':<12} | {'Longest':<10}")
        print("  " + "-" * 70)
        for ds in dt_by_st:
            name_label = f"S{ds['station_id']}: {ds['station_name'][:17]}"
            print(
                f"  {name_label:<22} | {ds['stop_count']:<6d} | {ds['total_downtime_seconds']:>8.1f}s    | "
                f"{ds['average_stop_duration']:>8.1f}s    | {ds['longest_stop_duration']:>6.1f}s"
            )
    else:
        print("  No stoppage events recorded for this period.")

    # 4. Alarms history
    alarms = query_svc.get_alarm_history(preset)
    print(f"\n  [ALARM HISTORY] ({len(alarms)} events recorded)")
    for al in alarms[:10]:
        st_txt = f"Station {al.station_id}" if al.station_id else "Line"
        dur_txt = f"{al.duration_seconds:.1f}s" if al.duration_seconds is not None else "Active"
        print(f"  • [{al.timestamp[:19]}] [{al.severity}] {al.alarm_code} ({st_txt}): {al.alarm_message} (Dur: {dur_txt})")
    if len(alarms) > 10:
        print(f"  ... and {len(alarms) - 10} more alarm record(s)")

    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Industrial Real-Time Production Monitor - Phase 4")
    parser.add_argument("--config", default="config/settings.json", help="Path to settings.json")
    parser.add_argument("--mapping", default="config/plc_mapping.json", help="Path to plc_mapping.json")
    parser.add_argument("--db", default=None, help="Path to SQLite database file")
    parser.add_argument("--gui", action="store_true", help="Launch the PySide6 native desktop dashboard")
    parser.add_argument("--cli", action="store_true", help="Run in terminal console mode")
    parser.add_argument("--single-shot", action="store_true", help="Perform a single scan and exit")
    parser.add_argument("--json", action="store_true", help="Output normalized data as raw JSON")
    parser.add_argument("--report", choices=["today", "yesterday", "week", "month", "3months"], help="Print historical report")
    args = parser.parse_args()

    # Determine execution mode: CLI flags take precedence, otherwise launch GUI
    is_cli_mode = args.cli or args.single_shot or args.json or (args.report is not None)

    if not is_cli_mode or args.gui:
        # Launch PySide6 GUI application
        try:
            from gui_main import run_gui
            sys.exit(run_gui(config_path=args.config, mapping_path=args.mapping, db_path=args.db))
        except Exception as exc:
            print(f"Warning: Failed to launch PySide6 GUI ({exc}). Falling back to CLI mode.")

    # Initialize logger for CLI mode
    logger = setup_logger("plc_monitor", level="INFO")
    logger.info("Initializing Industrial Production Monitor (Phase 4 CLI)...")

    try:
        manager = DataManager(
            settings_path=args.config,
            mapping_path=args.mapping,
            db_path=args.db,
        )
    except Exception as exc:
        logger.critical("Failed to initialize DataManager: %s", exc)
        sys.exit(1)

    # Historical report mode
    if args.report:
        print_historical_report(manager, args.report)
        manager.stop()
        return

    if args.single_shot:
        # Run one synchronous read cycle
        data = manager.client.read_cycle()
        kpi = manager.kpi_engine.process_data(data)
        if args.json:
            combined = {
                "plc_data": data.to_dict(include_metadata=True),
                "kpi_snapshot": kpi.to_dict(),
                "active_downtime": [d.to_dict() for d in manager.downtime_manager.get_active_events()],
                "active_alarms": [a.to_dict() for a in manager.alarm_manager.get_active_alarms()],
            }
            print(json.dumps(combined, indent=2))
        else:
            render_phase3_dashboard(data, kpi, manager)
        manager.stop()
        return

    # Real-time listener for streaming mode
    def on_telemetry(snapshot: NormalizedPLCData) -> None:
        kpi = manager.get_latest_kpi()
        if args.json:
            combined = {
                "plc_data": snapshot.to_dict(include_metadata=False),
                "kpi_snapshot": kpi.to_dict() if kpi else None,
                "active_downtime": [d.to_dict() for d in manager.downtime_manager.get_active_events()],
                "active_alarms": [a.to_dict() for a in manager.alarm_manager.get_active_alarms()],
            }
            print(json.dumps(combined, indent=None))
        else:
            render_phase3_dashboard(snapshot, kpi, manager)

    manager.register_data_listener(on_telemetry)

    # Graceful shutdown handler
    def handle_sigint(signum: Any, frame: Any) -> None:
        print("\nInterrupt signal received. Shutting down cleanly...")
        manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    # Start polling
    manager.start()

    print("Monitoring active. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        handle_sigint(None, None)


if __name__ == "__main__":
    main()

