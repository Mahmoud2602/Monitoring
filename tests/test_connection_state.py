"""
Unit tests for PLC Connection State Machine, Error Handling & Retries.
"""
import unittest

from plc.plc_client import PLCClient
from plc.plc_data import ConnectionState, PLCMappingConfig
from plc.simulated_driver import SimulatedPLCDriver


class TestConnectionState(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = PLCMappingConfig({
            "registers": {
                "speed": {"address": "D450"},
                "speed_setpoint": {"address": "D451"},
                "production_counter": {"address": "D452"},
                "daily_target": {"address": "D453"},
            },
            "stations": {
                "conv1_station1": {"address": "M550"},
            },
        })
        self.driver = SimulatedPLCDriver(host="192.168.1.10", port=502)
        self.client = PLCClient(
            driver=self.driver,
            mapping=self.mapping,
            cycle_time_ms=100,
            retry_interval_seconds=0.5,
        )

    def test_initial_state_is_disconnected(self) -> None:
        self.assertEqual(self.client.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.client.is_connected)

    def test_connect_success(self) -> None:
        result = self.client.connect()
        self.assertTrue(result)
        self.assertEqual(self.client.connection_state, ConnectionState.CONNECTED)
        self.assertTrue(self.client.is_connected)

    def test_connect_failure_does_not_crash(self) -> None:
        self.driver.force_connection_failure = True
        result = self.client.connect()
        self.assertFalse(result)
        self.assertEqual(self.client.connection_state, ConnectionState.ERROR)
        self.assertFalse(self.client.is_connected)

    def test_read_cycle_reconnects_when_disconnected(self) -> None:
        # Client starts disconnected
        self.assertFalse(self.client.is_connected)

        # read_cycle should automatically connect and fetch telemetry
        telemetry = self.client.read_cycle()
        self.assertTrue(self.client.is_connected)
        self.assertTrue(telemetry.connected)
        self.assertEqual(telemetry.connection_state, ConnectionState.CONNECTED)

    def test_read_error_recovery_graceful(self) -> None:
        self.client.connect()
        self.assertTrue(self.client.is_connected)

        # Inject read failure
        self.driver.force_read_error = True
        telemetry = self.client.read_cycle()

        # Application must NOT crash, and status should transition to RECONNECTING
        self.assertEqual(self.client.connection_state, ConnectionState.RECONNECTING)
        self.assertFalse(telemetry.connected)
        self.assertIsNotNone(telemetry.error_message)

        # Clear simulated read error
        self.driver.force_read_error = False
        # Next read cycle should reconnect successfully
        recovered_telemetry = self.client.read_cycle()
        self.assertTrue(self.client.is_connected)
        self.assertTrue(recovered_telemetry.connected)


if __name__ == "__main__":
    unittest.main()
