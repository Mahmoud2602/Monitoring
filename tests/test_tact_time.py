"""
Unit tests for Tact Time calculation and Engineering Unit Scaling.
"""
import unittest

from kpi.tact_time import SpeedScalingConfig, TactTimeCalculator


class TestTactTimeModule(unittest.TestCase):
    def test_raw_to_engineering_scaling(self) -> None:
        # Example from prompt: Raw D450 = 425, Scale = 0.1 -> 42.5 m/min
        cfg = SpeedScalingConfig(
            raw_address="D450",
            scale_factor=0.1,
            engineering_unit="m/min",
            product_pitch_meters=0.75,
        )
        eng_val = cfg.raw_to_engineering(425)
        self.assertAlmostEqual(eng_val, 42.5, places=2)

    def test_unit_conversions_to_mps(self) -> None:
        calc = TactTimeCalculator()
        # 60 m/min = 1.0 m/s
        self.assertAlmostEqual(calc.speed_to_meters_per_second(60.0, "m/min"), 1.0, places=3)
        # 2.5 m/s = 2.5 m/s
        self.assertAlmostEqual(calc.speed_to_meters_per_second(2.5, "m/s"), 2.5, places=3)
        # 1500 mm/s = 1.5 m/s
        self.assertAlmostEqual(calc.speed_to_meters_per_second(1500.0, "mm/s"), 1.5, places=3)

    def test_tact_time_and_target_rate_symmetry(self) -> None:
        # 100 pcs/hr should equate to 36 seconds tact time
        tact_time = TactTimeCalculator.calculate_tact_time_from_target_rate(100.0)
        self.assertEqual(tact_time, 36.0)

        rate = TactTimeCalculator.calculate_target_rate_from_tact_time(36.0)
        self.assertEqual(rate, 100.0)

    def test_process_raw_register_pipeline(self) -> None:
        cfg = SpeedScalingConfig(
            raw_address="D450",
            scale_factor=0.1,
            engineering_unit="m/min",
            product_pitch_meters=0.75,
        )
        calc = TactTimeCalculator(cfg)
        result = calc.process_raw_register(450)

        self.assertEqual(result["raw_value"], 450)
        self.assertEqual(result["scale"], 0.1)
        self.assertEqual(result["engineering_value"], 45.0)
        self.assertEqual(result["engineering_unit"], "m/min")
        self.assertEqual(result["tact_time_seconds"], 1.0)
        self.assertEqual(result["derived_target_rate"], 3600.0)


if __name__ == "__main__":
    unittest.main()
