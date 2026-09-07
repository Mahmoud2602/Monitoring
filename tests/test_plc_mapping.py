"""
Unit tests for PLC Data Mapping & Configuration Schema.
"""
import unittest

from plc.plc_data import ConnectionState, PLCMappingConfig


class TestPLCMapping(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_mapping = {
            "registers": {
                "speed": {"address": "D450", "scale": 1.0, "type": "FLOAT"},
                "speed_setpoint": {"address": "D451", "scale": 1.0, "type": "FLOAT"},
                "production_counter": {"address": "D452", "scale": 1.0, "type": "INT"},
                "daily_target": {"address": "D453", "scale": 1.0, "type": "INT"},
            },
            "stations": {
                "conv1_station1": {"address": "M550", "conveyor": "Conveyor 1", "station_index": 1},
                "conv1_station2": {"address": "M551", "conveyor": "Conveyor 1", "station_index": 2},
                "conv2_station1": {"address": "M555", "conveyor": "Conveyor 2", "station_index": 1},
            },
        }
        self.mapping_config = PLCMappingConfig(self.sample_mapping)

    def test_address_extraction(self) -> None:
        reg_addrs = self.mapping_config.register_addresses
        self.assertIn("D450", reg_addrs)
        self.assertIn("D451", reg_addrs)
        self.assertIn("D452", reg_addrs)
        self.assertIn("D453", reg_addrs)

        station_addrs = self.mapping_config.station_addresses
        self.assertIn("M550", station_addrs)
        self.assertIn("M551", station_addrs)
        self.assertIn("M555", station_addrs)

    def test_raw_to_normalized_mapping(self) -> None:
        raw_registers = {"D450": 42.5, "D451": 45.0, "D452": 1284, "D453": 1000}
        raw_bits = {"M550": True, "M551": False, "M555": True}

        normalized = self.mapping_config.map_raw_telemetry(
            raw_registers=raw_registers,
            raw_bits=raw_bits,
            connection_state=ConnectionState.CONNECTED,
            scan_time_ms=12.5,
        )

        self.assertTrue(normalized.connected)
        self.assertEqual(normalized.speed, 42.5)
        self.assertEqual(normalized.speed_setpoint, 45.0)
        self.assertEqual(normalized.production_counter, 1284)
        self.assertEqual(normalized.daily_target, 1000)
        self.assertTrue(normalized.stations["conv1_station1"])
        self.assertFalse(normalized.stations["conv1_station2"])
        self.assertTrue(normalized.stations["conv2_station1"])

    def test_to_dict_matches_specification(self) -> None:
        raw_registers = {"D450": 42.5, "D451": 45.0, "D452": 1284, "D453": 1000}
        raw_bits = {"M550": True, "M551": True, "M555": False}

        normalized = self.mapping_config.map_raw_telemetry(
            raw_registers=raw_registers,
            raw_bits=raw_bits,
            connection_state=ConnectionState.CONNECTED,
        )
        data_dict = normalized.to_dict()

        self.assertIn("timestamp", data_dict)
        self.assertIn("connected", data_dict)
        self.assertIn("speed", data_dict)
        self.assertIn("speed_setpoint", data_dict)
        self.assertIn("production_counter", data_dict)
        self.assertIn("daily_target", data_dict)
        self.assertIn("stations", data_dict)
        self.assertEqual(data_dict["speed"], 42.5)
        self.assertEqual(data_dict["production_counter"], 1284)

    def test_missing_required_register_raises_error(self) -> None:
        invalid_mapping = {
            "registers": {
                "speed": {"address": "D450"},
                # missing speed_setpoint, production_counter, daily_target
            },
            "stations": {},
        }
        with self.assertRaises(KeyError):
            PLCMappingConfig(invalid_mapping)


if __name__ == "__main__":
    unittest.main()
