# Industrial Real-Time Production Monitoring Application (Phase 1)

This repository contains **Phase 1** of the professional industrial real-time production monitoring application:
- **Modular Project Architecture**
- **Isolated PLC Communication Layer (`plc_client.py`)**
- **Decoupled M-Bit & D-Register Schema Mapping (`plc_mapping.json`)**
- **Normalized Data Model (`NormalizedPLCData`)**
- **Simulation Engine with Physics & Random Station Stoppages (`simulated_driver.py`)**
- **Unit Test Suite (`tests/`)**

---

## 1. Project Directory Structure

```text
.
├── main.py                     # Application entry point with CLI & real-time dashboard
├── requirements.txt            # Package manifest & protocol drivers
├── config/
│   ├── settings.json           # PLC IP, port, polling intervals, simulation toggle
│   └── plc_mapping.json        # Decoupled D450..D453 and M550..M559 mappings
├── plc/
│   ├── __init__.py
│   ├── base_driver.py          # Abstract protocol driver interface (BasePLCDriver)
│   ├── simulated_driver.py     # Realistic physics simulator & station jam generator
│   ├── plc_client.py           # Connection lifecycle, retry logic, & background polling
│   ├── plc_data.py             # Normalized data models (dataclass) & mapping parser
│   └── driver_template.py      # Template for plugging in Modbus TCP / MC Protocol / Snap7
├── core/
│   ├── __init__.py
│   └── data_manager.py         # Business coordinator & subscriber hub
├── utils/
│   ├── __init__.py
│   └── logger.py               # Structured industrial console & file logger
└── tests/
    ├── __init__.py
    ├── test_plc_mapping.py      # Register & bit mapping tests
    ├── test_simulated_driver.py # Simulator physics & counter tests
    ├── test_connection_state.py # Connection state machine & fault recovery tests
    └── test_station_mapping.py  # Conveyor 1 & 2 station mapping tests
```

---

## 2. Python Packages & Dependencies

### Core Application (Zero External Dependencies)
Phase 1 is built entirely using the **Python Standard Library** (`Python 3.8+`):
- `dataclasses`: Strongly typed data containers for normalized industrial snapshots.
- `typing`: Type annotations and contract enforcement across all modules.
- `json`: Parsing configuration and generating standard JSON telemetry payloads.
- `threading`: Background cyclic polling thread without blocking application UI or business logic.
- `logging`: Structured, timestamped industrial logging without using raw `print()`.
- `time` & `datetime`: High-resolution timers (`time.perf_counter`) for scan time benchmarking.
- `random`: Emulating industrial line speed jitter and station jam distributions.
- `abc`: Abstract base class (`BasePLCDriver`) enforcing the pluggable driver contract.
- `unittest`: Automated unit test execution.

### Optional Industrial Protocol Packages (When Connecting to Physical Hardware)
Depending on your PLC manufacturer, install the corresponding Ethernet protocol driver:
1. **Modbus TCP** (Schneider, WAGO, Delta, generic industrial gateways):
   `pip install pymodbus`
2. **Mitsubishi MELSEC** (Q-Series, L-Series, iQ-R, FX5U via MC Protocol / SLMP):
   `pip install pymcprotocol`
3. **Siemens SIMATIC** (S7-300, S7-400, S7-1200, S7-1500 via ISO-on-TCP):
   `pip install python-snap7`
4. **Rockwell / Allen-Bradley** (ControlLogix, CompactLogix via Ethernet/IP CIP):
   `pip install pycomm3`

---

## 3. How to Run the Project

### Running Continuous Real-Time Monitoring
```bash
python3 main.py
```
This launches the real-time console dashboard displaying:
- Connection status (`ONLINE` / `OFFLINE`) and scan cycle latency (ms)
- Line Speed (D450) vs Setpoint (D451)
- Production Counter (D452) vs Daily Target (D453)
- Conveyor 1 Stations (M550–M554: S1 to S5)
- Conveyor 2 Stations (M555–M559: S1 to S5)

### Running Single-Shot Scan (CLI)
```bash
python3 main.py --single-shot
```

### Emitting Raw JSON Telemetry
```bash
python3 main.py --single-shot --json
```
Output:
```json
{
  "timestamp": "2026-09-06T11:43:24.799082+00:00",
  "connected": true,
  "speed": 44.97,
  "speed_setpoint": 45.0,
  "production_counter": 1280,
  "daily_target": 1000,
  "stations": {
    "conv1_station1": true,
    "conv1_station2": true,
    "conv1_station3": true,
    "conv1_station4": true,
    "conv1_station5": true,
    "conv2_station1": true,
    "conv2_station2": true,
    "conv2_station3": true,
    "conv2_station4": true,
    "conv2_station5": true
  }
}
```

### Running the Unit Test Suite
```bash
python3 -m unittest discover -s tests
```

---

## 4. Configuration Guide

### How to Switch Between Simulation Mode and Real PLC Mode
Open `config/settings.json`:
- Set `"simulation_mode": true` for simulation mode.
- Set `"simulation_mode": false` to connect to physical hardware.

```json
{
  "simulation_mode": true
}
```

### Where to Change the PLC IP & Polling Cycle
In `config/settings.json`:
```json
{
  "plc": {
    "ip_address": "192.168.1.10",
    "port": 502,
    "timeout_seconds": 2.0,
    "retry_interval_seconds": 3.0,
    "max_retries": 5
  },
  "polling": {
    "cycle_time_ms": 500
  }
}
```
- **IP Address**: Edit `"ip_address"`.
- **Port**: Edit `"port"`.
- **Polling Interval**: Edit `"cycle_time_ms"` (e.g. `100`, `250`, `500`, or `1000`).

### Where to Change D-Register and M-Bit Mappings
Open `config/plc_mapping.json`:
```json
{
  "registers": {
    "speed": { "address": "D450", "type": "FLOAT", "scale": 1.0 },
    "speed_setpoint": { "address": "D451", "type": "FLOAT", "scale": 1.0 },
    "production_counter": { "address": "D452", "type": "INT", "scale": 1.0 },
    "daily_target": { "address": "D453", "type": "INT", "scale": 1.0 }
  },
  "stations": {
    "conv1_station1": { "address": "M550", "conveyor": "Conveyor 1", "station_index": 1 },
    "conv1_station2": { "address": "M551", "conveyor": "Conveyor 1", "station_index": 2 },
    "conv1_station3": { "address": "M552", "conveyor": "Conveyor 1", "station_index": 3 },
    "conv1_station4": { "address": "M553", "conveyor": "Conveyor 1", "station_index": 4 },
    "conv1_station5": { "address": "M554", "conveyor": "Conveyor 1", "station_index": 5 },
    "conv2_station1": { "address": "M555", "conveyor": "Conveyor 2", "station_index": 1 },
    "conv2_station2": { "address": "M556", "conveyor": "Conveyor 2", "station_index": 2 },
    "conv2_station3": { "address": "M557", "conveyor": "Conveyor 2", "station_index": 3 },
    "conv2_station4": { "address": "M558", "conveyor": "Conveyor 2", "station_index": 4 },
    "conv2_station5": { "address": "M559", "conveyor": "Conveyor 2", "station_index": 5 }
  }
}
```
If register addresses change in the PLC ladder logic (e.g., `D450` moves to `D1000`, or `M550` moves to `M100`), update the `"address"` values in this JSON file. The rest of the application will continue running without code modifications.
