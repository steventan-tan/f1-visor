"""Failure-path checks without opening a camera, GPIO or serial device."""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import detect


class RuntimeTests(unittest.TestCase):
    def test_startup_and_inference_failures_release_resources(self):
        for failure in ("load", "infer"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / "config.json"
                config.write_text(json.dumps({"lock_path": str(Path(directory) / "lock")}))
                gpio = types.ModuleType("gpiozero")
                gpio.Servo = MagicMock()
                pigpio = types.ModuleType("gpiozero.pins.pigpio")
                pigpio.PiGPIOFactory = MagicMock()
                camera = MagicMock()
                import numpy as np
                camera.capture_array.return_value = np.zeros((32, 32, 3), dtype=np.uint8)
                predictor = MagicMock()
                predictor.meta = {"threshold": .4, "image_size": 32}
                predictor.predict.side_effect = ValueError("inference failed")
                with patch.dict("sys.modules", {"gpiozero": gpio, "gpiozero.pins.pigpio": pigpio}), \
                     patch("sys.argv", ["detect.py", "--config", str(config)]), \
                     patch("f1visor.vision.Predictor", return_value=predictor) as factory, \
                     patch.object(detect, "open_camera", return_value=camera), \
                     patch.object(detect, "bluetooth_loop"):
                    if failure == "load":
                        factory.side_effect = ValueError("bad model")
                    with self.assertRaises(ValueError):
                        detect.main()
                if failure == "load":
                    gpio.Servo.assert_not_called()
                else:
                    camera.close.assert_called_once()
                    self.assertEqual(gpio.Servo.return_value.value, 0)
                    gpio.Servo.return_value.close.assert_called_once()
                    pigpio.PiGPIOFactory.return_value.close.assert_called_once()
                # A failure must not leave the single-instance lock held.
                with detect.single_instance(Path(directory) / "lock"):
                    pass


if __name__ == "__main__":
    unittest.main()
