import React, { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  Wifi, 
  WifiOff, 
  AlertTriangle, 
  Play, 
  Pause, 
  RefreshCw, 
  Sliders, 
  FileCode, 
  CheckCircle2, 
  Radio, 
  Server,
  Zap,
  ChevronRight,
  Terminal,
  Clock,
  Settings,
  Gauge,
  BarChart3,
  TrendingUp,
  RotateCcw,
  Layers,
  Edit3
} from 'lucide-react';

interface StationItem {
  id: number;
  key: string;
  address: string;
  name: string;
  conveyor: string;
  active: boolean;
}

interface HourlyRecord {
  date: string;
  hour_start: string;
  hour_end: string;
  hourly_target: number;
  actual_production: number;
  hourly_achievement_percent: number;
  cumulative_target: number;
  cumulative_actual: number;
  cumulative_achievement_percent: number;
  tact_time: number;
  average_speed?: number;
}

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'DEBUG' | 'WARN' | 'DATA' | 'ERROR';
  message: string;
}

export default function App() {
  // 1. Line & Station Configurations (Phase 2 Configurable Requirements)
  const [assemblyLineName, setAssemblyLineName] = useState<string>("Assembly Line");
  const [productionDayStart, setProductionDayStart] = useState<string>("08:00");
  const [targetProductionRate, setTargetProductionRate] = useState<number>(100.0); // pcs/hour
  const [productPitchMeters, setProductPitchMeters] = useState<number>(0.75); // meters
  const [speedScaleFactor] = useState<number>(1.0);
  const [speedUnit] = useState<string>("m/min");

  // Station display names (Configurable mapping: Physical M550-M559 remain stable)
  const [stationNames, setStationNames] = useState<Record<number, string>>({
    1: "Assembly 1",
    2: "Screw Installation",
    3: "Inspection",
    4: "Riveting",
    5: "Transfer 1",
    6: "Component Insertion",
    7: "Optical Inspection",
    8: "Laser Marking",
    9: "Cleaning",
    10: "Unloading",
  });

  // Physical discrete bits (M550-M559)
  const [stations, setStations] = useState<Record<string, boolean>>({
    conv1_station1: true, // Station 1 -> M550
    conv1_station2: true, // Station 2 -> M551
    conv1_station3: false, // Station 3 -> M552 (sample stoppage)
    conv1_station4: true, // Station 4 -> M553
    conv1_station5: true, // Station 5 -> M554
    conv2_station1: true, // Station 6 -> M555
    conv2_station2: true, // Station 7 -> M556
    conv2_station3: true, // Station 8 -> M557
    conv2_station4: true, // Station 9 -> M558
    conv2_station5: true, // Station 10 -> M559
  });

  // 2. PLC Registers (D450 - D453)
  const [speedSetpoint] = useState<number>(45.0); // D451
  const [lineSpeed, setLineSpeed] = useState<number>(42.8); // D450
  const [productionCounter, setProductionCounter] = useState<number>(1284); // D452
  const [dailyTarget] = useState<number>(2000); // D453

  // 3. KPI Engine State (Phase 2)
  const [currentHourActual, setCurrentHourActual] = useState<number>(34);
  const [currentHourStart, setCurrentHourStart] = useState<string>("08:00");
  const [currentHourEnd, setCurrentHourEnd] = useState<string>("09:00");
  const [completedHours, setCompletedHours] = useState<HourlyRecord[]>([
    {
      date: "2026-09-06",
      hour_start: "06:00",
      hour_end: "07:00",
      hourly_target: 100,
      actual_production: 98,
      hourly_achievement_percent: 98.0,
      cumulative_target: 100,
      cumulative_actual: 98,
      cumulative_achievement_percent: 98.0,
      tact_time: 1.05,
      average_speed: 43.2,
    },
    {
      date: "2026-09-06",
      hour_start: "07:00",
      hour_end: "08:00",
      hourly_target: 100,
      actual_production: 95,
      hourly_achievement_percent: 95.0,
      cumulative_target: 200,
      cumulative_actual: 193,
      cumulative_achievement_percent: 96.5,
      tact_time: 1.04,
      average_speed: 42.9,
    },
  ]);

  // Modals & UI Controls
  const [connected, setConnected] = useState<boolean>(true);
  const [simulationMode] = useState<boolean>(true);
  const [pollingRateMs, setPollingRateMs] = useState<number>(500);
  const [scanLatency, setScanLatency] = useState<number>(12.4);
  const [autoRandomStops, setAutoRandomStops] = useState<boolean>(false);
  const [showJsonModal, setShowJsonModal] = useState<boolean>(false);
  const [showConfigModal, setShowConfigModal] = useState<boolean>(false);
  const [configTab, setConfigTab] = useState<'line' | 'stations'>('line');

  // Logs
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: '1', timestamp: '08:00:00', level: 'INFO', message: 'KPI Engine initialized. Assembly Line: Assembly Line' },
    { id: '2', timestamp: '08:00:01', level: 'INFO', message: 'Loaded 10 physical station mappings (M550-M559)' },
    { id: '3', timestamp: '08:00:02', level: 'INFO', message: 'Target production rate set to 100.0 pcs/hr' },
    { id: '4', timestamp: '08:00:03', level: 'DATA', message: 'Speed: 42.8 m/min | Tact Time: 1.05s | Counter: 1284' },
    { id: '5', timestamp: '08:00:15', level: 'WARN', message: 'Line STOPPED: Station 3 (Inspection, M552) halted' },
  ]);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const stopTimersRef = useRef<Record<string, number>>({ conv1_station3: 15 });

  const addLog = (level: LogEntry['level'], message: string) => {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    const newEntry: LogEntry = {
      id: Math.random().toString(36).substring(2, 9),
      timestamp: timeStr,
      level,
      message,
    };
    setLogs((prev) => [...prev.slice(-40), newEntry]);
  };

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // ---------------------------------------------------------------------------
  // KPI Calculations (Formulas matching Python KPIEngine)
  // ---------------------------------------------------------------------------
  // Tact time (seconds) = Pitch (m) / Speed (m/s) = Pitch * 60 / Speed (m/min)
  const tactTimeSeconds = lineSpeed > 0 ? Number(((productPitchMeters * 60.0) / lineSpeed).toFixed(2)) : 0;
  
  // Hourly Target & Achievement
  const hourlyTarget = targetProductionRate;
  const hourlyAchievementPercent = hourlyTarget > 0 ? Number(((currentHourActual / hourlyTarget) * 100.0).toFixed(1)) : 0;

  // Cumulative Target & Achievement (across completed hours + current progress)
  const completedTargetSum = completedHours.reduce((acc, h) => acc + h.hourly_target, 0);
  const completedActualSum = completedHours.reduce((acc, h) => acc + h.actual_production, 0);

  const cumulativeTarget = completedTargetSum + hourlyTarget;
  const cumulativeActual = completedActualSum + currentHourActual;
  const cumulativeAchievementPercent = cumulativeTarget > 0 ? Number(((cumulativeActual / cumulativeTarget) * 100.0).toFixed(1)) : 0;

  // Line Operating Status & Stopped Stations
  const stoppedStationList: Array<{ id: number; name: string; address: string }> = [];
  for (let i = 1; i <= 10; i++) {
    const key = i <= 5 ? `conv1_station${i}` : `conv2_station${i - 5}`;
    const addr = i <= 5 ? `M${550 + i - 1}` : `M${555 + i - 6}`;
    if (!stations[key]) {
      stoppedStationList.push({
        id: i,
        name: stationNames[i] || `Station ${i}`,
        address: addr,
      });
    }
  }
  const isLineRunning = stoppedStationList.length === 0;

  // ---------------------------------------------------------------------------
  // Main Polling & Telemetry Simulation Loop
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!connected) return;

    const interval = setInterval(() => {
      // Speed adjustments based on line running status
      setLineSpeed((prev) => {
        let target: number;
        if (!isLineRunning) {
          target = 10.0 + (Math.random() * 2.0 - 1.0);
        } else {
          target = speedSetpoint + (Math.random() * 2.0 - 1.0);
        }
        const next = prev + 0.25 * (target - prev);
        return Math.round(next * 10) / 10;
      });

      // Increment production counters if speed is sufficient
      if (lineSpeed > 15 && isLineRunning) {
        if (Math.random() < 0.4) {
          setProductionCounter((c) => c + 1);
          setCurrentHourActual((a) => a + 1);
        }
      }

      setScanLatency(Math.round((10 + Math.random() * 4) * 10) / 10);

      // Random station stoppage simulation if enabled
      if (autoRandomStops && Math.random() < 0.05) {
        const keys = Object.keys(stations);
        const randomKey = keys[Math.floor(Math.random() * keys.length)];
        if (stations[randomKey]) {
          setStations((prev) => ({ ...prev, [randomKey]: false }));
          stopTimersRef.current[randomKey] = 6;
          addLog('WARN', `Fault detected at station: ${randomKey}`);
        }
      }

      // Auto-clear timers
      Object.keys(stopTimersRef.current).forEach((key) => {
        if (stopTimersRef.current[key] > 0) {
          stopTimersRef.current[key] -= 1;
          if (stopTimersRef.current[key] === 0) {
            setStations((prev) => ({ ...prev, [key]: true }));
            addLog('INFO', `Station ${key} cleared stoppage automatically`);
          }
        }
      });
    }, pollingRateMs);

    return () => clearInterval(interval);
  }, [connected, isLineRunning, lineSpeed, speedSetpoint, pollingRateMs, autoRandomStops, stations]);

  // ---------------------------------------------------------------------------
  // Handlers for Testing Phase 2 Edge Cases
  // ---------------------------------------------------------------------------
  const handleSimulateCounterReset = () => {
    // Demonstrates safe counter rollover (e.g. 999 -> 10)
    addLog('WARN', `Testing Safe Rollover: Previous counter = 999, New counter = 10`);
    setProductionCounter(10);
    // Delta handled as +10 rather than -989!
    setCurrentHourActual((prev) => prev + 10);
    addLog('DATA', `Safe rollover handled: Added 10 pcs to current hour actual (never negative).`);
  };

  const handleAdvanceHour = () => {
    // Finalize current hour into completed hours history
    const newRecord: HourlyRecord = {
      date: new Date().toISOString().split('T')[0],
      hour_start: currentHourStart,
      hour_end: currentHourEnd,
      hourly_target: hourlyTarget,
      actual_production: currentHourActual,
      hourly_achievement_percent: hourlyAchievementPercent,
      cumulative_target: cumulativeTarget,
      cumulative_actual: cumulativeActual,
      cumulative_achievement_percent: cumulativeAchievementPercent,
      tact_time: tactTimeSeconds,
      average_speed: lineSpeed,
    };
    setCompletedHours((prev) => [...prev, newRecord]);
    addLog('INFO', `Hour finalized [${currentHourStart} - ${currentHourEnd}]: Target=${hourlyTarget}, Actual=${currentHourActual} (${hourlyAchievementPercent}%)`);

    // Advance hour label (e.g. 09:00 - 10:00)
    const startHourInt = parseInt(currentHourStart.split(':')[0], 10);
    const nextStartHour = (startHourInt + 1) % 24;
    const nextEndHour = (nextStartHour + 1) % 24;
    const nextStartStr = `${String(nextStartHour).padStart(2, '0')}:00`;
    const nextEndStr = `${String(nextEndHour).padStart(2, '0')}:00`;

    setCurrentHourStart(nextStartStr);
    setCurrentHourEnd(nextEndStr);
    setCurrentHourActual(0);
  };

  const toggleStation = (key: string, stationId: number) => {
    const willBeActive = !stations[key];
    setStations((prev) => ({ ...prev, [key]: willBeActive }));
    const name = stationNames[stationId] || `Station ${stationId}`;
    const addr = stationId <= 5 ? `M${550 + stationId - 1}` : `M${555 + stationId - 6}`;
    if (!willBeActive) {
      stopTimersRef.current[key] = 12;
      addLog('WARN', `Operator manual stoppage: Station ${stationId} (${name}, ${addr})`);
    } else {
      stopTimersRef.current[key] = 0;
      addLog('INFO', `Operator manual reset: Station ${stationId} (${name}, ${addr})`);
    }
  };

  const conveyor1Stations: StationItem[] = [1, 2, 3, 4, 5].map((id) => ({
    id,
    key: `conv1_station${id}`,
    address: `M${550 + id - 1}`,
    name: stationNames[id] || `Station ${id}`,
    conveyor: 'Conveyor 1',
    active: stations[`conv1_station${id}`],
  }));

  const conveyor2Stations: StationItem[] = [6, 7, 8, 9, 10].map((id) => ({
    id,
    key: `conv2_station${id - 5}`,
    address: `M${555 + id - 6}`,
    name: stationNames[id] || `Station ${id}`,
    conveyor: 'Conveyor 2',
    active: stations[`conv2_station${id - 5}`],
  }));

  // JSON representation matching Section 8 & Section 12 requirements
  const phase2JsonSnapshot = {
    timestamp: new Date().toISOString(),
    assembly_line_name: assemblyLineName,
    line_status: isLineRunning ? 'RUNNING' : 'STOPPED',
    stopped_stations: stoppedStationList.map((s) => ({
      station_id: s.id,
      display_name: s.name,
      plc_address: s.address,
    })),
    stations: {
      ...conveyor1Stations.reduce((acc, s) => ({
        ...acc,
        [`station_${s.id}`]: { station_id: s.id, display_name: s.name, plc_address: s.address, status: s.active },
      }), {}),
      ...conveyor2Stations.reduce((acc, s) => ({
        ...acc,
        [`station_${s.id}`]: { station_id: s.id, display_name: s.name, plc_address: s.address, status: s.active },
      }), {}),
    },
    current_hour: {
      date: new Date().toISOString().split('T')[0],
      hour_start: currentHourStart,
      hour_end: currentHourEnd,
      hourly_target: hourlyTarget,
      actual_production: currentHourActual,
      hourly_achievement_percent: hourlyAchievementPercent,
      cumulative_target: cumulativeTarget,
      cumulative_actual: cumulativeActual,
      cumulative_achievement_percent: cumulativeAchievementPercent,
      tact_time: tactTimeSeconds,
      average_speed: lineSpeed,
    },
    completed_hours: completedHours,
    target_production_rate: targetProductionRate,
    tact_time_seconds: tactTimeSeconds,
    production_counter_raw: productionCounter,
    daily_target: dailyTarget,
    engineering_speed: lineSpeed,
    speed_unit: speedUnit,
  };

  return (
    <div id="app-root" className="w-screen h-screen bg-[#0F0F11] text-[#E0E0E0] font-sans flex flex-col overflow-hidden select-none">
      {/* Top SCADA Header */}
      <header id="scada-header" className="h-16 border-b border-[#333] flex items-center justify-between px-4 sm:px-6 bg-[#161618] shrink-0">
        <div className="flex items-center gap-3 sm:gap-4">
          <div className="w-8 h-8 bg-[#F27D26] flex items-center justify-center font-bold text-black text-xs tracking-tighter">
            KPI
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold tracking-tight uppercase">
                {assemblyLineName}
              </h1>
              <span className="text-[10px] bg-[#222] text-[#F27D26] px-1.5 py-0.5 rounded font-mono border border-[#333]">
                Phase 2
              </span>
            </div>
            <div className="text-[#888] text-xs hidden sm:flex items-center gap-2">
              <span>Shift Start: {productionDayStart}</span>
              <span>•</span>
              <span>Target Rate: {targetProductionRate} pcs/hr</span>
            </div>
          </div>
        </div>

        {/* Global Line Status Banner in Header */}
        <div className="flex items-center gap-2 sm:gap-4">
          <div 
            id="line-status-badge"
            className={`px-3 py-1.5 rounded border flex items-center gap-2 transition-all ${
              isLineRunning 
                ? 'bg-[#1A2E1A] border-[#2A4D2A] text-[#00FF00]' 
                : 'bg-[#2E1A1A] border-[#4D2A2A] text-[#FF4444]'
            }`}
          >
            <div className={`w-2 h-2 rounded-full ${isLineRunning ? 'bg-[#00FF00] shadow-[0_0_8px_rgba(0,255,0,0.8)]' : 'bg-[#FF4444] animate-pulse shadow-[0_0_8px_rgba(255,68,68,0.8)]'}`} />
            <span className="text-xs font-bold uppercase tracking-wider">
              {isLineRunning ? 'LINE RUNNING' : `STOPPED (${stoppedStationList.length} FAULT)`}
            </span>
          </div>

          {/* Config Settings Button */}
          <button
            id="open-config-btn"
            onClick={() => setShowConfigModal(true)}
            className="flex items-center gap-1.5 bg-[#222] hover:bg-[#2a2a2a] text-[#BBB] hover:text-white border border-[#333] px-2.5 py-1.5 text-xs font-mono rounded cursor-pointer transition-colors"
            title="Configure Line Name, Station Display Names, and Parameters"
          >
            <Settings className="w-3.5 h-3.5 text-[#F27D26]" />
            <span className="hidden md:inline">Configure</span>
          </button>

          {/* JSON Snapshot Viewer Button */}
          <button
            id="json-modal-btn"
            onClick={() => setShowJsonModal(true)}
            className="flex items-center gap-1.5 bg-[#222] hover:bg-[#2a2a2a] text-[#BBB] hover:text-white border border-[#333] px-2.5 py-1.5 text-xs font-mono rounded cursor-pointer transition-colors"
            title="View Phase 2 KPI JSON Model"
          >
            <FileCode className="w-3.5 h-3.5 text-[#F27D26]" />
            <span className="hidden lg:inline">KPI Model</span>
          </button>
        </div>
      </header>

      {/* Main Grid Content */}
      <main id="main-content-grid" className="flex-1 grid grid-cols-12 gap-px bg-[#333] overflow-hidden">
        {/* Left 8-Column Main Telemetry & KPI Panel */}
        <section id="kpi-main-section" className="col-span-12 lg:col-span-8 bg-[#0F0F11] flex flex-col p-4 sm:p-5 gap-4 overflow-y-auto">
          
          {/* 1. TOP PRODUCTION DATA & KPI ENGINE CARDS (Phase 2 Core Calculations) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {/* Hourly Target vs Actual */}
            <div id="kpi-hourly-card" className="bg-[#161618] border border-[#222] p-3.5 flex flex-col justify-between relative overflow-hidden">
              <div className="flex justify-between items-start">
                <span className="text-[10px] uppercase text-[#888] font-bold tracking-wider">
                  Hourly Achievement
                </span>
                <span className="text-[9px] font-mono text-[#F27D26] bg-[#222] px-1 rounded">
                  {currentHourStart}-{currentHourEnd}
                </span>
              </div>
              <div className="my-2">
                <div className="flex items-baseline gap-2">
                  <span className={`text-2xl sm:text-3xl font-mono font-bold ${hourlyAchievementPercent >= 100 ? 'text-[#00FF00]' : hourlyAchievementPercent >= 85 ? 'text-[#F27D26]' : 'text-[#FF4444]'}`}>
                    {hourlyAchievementPercent}%
                  </span>
                </div>
                <div className="text-[11px] text-[#888] font-mono mt-0.5">
                  Actual: <span className="text-white font-bold">{currentHourActual}</span> / Target: {hourlyTarget} pcs
                </div>
              </div>
              {/* Progress bar */}
              <div className="w-full h-1.5 bg-[#222] rounded-full overflow-hidden mt-1">
                <div 
                  className={`h-full transition-all duration-300 ${hourlyAchievementPercent >= 100 ? 'bg-[#00FF00]' : 'bg-[#F27D26]'}`}
                  style={{ width: `${Math.min(100, hourlyAchievementPercent)}%` }}
                />
              </div>
            </div>

            {/* Cumulative Target vs Actual */}
            <div id="kpi-cumulative-card" className="bg-[#161618] border border-[#222] p-3.5 flex flex-col justify-between relative overflow-hidden">
              <div className="flex justify-between items-start">
                <span className="text-[10px] uppercase text-[#888] font-bold tracking-wider">
                  Cumulative Achievement
                </span>
                <span className="text-[9px] font-mono text-[#888] bg-[#222] px-1 rounded">
                  Shift Total
                </span>
              </div>
              <div className="my-2">
                <div className="flex items-baseline gap-2">
                  <span className={`text-2xl sm:text-3xl font-mono font-bold ${cumulativeAchievementPercent >= 100 ? 'text-[#00FF00]' : cumulativeAchievementPercent >= 85 ? 'text-[#F27D26]' : 'text-[#FF4444]'}`}>
                    {cumulativeAchievementPercent}%
                  </span>
                </div>
                <div className="text-[11px] text-[#888] font-mono mt-0.5">
                  Actual: <span className="text-white font-bold">{cumulativeActual}</span> / Target: {cumulativeTarget} pcs
                </div>
              </div>
              {/* Progress bar */}
              <div className="w-full h-1.5 bg-[#222] rounded-full overflow-hidden mt-1">
                <div 
                  className={`h-full transition-all duration-300 ${cumulativeAchievementPercent >= 100 ? 'bg-[#00FF00]' : 'bg-[#F27D26]'}`}
                  style={{ width: `${Math.min(100, cumulativeAchievementPercent)}%` }}
                />
              </div>
            </div>

            {/* Tact Time */}
            <div id="kpi-tact-card" className="bg-[#161618] border border-[#222] p-3.5 flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <span className="text-[10px] uppercase text-[#888] font-bold tracking-wider">
                  Tact Time
                </span>
                <Gauge className="w-3.5 h-3.5 text-[#888]" />
              </div>
              <div className="my-2 flex items-baseline">
                <span className="text-2xl sm:text-3xl font-mono text-white font-bold">
                  {tactTimeSeconds > 0 ? tactTimeSeconds.toFixed(2) : '--'}
                </span>
                <span className="text-xs font-mono text-[#888] ml-1.5">sec / pc</span>
              </div>
              <div className="text-[9px] text-[#666] font-mono">
                Pitch: {productPitchMeters}m • Speed: {lineSpeed} {speedUnit}
              </div>
            </div>

            {/* Production Counter D452 */}
            <div id="kpi-counter-card" className="bg-[#161618] border border-[#222] p-3.5 flex flex-col justify-between">
              <div className="flex justify-between items-start">
                <span className="text-[10px] uppercase text-[#888] font-bold tracking-wider">
                  Continuous Counter (D452)
                </span>
                <span className="text-[9px] font-mono text-[#00FF00]">RAW</span>
              </div>
              <div className="my-2 flex items-baseline">
                <span className="text-2xl sm:text-3xl font-mono text-[#F27D26] font-bold">
                  {productionCounter.toLocaleString()}
                </span>
                <span className="text-xs font-mono text-[#888] ml-1.5">pcs</span>
              </div>
              <div className="text-[9px] text-[#666] font-mono">
                Target Daily: {dailyTarget} pcs
              </div>
            </div>
          </div>

          {/* 2. Interactive Testing Toolbar for Phase 2 Engine */}
          <div className="bg-[#161618] border border-[#222] p-2.5 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase text-[#888]">Engine Controls:</span>
              <button
                id="advance-hour-btn"
                onClick={handleAdvanceHour}
                className="bg-[#222] hover:bg-[#2A2A2D] text-[#EEE] px-2.5 py-1 text-xs font-mono rounded border border-[#333] cursor-pointer flex items-center gap-1"
                title="Finalize active hour into completed hours history table"
              >
                <Clock className="w-3 h-3 text-[#F27D26]" />
                <span>Finalize & Next Hour</span>
              </button>
              <button
                id="counter-reset-btn"
                onClick={handleSimulateCounterReset}
                className="bg-[#222] hover:bg-[#2A2A2D] text-[#EEE] px-2.5 py-1 text-xs font-mono rounded border border-[#333] cursor-pointer flex items-center gap-1"
                title="Simulate D452 Counter Reset (999 -> 10) to verify safe rollover logic"
              >
                <RotateCcw className="w-3 h-3 text-[#FF4444]" />
                <span>Test Rollover (999→10)</span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-[#666]">
                Target Rate: <span className="text-white">{targetProductionRate} pcs/hr</span>
              </span>
            </div>
          </div>

          {/* 3. Real-Time Conveyor Stations with Configurable Display Names */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Conveyor Line 1 (Stations 1-5, M550-M554) */}
            <div id="conveyor-line-1" className="bg-[#161618] border border-[#222] p-3.5 flex flex-col justify-between">
              <div>
                <div className="text-xs mb-3 flex items-center justify-between border-b border-[#262628] pb-2">
                  <span className="font-bold tracking-wider text-white">CONVEYOR LINE 1</span>
                  <div className="flex items-center gap-2 font-mono text-[10px] text-[#888]">
                    <span>M550–M554</span>
                    <span className="bg-[#222] px-1.5 py-0.5 rounded text-[#F27D26]">CNV_01</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  {conveyor1Stations.map((station) => (
                    <div
                      key={station.key}
                      id={`station-row-${station.id}`}
                      onClick={() => toggleStation(station.key, station.id)}
                      title={`Click to toggle station status (Address: ${station.address})`}
                      className={`flex items-center justify-between p-2 bg-[#1C1C1E] transition-all cursor-pointer hover:bg-[#252528] ${
                        !station.active ? 'border-l-2 border-[#FF4444]' : 'border-l-2 border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono text-[#888] w-12">{station.address}</span>
                        <div className="flex flex-col">
                          <span className="text-xs uppercase font-medium text-[#D0D0D0]">{station.name}</span>
                          <span className="text-[9px] text-[#555] font-mono">Station {station.id}</span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono uppercase text-[#666]">
                          {station.active ? 'RUNNING' : 'STOPPED'}
                        </span>
                        <div
                          className={`w-3 h-3 rounded-sm transition-all ${
                            station.active
                              ? 'bg-[#00FF00] shadow-[0_0_8px_rgba(0,255,0,0.3)]'
                              : 'bg-[#FF4444] shadow-[0_0_8px_rgba(255,68,68,0.5)]'
                          }`}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-2.5 pt-2 border-t border-[#222] flex justify-between text-[10px] text-[#666]">
                <span>Status: {conveyor1Stations.every((s) => s.active) ? 'NORMAL' : 'FAULT / STOPPED'}</span>
                <span>Click station to toggle bit</span>
              </div>
            </div>

            {/* Conveyor Line 2 (Stations 6-10, M555-M559) */}
            <div id="conveyor-line-2" className="bg-[#161618] border border-[#222] p-3.5 flex flex-col justify-between">
              <div>
                <div className="text-xs mb-3 flex items-center justify-between border-b border-[#262628] pb-2">
                  <span className="font-bold tracking-wider text-white">CONVEYOR LINE 2</span>
                  <div className="flex items-center gap-2 font-mono text-[10px] text-[#888]">
                    <span>M555–M559</span>
                    <span className="bg-[#222] px-1.5 py-0.5 rounded text-[#F27D26]">CNV_02</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  {conveyor2Stations.map((station) => (
                    <div
                      key={station.key}
                      id={`station-row-${station.id}`}
                      onClick={() => toggleStation(station.key, station.id)}
                      title={`Click to toggle station status (Address: ${station.address})`}
                      className={`flex items-center justify-between p-2 bg-[#1C1C1E] transition-all cursor-pointer hover:bg-[#252528] ${
                        !station.active ? 'border-l-2 border-[#FF4444]' : 'border-l-2 border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono text-[#888] w-12">{station.address}</span>
                        <div className="flex flex-col">
                          <span className="text-xs uppercase font-medium text-[#D0D0D0]">{station.name}</span>
                          <span className="text-[9px] text-[#555] font-mono">Station {station.id}</span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono uppercase text-[#666]">
                          {station.active ? 'RUNNING' : 'STOPPED'}
                        </span>
                        <div
                          className={`w-3 h-3 rounded-sm transition-all ${
                            station.active
                              ? 'bg-[#00FF00] shadow-[0_0_8px_rgba(0,255,0,0.3)]'
                              : 'bg-[#FF4444] shadow-[0_0_8px_rgba(255,68,68,0.5)]'
                          }`}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-2.5 pt-2 border-t border-[#222] flex justify-between text-[10px] text-[#666]">
                <span>Status: {conveyor2Stations.every((s) => s.active) ? 'NORMAL' : 'FAULT / STOPPED'}</span>
                <span>Click station to toggle bit</span>
              </div>
            </div>
          </div>

          {/* 4. Hourly Production Snapshots History Table (Section 8 Schema) */}
          <div className="bg-[#161618] border border-[#222] p-3.5">
            <div className="flex items-center justify-between mb-2.5 pb-2 border-b border-[#262628]">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-3.5 h-3.5 text-[#F27D26]" />
                <h3 className="text-xs uppercase font-bold tracking-wider text-white">
                  Hourly Production Snapshots (Shift History)
                </h3>
              </div>
              <span className="text-[10px] font-mono text-[#888]">
                {completedHours.length} Completed Hour(s)
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="border-b border-[#262628] text-[10px] text-[#666] uppercase">
                    <th className="py-1.5 px-2">Date</th>
                    <th className="py-1.5 px-2">Bucket</th>
                    <th className="py-1.5 px-2 text-right">Target</th>
                    <th className="py-1.5 px-2 text-right">Actual</th>
                    <th className="py-1.5 px-2 text-right">Hourly %</th>
                    <th className="py-1.5 px-2 text-right">Cumul. Target</th>
                    <th className="py-1.5 px-2 text-right">Cumul. Actual</th>
                    <th className="py-1.5 px-2 text-right">Cumul. %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#222]">
                  {completedHours.map((row, idx) => (
                    <tr key={idx} className="hover:bg-[#1E1E22] transition-colors">
                      <td className="py-2 px-2 text-[#AAA]">{row.date}</td>
                      <td className="py-2 px-2 text-[#F27D26]">{row.hour_start} - {row.hour_end}</td>
                      <td className="py-2 px-2 text-right text-[#AAA]">{row.hourly_target}</td>
                      <td className="py-2 px-2 text-right text-white font-bold">{row.actual_production}</td>
                      <td className={`py-2 px-2 text-right font-bold ${row.hourly_achievement_percent >= 100 ? 'text-[#00FF00]' : 'text-[#F27D26]'}`}>
                        {row.hourly_achievement_percent.toFixed(1)}%
                      </td>
                      <td className="py-2 px-2 text-right text-[#AAA]">{row.cumulative_target}</td>
                      <td className="py-2 px-2 text-right text-white font-bold">{row.cumulative_actual}</td>
                      <td className={`py-2 px-2 text-right font-bold ${row.cumulative_achievement_percent >= 100 ? 'text-[#00FF00]' : 'text-[#F27D26]'}`}>
                        {row.cumulative_achievement_percent.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                  {/* Live Active Hour Row */}
                  <tr className="bg-[#1C1C20] font-bold">
                    <td className="py-2 px-2 text-[#888]">{new Date().toISOString().split('T')[0]}</td>
                    <td className="py-2 px-2 text-[#00FF00] flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#00FF00] animate-pulse" />
                      {currentHourStart} - {currentHourEnd} (Live)
                    </td>
                    <td className="py-2 px-2 text-right text-[#AAA]">{hourlyTarget}</td>
                    <td className="py-2 px-2 text-right text-white">{currentHourActual}</td>
                    <td className={`py-2 px-2 text-right ${hourlyAchievementPercent >= 100 ? 'text-[#00FF00]' : 'text-[#F27D26]'}`}>
                      {hourlyAchievementPercent.toFixed(1)}%
                    </td>
                    <td className="py-2 px-2 text-right text-[#AAA]">{cumulativeTarget}</td>
                    <td className="py-2 px-2 text-right text-white">{cumulativeActual}</td>
                    <td className={`py-2 px-2 text-right ${cumulativeAchievementPercent >= 100 ? 'text-[#00FF00]' : 'text-[#F27D26]'}`}>
                      {cumulativeAchievementPercent.toFixed(1)}%
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Right 4-Column Live Communication & Engine Diagnostics Panel */}
        <aside id="communication-log-panel" className="col-span-12 lg:col-span-4 bg-[#0A0A0C] border-t lg:border-t-0 lg:border-l border-[#333] flex flex-col overflow-hidden">
          {/* Header */}
          <div className="p-3.5 border-b border-[#222] flex justify-between items-center bg-[#111113] shrink-0">
            <div className="flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 text-[#F27D26]" />
              <h2 className="text-[10px] uppercase tracking-widest font-bold text-[#888]">
                Telemetry & KPI Events
              </h2>
            </div>
            <div className="flex items-center gap-2 font-mono text-[9px] text-[#666]">
              <span>POLL: {pollingRateMs}ms</span>
              <div className="w-2 h-2 rounded-full bg-[#00FF00] animate-pulse" />
            </div>
          </div>

          {/* Log Stream */}
          <div className="flex-1 p-3.5 font-mono text-[11px] space-y-1.5 overflow-y-auto leading-relaxed">
            {logs.map((log) => {
              let tagColor = 'text-[#888]';
              if (log.level === 'INFO') tagColor = 'text-[#00FF00]';
              if (log.level === 'DATA') tagColor = 'text-[#00FF00] font-bold';
              if (log.level === 'WARN') tagColor = 'text-[#F27D26] font-bold';
              if (log.level === 'ERROR') tagColor = 'text-[#FF4444] font-bold';

              return (
                <div key={log.id} className="flex items-start gap-1.5">
                  <span className="text-[#555] shrink-0">[{log.timestamp}]</span>
                  <span className={`w-11 shrink-0 ${tagColor}`}>{log.level}</span>
                  <span className="text-[#C8C8C8] break-all">{log.message}</span>
                </div>
              );
            })}
            <div ref={logsEndRef} />
          </div>

          {/* Diagnostic KPI Telemetry Box */}
          <div className="p-3.5 border-t border-[#222] bg-[#111113] shrink-0">
            <div className="grid grid-cols-2 gap-2 mb-2">
              <div className="bg-[#1C1C1E] p-2 text-center border border-[#262628]">
                <span className="block text-[8px] uppercase text-[#666] tracking-wider">Line Status</span>
                <span className={`text-[10px] font-mono font-bold ${isLineRunning ? 'text-[#00FF00]' : 'text-[#FF4444]'}`}>
                  {isLineRunning ? 'RUNNING' : 'STOPPED'}
                </span>
              </div>
              <div className="bg-[#1C1C1E] p-2 text-center border border-[#262628]">
                <span className="block text-[8px] uppercase text-[#666] tracking-wider">Stopped Stations</span>
                <span className="text-[10px] font-mono text-white">
                  {stoppedStationList.length > 0 ? stoppedStationList.map((s) => `S${s.id}`).join(', ') : 'None (All OK)'}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="bg-[#1C1C1E] p-2 text-center border border-[#262628]">
                <span className="block text-[8px] uppercase text-[#666] tracking-wider">Tact Time Formula</span>
                <span className="text-[10px] font-mono text-[#AAA]">Pitch / Speed</span>
              </div>
              <div className="bg-[#1C1C1E] p-2 text-center border border-[#262628]">
                <span className="block text-[8px] uppercase text-[#666] tracking-wider">Engineering Unit</span>
                <span className="text-[10px] font-mono text-[#F27D26]">{speedUnit}</span>
              </div>
            </div>
          </div>
        </aside>
      </main>

      {/* Industrial SCADA Footer */}
      <footer id="scada-footer" className="h-8 bg-[#161618] border-t border-[#333] flex items-center justify-between px-6 text-[10px] text-[#666] uppercase tracking-widest font-medium shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[#00FF00]"></span>
          <span>Phase 2: Production Data & KPI Engine Active</span>
        </div>
        <div className="hidden sm:block">
          Line: {assemblyLineName} • Shift Start: {productionDayStart}
        </div>
        <div className="font-mono text-[#00FF00]">
          Link: CONNECTED (Sim)
        </div>
      </footer>

      {/* Configuration Dialog (Requirement 1A & 1B) */}
      {showConfigModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#161618] border border-[#333] rounded max-w-xl w-full max-h-[90vh] flex flex-col shadow-2xl">
            <div className="p-4 border-b border-[#262628] flex justify-between items-center">
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-[#F27D26]" />
                <h3 className="font-bold text-sm text-white uppercase tracking-wider font-mono">
                  Production Configuration & Mappings
                </h3>
              </div>
              <button
                onClick={() => setShowConfigModal(false)}
                className="text-[#888] hover:text-white font-mono text-sm px-2 py-1 bg-[#222] rounded cursor-pointer"
              >
                ✕ CLOSE
              </button>
            </div>

            {/* Tab Navigation */}
            <div className="flex border-b border-[#262628] bg-[#111113] text-xs font-mono">
              <button
                onClick={() => setConfigTab('line')}
                className={`py-2 px-4 border-b-2 font-medium cursor-pointer ${
                  configTab === 'line' ? 'border-[#F27D26] text-white bg-[#161618]' : 'border-transparent text-[#888] hover:text-white'
                }`}
              >
                Line & Shift Setup
              </button>
              <button
                onClick={() => setConfigTab('stations')}
                className={`py-2 px-4 border-b-2 font-medium cursor-pointer ${
                  configTab === 'stations' ? 'border-[#F27D26] text-white bg-[#161618]' : 'border-transparent text-[#888] hover:text-white'
                }`}
              >
                Station Display Names (10)
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-4 text-xs font-mono">
              {configTab === 'line' ? (
                <div className="space-y-3">
                  <div>
                    <label className="block text-[#888] uppercase text-[10px] mb-1">
                      Assembly Line Name (Requirement 1A)
                    </label>
                    <input
                      type="text"
                      value={assemblyLineName}
                      onChange={(e) => setAssemblyLineName(e.target.value)}
                      className="w-full bg-[#0A0A0C] border border-[#333] px-3 py-2 text-white rounded font-mono focus:border-[#F27D26] focus:outline-none"
                    />
                    <span className="text-[10px] text-[#666]">User can change this without touching Python source code.</span>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[#888] uppercase text-[10px] mb-1">
                        Production Day Start
                      </label>
                      <input
                        type="text"
                        value={productionDayStart}
                        onChange={(e) => setProductionDayStart(e.target.value)}
                        className="w-full bg-[#0A0A0C] border border-[#333] px-3 py-2 text-white rounded font-mono focus:border-[#F27D26] focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[#888] uppercase text-[10px] mb-1">
                        Target Production Rate (pcs/hr)
                      </label>
                      <input
                        type="number"
                        value={targetProductionRate}
                        onChange={(e) => setTargetProductionRate(parseFloat(e.target.value) || 100)}
                        className="w-full bg-[#0A0A0C] border border-[#333] px-3 py-2 text-white rounded font-mono focus:border-[#F27D26] focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[#888] uppercase text-[10px] mb-1">
                        Product Pitch (Meters)
                      </label>
                      <input
                        type="number"
                        step="0.05"
                        value={productPitchMeters}
                        onChange={(e) => setProductPitchMeters(parseFloat(e.target.value) || 0.75)}
                        className="w-full bg-[#0A0A0C] border border-[#333] px-3 py-2 text-white rounded font-mono focus:border-[#F27D26] focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[#888] uppercase text-[10px] mb-1">
                        Engineering Unit (D450)
                      </label>
                      <input
                        type="text"
                        readOnly
                        value={`${speedUnit} (Scale: ${speedScaleFactor})`}
                        className="w-full bg-[#1A1A1D] border border-[#333] px-3 py-2 text-[#AAA] rounded font-mono cursor-not-allowed"
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-[10px] text-[#F27D26] mb-2 font-mono">
                    Physical PLC mapping remains fixed (M550–M559). Edit the display names below:
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((id) => {
                      const addr = id <= 5 ? `M${550 + id - 1}` : `M${555 + id - 6}`;
                      return (
                        <div key={id} className="bg-[#0A0A0C] border border-[#262628] p-2 rounded">
                          <div className="flex justify-between text-[10px] text-[#666] mb-1">
                            <span>Station {id} ({addr})</span>
                            <span>{id <= 5 ? 'Conv 1' : 'Conv 2'}</span>
                          </div>
                          <input
                            type="text"
                            value={stationNames[id] || ''}
                            onChange={(e) =>
                              setStationNames((prev) => ({
                                ...prev,
                                [id]: e.target.value,
                              }))
                            }
                            className="w-full bg-[#161618] border border-[#333] px-2 py-1 text-white rounded font-mono text-xs focus:border-[#F27D26] focus:outline-none"
                          />
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            <div className="p-3 border-t border-[#262628] bg-[#111113] flex justify-between items-center text-[10px] font-mono">
              <span className="text-[#888]">Settings reflect live in the telemetry & KPI Engine.</span>
              <button
                onClick={() => {
                  setShowConfigModal(false);
                  addLog('INFO', `Configuration saved: Line '${assemblyLineName}', Target: ${targetProductionRate} pcs/hr`);
                }}
                className="bg-[#F27D26] text-black font-bold px-3 py-1.5 rounded cursor-pointer hover:bg-[#ff9142]"
              >
                Apply Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Phase 2 KPI JSON Schema Modal */}
      {showJsonModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#161618] border border-[#333] rounded max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            <div className="p-4 border-b border-[#262628] flex justify-between items-center">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-[#F27D26]" />
                <h3 className="font-bold text-sm text-white uppercase tracking-wider font-mono">
                  Phase 2 KPI Snapshot Data Structure
                </h3>
              </div>
              <button
                onClick={() => setShowJsonModal(false)}
                className="text-[#888] hover:text-white font-mono text-sm px-2 py-1 bg-[#222] rounded cursor-pointer"
              >
                ✕ CLOSE
              </button>
            </div>

            <div className="p-4 overflow-y-auto font-mono text-xs text-[#00FF00] bg-[#0A0A0C]">
              <pre className="whitespace-pre-wrap leading-relaxed">
                {JSON.stringify(phase2JsonSnapshot, null, 2)}
              </pre>
            </div>

            <div className="p-3 border-t border-[#262628] bg-[#111113] text-[10px] text-[#888] flex justify-between">
              <span>Produced by: kpi/kpi_engine.py (KPISnapshot)</span>
              <span className="text-[#F27D26]">Includes Hourly & Cumulative Achievement %</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
