import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from f1visor.control import DetectionGate, ServoController, is_manual_trigger, single_instance


class ControlTests(unittest.TestCase):
    def test_hold_reset_and_cooldown(self):
        gate = DetectionGate(0.4, 3, 2)
        self.assertFalse(gate.update(0.5, 0))
        self.assertFalse(gate.update(0.3, 2))
        self.assertFalse(gate.update(0.5, 3))
        self.assertTrue(gate.update(0.4, 6))
        gate.actuated(6)
        self.assertFalse(gate.update(1, 7))
        self.assertFalse(gate.update(1, 8))
        self.assertTrue(gate.update(1, 11))
        gate.reset()
        self.assertFalse(gate.update(1, 20))

    def test_invalid_prediction_clears_timer(self):
        gate = DetectionGate(0.4, 3, 2)
        gate.update(1, 0)
        with self.assertRaises(ValueError):
            gate.update(float('nan'), 3)
        self.assertFalse(gate.update(1, 4))

    def test_only_expected_serial_bytes_trigger(self):
        for value in (b'S', b's'):
            self.assertTrue(is_manual_trigger(value))
        for value in (b'', b'\xff', b'\n', b'STOP'):
            self.assertFalse(is_manual_trigger(value))

    def test_servo_stop_failure_and_busy(self):
        class Servo:
            value = 0
        servo, stop = Servo(), threading.Event()
        controller = ServoController(servo, stop, 0.001, 0.1, 1)
        self.assertTrue(controller.run())
        self.assertEqual(servo.value, 0.1)
        with controller.lock:
            self.assertFalse(controller.run())
        stop.set()
        self.assertFalse(controller.run())
        stop.clear()
        def fail_wait(_):
            raise OSError('interrupted')
        stop.wait = fail_wait
        with self.assertRaises(OSError):
            controller.run()
        self.assertEqual(servo.value, 0.1)
        self.assertFalse(controller.lock.locked())

    def test_lock_released_after_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'controller.lock'
            with self.assertRaises(ValueError):
                with single_instance(path):
                    with self.assertRaises(RuntimeError):
                        with single_instance(path):
                            pass
                    raise ValueError('test')
            with single_instance(path):
                pass

    def test_manual_motion_invalidates_pending_visual_decision(self):
        class Servo:
            value = 0
        servo = Servo()
        controller = ServoController(servo, threading.Event(), 0.001, 0, 1)
        # Manual motion finishes between the camera's gate check and actuator lock.
        with patch('f1visor.control.time.monotonic', return_value=10):
            self.assertTrue(controller.run())
        self.assertFalse(controller.run(automatic_since=7))
        self.assertFalse(controller.run(automatic_since=10))
        self.assertEqual(controller.last_finished, 10)
        self.assertEqual(servo.value, 0)
        with patch('f1visor.control.time.monotonic', return_value=15):
            self.assertTrue(controller.run(automatic_since=11))
        self.assertTrue(controller.run())


if __name__ == '__main__':
    unittest.main()
