"""
Unit Tests for Phase 3: Downtime Manager
Verifies state transition detection, continuous stop deduplication,
accurate duration calculation in seconds, and restart recovery.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from database.database_manager import DatabaseManager
from database.downtime_manager import DowntimeManager
from database.repositories import DowntimeRepository, StationStatusRepository


class TestDowntimeManager(unittest.TestCase):
    """Rigorous tests for industrial downtime detection and lifecycle tracking."""

    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

        self.db_manager = DatabaseManager(self.db_path)
        self.downtime_repo = DowntimeRepository(self.db_manager)
        self.status_repo = StationStatusRepository(self.db_manager)
        self.downtime_mgr = DowntimeManager(
            downtime_repo=self.downtime_repo,
            status_repo=self.status_repo,
            production_day_start="08:00",
        )

    def tearDown(self) -> None:
        self.db_manager.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_01_single_stop_event_creation_and_closure(self) -> None:
        """
        Verify that a RUNNING -> STOPPED transition creates an open event,
        and STOPPED -> RUNNING closes it with accurate duration.
        """
        # Cycle 1: All stations running
        states_cycle1 = {
            1: ("Assembly 1", "M550", True),
            2: ("Screw Installation", "M551", True),
        }
        self.downtime_mgr.process_station_states(states_cycle1)
        self.assertEqual(len(self.downtime_mgr.get_active_events()), 0)

        # Cycle 2: Station 2 stops
        states_cycle2 = {
            1: ("Assembly 1", "M550", True),
            2: ("Screw Installation", "M551", False),
        }
        self.downtime_mgr.process_station_states(states_cycle2)
        active = self.downtime_mgr.get_active_events()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].station_id, 2)
        self.assertIsNone(active[0].end_time)

        # Allow slight time elapsed
        time.sleep(0.05)

        # Cycle 3: Station 2 resumes running
        states_cycle3 = {
            1: ("Assembly 1", "M550", True),
            2: ("Screw Installation", "M551", True),
        }
        self.downtime_mgr.process_station_states(states_cycle3)
        self.assertEqual(len(self.downtime_mgr.get_active_events()), 0)

        # Check in repository
        history = self.downtime_repo.get_by_station(2)
        self.assertEqual(len(history), 1)
        closed_ev = history[0]
        self.assertIsNotNone(closed_ev.end_time)
        self.assertIsNotNone(closed_ev.duration_seconds)
        self.assertGreaterEqual(closed_ev.duration_seconds, 0.04)

    def test_02_continuous_stop_does_not_create_duplicate_records(self) -> None:
        """
        CRITICAL REQUIREMENT: One continuous stop must create ONE event.
        Verify that 20 polling cycles with a station in STOPPED state
        only creates 1 open record in the database.
        """
        # Initial scan: Running
        self.downtime_mgr.process_station_states({5: ("Transfer 1", "M554", True)})

        # Station 5 stops and stays stopped for 15 consecutive cycles
        for cycle in range(15):
            self.downtime_mgr.process_station_states({5: ("Transfer 1", "M554", False)})

        # Total open events in database must be exactly 1
        open_events = self.downtime_repo.get_open_events()
        self.assertEqual(len(open_events), 1, "Continuous stop must create exactly ONE event, not one per scan cycle!")

        # All events for station 5 in DB must be 1
        all_events = self.downtime_repo.get_by_station(5)
        self.assertEqual(len(all_events), 1)

        # Station 5 resumes running
        self.downtime_mgr.process_station_states({5: ("Transfer 1", "M554", True)})

        # Still 1 total event, now closed
        all_events_after = self.downtime_repo.get_by_station(5)
        self.assertEqual(len(all_events_after), 1)
        self.assertIsNotNone(all_events_after[0].end_time)

    def test_03_continuous_running_creates_no_downtime(self) -> None:
        """Verify that uninterrupted RUNNING states across multiple cycles create 0 downtime events."""
        for _ in range(10):
            self.downtime_mgr.process_station_states({
                1: ("Station 1", "M550", True),
                2: ("Station 2", "M551", True),
                3: ("Station 3", "M552", True),
            })

        self.assertEqual(len(self.downtime_repo.get_all_events()), 0)

    def test_04_multiple_stations_independent_stops(self) -> None:
        """Verify that multiple stations can stop and resume independently without interference."""
        # Station 1 and Station 7 both stop
        self.downtime_mgr.process_station_states({
            1: ("Station 1", "M550", False),
            7: ("Station 7", "M556", False),
        })
        self.assertEqual(len(self.downtime_mgr.get_active_events()), 2)

        # Station 1 recovers first
        self.downtime_mgr.process_station_states({
            1: ("Station 1", "M550", True),
            7: ("Station 7", "M556", False),
        })
        active = self.downtime_mgr.get_active_events()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].station_id, 7)

        # Station 7 recovers second
        self.downtime_mgr.process_station_states({
            1: ("Station 1", "M550", True),
            7: ("Station 7", "M556", True),
        })
        self.assertEqual(len(self.downtime_mgr.get_active_events()), 0)

        # Database should contain 1 closed event for Station 1 and 1 for Station 7
        self.assertEqual(len(self.downtime_repo.get_by_station(1)), 1)
        self.assertEqual(len(self.downtime_repo.get_by_station(7)), 1)

    def test_05_restart_recovery_of_unclosed_events(self) -> None:
        """
        Verify that if the application terminates while a station is stopped,
        a newly initialized DowntimeManager recovers the open event and closes it
        cleanly when the station resumes.
        """
        # Step 1: Start a stop in Manager 1
        self.downtime_mgr.process_station_states({4: ("Riveting", "M553", False)})
        self.assertEqual(len(self.downtime_mgr.get_active_events()), 1)

        # Step 2: Simulate application reboot by creating a fresh DowntimeManager on same DB
        fresh_mgr = DowntimeManager(
            downtime_repo=self.downtime_repo,
            status_repo=self.status_repo,
            production_day_start="08:00",
        )
        # Verify it recovered the active stop for Station 4
        self.assertEqual(len(fresh_mgr.get_active_events()), 1)
        self.assertEqual(fresh_mgr.get_active_events()[0].station_id, 4)

        # Step 3: Fresh manager observes Station 4 returning to RUNNING
        fresh_mgr.process_station_states({4: ("Riveting", "M553", True)})
        self.assertEqual(len(fresh_mgr.get_active_events()), 0)

        # Database event is closed cleanly
        events = self.downtime_repo.get_by_station(4)
        self.assertEqual(len(events), 1)
        self.assertIsNotNone(events[0].end_time)


if __name__ == "__main__":
    unittest.main()
