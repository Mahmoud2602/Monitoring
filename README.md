# Industrial Real-Time Production Monitoring Application

A modular, production-hardened desktop and data layer application for industrial manufacturing lines. Features real-time PLC telemetry polling, reset-safe production counter tracking, centralized production-day logic, persistent SQLite historical auditing, automated downtime state machine detection, active alarm management, and an interactive PyQt/PySide graphical user interface.

---

## 1. System Architecture Overview

```text
.
├── config/                     # Decoupled industrial configuration
│   ├── settings.json           # PLC IP, port, polling cycles, shift hours, simulation toggle
│   └── plc_mapping.json        # D450..D453 and M550..M559 register mappings
├── plc/                        # Hardware abstraction and communications
│   ├── base_driver.py          # Abstract protocol interface (BasePLCDriver)
│   ├── ethernet_driver.py      # Real hardware Ethernet socket & protocol implementation
│   ├── simulated_driver.py     # Realistic physics simulator with random station stoppage
│   ├── plc_client.py           # Background cyclic polling, retry, and connection state machine
│   └── plc_data.py             # Normalized industrial telemetry dataclass (NormalizedPLCData)
├── core/                       # Core business orchestration & timing
│   ├── production_day.py       # Single source of truth for 08:00 production day boundaries
│   └── data_manager.py         # Central coordinator wiring PLC, KPI, Database & Alarms
├── kpi/                        # High-precision industrial computation engine
│   ├── kpi_engine.py           # Reset-safe counter tracker, hourly buckets, line status
│   ├── tact_time.py            # Calibrated engineering speed & tact time derivation
│   └── models.py               # Strongly-typed KPI models and snapshots
├── database/                   # SQLite persistence & audit analytics
│   ├── database_manager.py     # Connection lifecycle, schema DDL, indexing & verification
│   ├── models.py               # Normalized database entity records
│   ├── repositories.py         # Parameterized data access objects (Production, Downtime, Alarms)
│   ├── downtime_manager.py     # RUNNING -> STOPPED state machine tracking discrete stops
│   ├── alarm_manager.py        # Active alarm lifecycles and historical fault logging
│   └── query_service.py        # 12-metric analytics query engine & trend aggregation
├── ui/                         # Modern industrial desktop GUI (PySide6 / PyQt6)
│   ├── main_window.py          # Dual-page container (Real-time Dashboard & Historical Analysis)
│   ├── worker.py               # Background telemetry worker thread (TelemetryBridge)
│   ├── theme.py                # Industrial high-contrast dark palette
│   ├── dashboard/              # Real-time monitoring views
│   │   ├── dashboard_page.py   # Primary dashboard layout
│   │   ├── kpi_cards.py        # Real-time KPI summary widgets
│   │   ├── production_line.py  # 10-Station dual conveyor physical layout visualizer
│   │   ├── charts.py           # Real-time hourly production & speed chart
│   │   └── active_alarms.py    # Active alarm table & status banner
│   └── historical/             # Historical audit & bottleneck analytics
│       ├── historical_page.py  # Asynchronous historical analysis page (QThread worker)
│       ├── filter_bar.py       # Presets (Today, Yesterday, 7D, 30D, 3M, Custom) & Station filter
│       ├── kpi_summary_bar.py  # 12 Executive KPI metric cards
│       ├── charts.py           # 7 Interactive PyQtGraph visualization panels
│       └── tables.py           # Filterable downtime event logs & alarm audit trail
├── gui_main.py                 # Desktop GUI entry point
├── main.py                     # CLI & Console monitoring entry point
└── tests/                      # Comprehensive test suite (112 unit & hardening tests)
```

---

## 2. Core Subsystems & Engineering Hardening

### A. Production Counter Reset Safety & Rollovers
Industrial PLCs often experience counter resets at shift handovers, power cycles, or integer overflows. The `KPIEngine` guarantees:
- **Monotonic Hourly Accumulation**: Handles normal positive increments.
- **16-Bit Unsigned Rollover**: Automatically detects rollovers from `65535` back to zero (e.g. `65530 -> 10` calculates a delta of `16`).
- **15-Bit Signed Rollover**: Handles `32767` rollovers seamlessly.
- **4-Digit BCD/Decimal Rollover**: Handles `9999` rollovers seamlessly.
- **Manual Counter Resets**: If the counter drops to `0` or an arbitrary small number after reset, it treats the change safely without causing negative production or gigantic spikes.
- **Negative Counter Protection**: Invalid negative register values yield zero delta.

### B. Centralized Production Day Single Source of Truth
The manufacturing day is defined as **08:00 AM to 07:59:59 AM next calendar day**:
- Implemented strictly in `core/production_day.py`.
- Timestamps before 08:00:00 (e.g. 07:59:59 or 02:30:00) belong to the previous calendar day.
- Timestamps at or after 08:00:00 belong to the current calendar day.
- Shared and enforced across `KPIEngine`, `DatabaseManager`, `DowntimeManager`, and `HistoricalQueryService`.

