"""
Industrial PLC Production Monitor - Database Manager
Phase 3: Core SQLite connection management, initialization, schema validation,
and transaction control.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, Generator, List, Optional

from utils.logger import get_logger

logger = get_logger("database.manager")

SCHEMA_SQL = """
-- 1. production_data: Historical records for hourly production buckets
CREATE TABLE IF NOT EXISTS production_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    production_date TEXT NOT NULL,
    hour_start TEXT NOT NULL,
    hour_end TEXT NOT NULL,
    hourly_target REAL NOT NULL,
    actual_production INTEGER NOT NULL,
    hourly_achievement_percent REAL NOT NULL,
    cumulative_target REAL NOT NULL,
    cumulative_actual INTEGER NOT NULL,
    cumulative_achievement_percent REAL NOT NULL,
    tact_time REAL DEFAULT 0.0,
    average_speed REAL,
    production_counter INTEGER DEFAULT 0,
    UNIQUE(production_date, hour_start)
);

CREATE INDEX IF NOT EXISTS idx_prod_date ON production_data(production_date);
CREATE INDEX IF NOT EXISTS idx_prod_timestamp ON production_data(timestamp);
CREATE INDEX IF NOT EXISTS idx_prod_date_hour ON production_data(production_date, hour_start);

-- 2. downtime_events: Every discrete stop event per station
CREATE TABLE IF NOT EXISTS downtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id INTEGER NOT NULL,
    station_name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_seconds REAL,
    alarm_id TEXT,
    alarm_message TEXT,
    production_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_downtime_date ON downtime_events(production_date);
CREATE INDEX IF NOT EXISTS idx_downtime_station ON downtime_events(station_id);
CREATE INDEX IF NOT EXISTS idx_downtime_date_station ON downtime_events(production_date, station_id);
CREATE INDEX IF NOT EXISTS idx_downtime_start ON downtime_events(start_time);
CREATE INDEX IF NOT EXISTS idx_downtime_open ON downtime_events(station_id, end_time);

-- 3. alarm_events: Alarms and faults history
CREATE TABLE IF NOT EXISTS alarm_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    station_id INTEGER,
    station_name TEXT,
    alarm_code TEXT NOT NULL,
    alarm_message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'WARNING',
    active INTEGER NOT NULL DEFAULT 1,
    cleared_at TEXT,
    duration_seconds REAL,
    production_date TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alarm_date ON alarm_events(production_date);
CREATE INDEX IF NOT EXISTS idx_alarm_active ON alarm_events(active);
CREATE INDEX IF NOT EXISTS idx_alarm_station ON alarm_events(station_id);
CREATE INDEX IF NOT EXISTS idx_alarm_date_station ON alarm_events(production_date, station_id);
CREATE INDEX IF NOT EXISTS idx_alarm_date_severity ON alarm_events(production_date, severity);

-- 4. station_status: Meaningful state transitions (RUNNING <-> STOPPED)
CREATE TABLE IF NOT EXISTS station_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    station_id INTEGER NOT NULL,
    station_name TEXT NOT NULL,
    status TEXT NOT NULL,
    plc_address TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_station_status_id ON station_status(station_id);
CREATE INDEX IF NOT EXISTS idx_station_status_time ON station_status(timestamp);

-- 5. daily_summary: Daily aggregated roll-up
CREATE TABLE IF NOT EXISTS daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_date TEXT NOT NULL UNIQUE,
    daily_target REAL NOT NULL,
    total_production INTEGER NOT NULL,
    cumulative_achievement_percent REAL NOT NULL,
    total_downtime_seconds REAL NOT NULL,
    total_stops INTEGER NOT NULL,
    running_time_seconds REAL NOT NULL,
    average_speed REAL NOT NULL,
    average_tact_time REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON daily_summary(production_date);
"""

EXPECTED_TABLES = [
    "production_data",
    "downtime_events",
    "alarm_events",
    "station_status",
    "daily_summary",
]


class DatabaseManager:
    """
    Manages SQLite database connections, schema provisioning, thread safety,
    and transactions for the industrial monitoring application.
    """

    def __init__(
        self,
        db_path: str = "production_monitor.db",
        auto_init: bool = True,
    ) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._is_memory = (db_path == ":memory:" or "mode=memory" in db_path)

        # For in-memory database, hold one persistent connection so tables persist across contexts
        self._persistent_mem_conn: Optional[sqlite3.Connection] = None
        if self._is_memory:
            self._persistent_mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_mem_conn.row_factory = sqlite3.Row

        if auto_init:
            self.initialize_database()

    def get_raw_connection(self) -> sqlite3.Connection:
        """Create or return an SQLite connection with optimized pragmas and row_factory."""
        if self._is_memory:
            if self._persistent_mem_conn is None:
                self._persistent_mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._persistent_mem_conn.row_factory = sqlite3.Row
            return self._persistent_mem_conn

        # Ensure parent directory exists for file databases
        parent_dir = Path(self.db_path).parent
        if parent_dir and not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)

        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=15.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Configure database performance & integrity PRAGMAs
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.close()
            return conn
        except sqlite3.Error as exc:
            logger.error("Failed to connect to SQLite database at '%s': %s", self.db_path, exc)
            raise

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Thread-safe context manager providing an active SQLite connection.
        Automatically commits on successful block exit, and rolls back on exception.
        """
        with self._lock:
            conn = self.get_raw_connection()
            try:
                yield conn
                if not self._is_memory:
                    conn.commit()
                else:
                    self._persistent_mem_conn.commit()
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.error("Database transaction rolled back due to exception: %s", exc)
                raise
            finally:
                if not self._is_memory:
                    conn.close()

    def initialize_database(self) -> None:
        """
        Idempotently create all tables, indexes, and schema structures.
        Validates structural integrity immediately following creation.
        """
        logger.info("Initializing database at: '%s'", self.db_path)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(SCHEMA_SQL)
            cursor.close()

        # Validate structure
        is_valid = self.validate_database_structure()
        if not is_valid:
            raise RuntimeError(f"Database validation failed for '{self.db_path}'")
        logger.info("Database initialized and verified successfully.")

    def validate_database_structure(self) -> bool:
        """
        Inspect SQLite catalog to ensure all expected tables exist.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                existing_tables = {row["name"] for row in cursor.fetchall()}
                cursor.close()

                missing = [t for t in EXPECTED_TABLES if t not in existing_tables]
                if missing:
                    logger.error("Database structure validation failed. Missing tables: %s", missing)
                    return False
                return True
        except sqlite3.Error as exc:
            logger.error("Database structure validation encountered an error: %s", exc)
            return False

    def backup(self, destination_path: Optional[str] = None) -> str:
        """
        Create a live point-in-time snapshot backup of the SQLite database
        without locking out concurrent readers or writers.
        """
        import os
        from datetime import datetime

        if not destination_path:
            os.makedirs("backups", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            destination_path = f"backups/production_monitor_backup_{ts}.db"
        else:
            dest_dir = os.path.dirname(destination_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)

        with self.get_connection() as src_conn:
            dest_conn = sqlite3.connect(destination_path)
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()

        logger.info("Database successfully backed up to: %s", destination_path)
        return destination_path

    def close(self) -> None:
        """Close persistent resources if open."""
        with self._lock:
            if self._persistent_mem_conn is not None:
                try:
                    self._persistent_mem_conn.close()
                except Exception:
                    pass
                self._persistent_mem_conn = None

