"""
Unit Tests for Phase 3: Alarm Manager
Verifies alarm raising, active deduplication, clearing, severity handling,
and event subscriber callbacks.
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from database.alarm_manager import AlarmManager
from database.database_manager import DatabaseManager
from database.models import AlarmEventRecord
from database.repositories import AlarmRepository


class TestAlarmManager(unittest.TestCase):
    """Test suite for industrial alarm lifecycle management."""

    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.db_path = self.temp_file.name

        self.db_manager = DatabaseManager(self.db_path)
        self.alarm_repo = AlarmRepository(self.db_manager)
        self.alarm_mgr = AlarmManager(
            alarm_repo=self.alarm_repo,
            production_day_start="08:00",
        )

    def tearDown(self) -> None:
        self.db_manager.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_raise_and_clear_alarm(self) -> None:
        """Verify raising an alarm creates an active record and clearing closes it."""
        received_alarms = []
        self.alarm_mgr.register_listener(lambda al: received_alarms.append(al))

        alarm = self.alarm_mgr.raise_alarm(
            alarm_code="ALM_CONV_JAM",
            alarm_message="Part jam detected at transfer sensor",
            severity="HIGH",
            station_id=5,
            station_name="Transfer 1",
        )
        self.assertIsNotNone(alarm)
        self.assertEqual(len(received_alarms), 1)

        active = self.alarm_mgr.get_active_alarms()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].alarm_code, "ALM_CONV_JAM")

        time.sleep(0.04)

        cleared = self.alarm_mgr.clear_alarm(alarm_code="ALM_CONV_JAM", station_id=5)
        self.assertIsNotNone(cleared)
        self.assertIsNotNone(cleared.cleared_at)
        self.assertGreater(cleared.duration_seconds, 0.0)
        self.assertEqual(len(self.alarm_mgr.get_active_alarms()), 0)

    def test_duplicate_raise_ignored_while_active(self) -> None:
        """Verify that raising an alarm that is already active does not duplicate records."""
        al1 = self.alarm_mgr.raise_alarm("ALM_TEMP_HIGH", "Motor temperature above threshold", severity="WARNING")
        al2 = self.alarm_mgr.raise_alarm("ALM_TEMP_HIGH", "Motor temperature above threshold", severity="WARNING")

        self.assertEqual(al1.id, al2.id)
        self.assertEqual(len(self.alarm_repo.get_active_alarms()), 1)

    def test_restart_recovery_of_active_alarms(self) -> None:
        """Verify that a fresh AlarmManager recovers un-cleared active alarms from the database."""
        self.alarm_mgr.raise_alarm("ALM_SAFETY_GATE", "Safety gate interlock open", severity="CRITICAL")

        fresh_mgr = AlarmManager(alarm_repo=self.alarm_repo, production_day_start="08:00")
        self.assertEqual(len(fresh_mgr.get_active_alarms()), 1)

        fresh_mgr.clear_alarm("ALM_SAFETY_GATE")
        self.assertEqual(len(fresh_mgr.get_active_alarms()), 0)


if __name__ == "__main__":
    unittest.main()