### C. Precision KPI Engine Formulas
- **Hourly Target**: Configurable target pieces per hour (e.g., 100 pcs/hr).
- **Hourly Achievement %**: `(Actual Production / Expected Hourly Target) * 100`.
- **Cumulative Achievement %**: `(Cumulative Actual / Cumulative Target) * 100`.
- **Tact Time (Instantaneous)**: `Product Pitch (m) / (Conveyor Speed (m/min) / 60)`. When the conveyor is stopped (`0.0 m/min`), tact time safely evaluates to `0.0s` (displayed as `--`).
- **Line Operating Status**: Dynamically switches between `RUNNING`, `STOPPED` (with stopped station identification), and `DISCONNECTED`.

### D. SQLite Persistence & Relational Schema
All metrics and discrete events are stored in `production_monitor.db` with indexed foreign keys:
1. `production_data`: Hourly production buckets with unique constraint `UNIQUE(production_date, hour_start)`.
2. `downtime_events`: Discrete stop events per station with start time, end time, duration, and associated alarms.
3. `alarm_events`: Historical alarm events with severity, duration, and active resolution tracking.
4. `daily_summaries`: Daily rollups of production totals, average speeds, and downtime totals.

### E. Downtime State Machine & Comm Loss Protection
The `DowntimeManager` detects transitions across all 10 workstations:
- `RUNNING -> STOPPED`: Opens a new downtime event in SQLite.
- Steady `STOPPED`: Repeated polls do not duplicate events.
- `STOPPED -> RUNNING`: Concludes the active downtime event with exact duration in seconds.
- **Communication Loss Protection**: If the PLC communication fails (`is_connected=False`), it is logged as a communication error and does not generate false mechanical downtime events for individual stations.
- **Application Restart Recovery**: Open downtime events are preserved and resumed on restart.

### F. Historical Analysis & 12 Executive Summary Metrics
The `HistoricalQueryService` provides analytics across multiple date ranges:
- **Date Presets**: `Today`, `Yesterday`, `Last 7 Days`, `Last 30 Days`, `Last 3 Months`, and `Custom Date Range`.
- **12 Executive Metrics**:
  1. Total Production (pcs)
  2. Total Target (pcs)
  3. Achievement %
  4. Total Downtime (hh:mm:ss)
  5. Running Time (Net Operating Time)
  6. Total Stops (count)
  7. Average Stop Duration
  8. Longest Stop Duration
  9. Average Line Speed (m/min)
  10. Average Tact Time (s)
  11. Best Performing Hour
  12. Worst Performing Hour
- **10-Station Full Breakdown**: Visualizes downtime duration and stop frequency across all 10 stations and highlights line bottlenecks.
- **Asynchronous GUI Query Worker**: Heavy database aggregations execute in `HistoricalQueryWorker` (`QThread`), keeping the PyQt/PySide GUI responsive at all times.

---

## 3. How to Run

### Requirements
- Python 3.8+
- PySide6 (or PyQt6)
- pyqtgraph (for interactive charts)

### 1. Launch the Desktop GUI
```bash
python3 gui_main.py
```
This opens the dual-page industrial dashboard:
- **Dashboard View**: Real-time line status, speed gauges, cumulative KPIs, 10-station interactive diagram, hourly production chart, and active alarms.
- **Historical Analysis View**: Audit filters, executive summary bar, 7 interactive charts (Production Trend, Achievement Trend vs 100%, Speed vs Setpoint, Downtime Timeline, Station Bottleneck Chart, 10-Station Breakdown), and data audit tables.

### 2. Launch the Console / CLI Real-Time Monitor
```bash
python3 main.py
```
Or run a single scan:
```bash
python3 main.py --single-shot --json
```

### 3. Run the Automated Test Suite
Run the full test suite (112 tests):
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

Run only the Phase 5 hardening tests:
```bash
python3 -m unittest tests/test_hardening_pass.py
```

---

## 4. Configuration Guide

### Switching Between Simulation and Real PLC Hardware
In `config/settings.json`:
- Set `"simulation_mode": true` for simulation with physics and random station jams.
- Set `"simulation_mode": false` to connect to physical PLC hardware via Ethernet.

```json
{
  "simulation_mode": true,
  "plc": {
    "ip_address": "192.168.1.10",
    "port": 502,
    "timeout_seconds": 2.0,
    "retry_interval_seconds": 3.0,
    "max_retries": 5
  },
  "production": {
    "day_start_time": "08:00",
    "hourly_target": 100,
    "daily_target": 1000,
    "speed_setpoint_mpm": 45.0
  }
}
```

### Station Mapping
Station names, PLC addresses (`M550`–`M559`), and conveyor assignments are configured in `config/plc_mapping.json`.
