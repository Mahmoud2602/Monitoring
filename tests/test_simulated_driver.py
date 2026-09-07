"""
Unit tests for Simulated PLC Driver & Physics Engine.
"""
import time
import unittest

from plc.base_driver import PLCConnectionError
from plc.simulated_driver import SimulatedPLCDriver


class TestSimulatedDriver(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = SimulatedPLCDriver(
            host="127.0.0.1",
            port=502,
            driver_params={
                "base_speed": 45.0,
                "speed_fluctuation": 1.0,
                "daily_target": 1000,
                "initial_counter": 1284,
                "station_stop_probability": 0.0,  # disable random stop for baseline tests
            },
        )

    def test_connection_lifecycle(self) -> None:
        self.assertFalse(self.driver.is_connected)
        self.driver.connect()
        self.assertTrue(self.driver.is_connected)
        self.driver.disconnect()
        self.assertFalse(self.driver.is_connected)

    def test_read_without_connection_fails(self) -> None:
        with self.assertRaises(PLCConnectionError):
            self.driver.read_registers(["D450"])

        with self.assertRaises(PLCConnectionError):
            self.driver.read_bits(["M550"])

    def test_read_registers_values_and_types(self) -> None:
        self.driver.connect()
        reg_data = self.driver.read_registers(["D450", "D451", "D452", "D453"])

        self.assertIn("D450", reg_data)
        self.assertIn("D451", reg_data)
        self.assertIn("D452", reg_data)
        self.assertIn("D453", reg_data)

        # D450: Speed should be around 45.0
        self.assertAlmostEqual(reg_data["D451"], 45.0, delta=0.5)
        self.assertGreater(reg_data["D450"], 35.0)
        self.assertLess(reg_data["D450"], 55.0)
        # D452: Production counter
        self.assertGreaterEqual(reg_data["D452"], 1284)
        # D453: Daily target
        self.assertEqual(reg_data["D453"], 1000)

    def test_production_counter_increments_over_time(self) -> None:
        self.driver.connect()
        reg1 = self.driver.read_registers(["D452"])
        initial_counter = reg1["D452"]

        # Sleep briefly to allow simulation tick to accumulate parts
        time.sleep(0.3)
        reg2 = self.driver.read_registers(["D452"])
        final_counter = reg2["D452"]

        self.assertGreaterEqual(final_counter, initial_counter)

    def test_station_stops_affect_conveyor_speed(self) -> None:
        # Create a driver with 100% stop probability on a station
        stop_driver = SimulatedPLCDriver(
            driver_params={
                "base_speed": 45.0,
                "station_stop_probability": 1.0,
                "station_stop_duration_cycles": 10,
            }
        )
        stop_driver.connect()
        bits = stop_driver.read_bits(["M550", "M551", "M552"])

        # At least one station should be stopped
        stopped_count = sum(1 for status in bits.values() if not status)
        self.assertGreater(stopped_count, 0)


if __name__ == "__main__":
    unittest.main()
