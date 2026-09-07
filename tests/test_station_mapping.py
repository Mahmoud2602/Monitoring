"""
Unit tests for Conveyor Station Status Mapping (M550..M559).
"""
import unittest

from plc.plc_data import ConnectionState, PLCMappingConfig


class TestStationMapping(unittest.TestCase):
    def setUp(self) -> None:
        self.mapping = PLCMappingConfig.from_file("config/plc_mapping.json")

    def test_conveyor1_station_addresses(self) -> None:
        # Conveyor 1: M550 to M554
        expected_c1 = {
            "conv1_station1": "M550",
            "conv1_station2": "M551",
            "conv1_station3": "M552",
            "conv1_station4": "M553",
            "conv1_station5": "M554",
        }
        for key, addr in expected_c1.items():
            self.assertEqual(
                self.mapping.get_station_address(key),
                addr,
                f"Mismatch in Conveyor 1 address for {key}",
            )

    def test_conveyor2_station_addresses(self) -> None:
        # Conveyor 2: M555 to M559
        expected_c2 = {
            "conv2_station1": "M555",
            "conv2_station2": "M556",
            "conv2_station3": "M557",
            "conv2_station4": "M558",
            "conv2_station5": "M559",
        }
        for key, addr in expected_c2.items():
            self.assertEqual(
                self.mapping.get_station_address(key),
                addr,
                f"Mismatch in Conveyor 2 address for {key}",
            )

    def test_station_telemetry_normalization(self) -> None:
        # Simulate custom raw bit responses
        raw_registers = {"D450": 45.0, "D451": 45.0, "D452": 1200, "D453": 1000}
        raw_bits = {
            "M550": True,
            "M551": True,
            "M552": False,  # Station 3 Stopped on Conveyor 1
            "M553": True,
            "M554": True,
            "M555": True,
            "M556": True,
            "M557": True,
            "M558": False,  # Station 4 Stopped on Conveyor 2
            "M559": True,
        }

        normalized = self.mapping.map_raw_telemetry(
            raw_registers=raw_registers,
            raw_bits=raw_bits,
            connection_state=ConnectionState.CONNECTED,
        )

        stations = normalized.stations
        self.assertEqual(len(stations), 10)

        # Check Conveyor 1
        self.assertTrue(stations["conv1_station1"])
        self.assertTrue(stations["conv1_station2"])
        self.assertFalse(stations["conv1_station3"])
        self.assertTrue(stations["conv1_station4"])
        self.assertTrue(stations["conv1_station5"])

        # Check Conveyor 2
        self.assertTrue(stations["conv2_station1"])
        self.assertTrue(stations["conv2_station2"])
        self.assertTrue(stations["conv2_station3"])
        self.assertFalse(stations["conv2_station4"])
        self.assertTrue(stations["conv2_station5"])

        # Check detailed station metadata
        conv1_s3 = normalized.station_details["conv1_station3"]
        self.assertEqual(conv1_s3.station_index, 3)
        self.assertEqual(conv1_s3.conveyor, "Conveyor 1")
        self.assertEqual(conv1_s3.address, "M552")
        self.assertFalse(conv1_s3.is_active)


if __name__ == "__main__":
    unittest.main()
