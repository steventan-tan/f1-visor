#!/usr/bin/env python3
"""Calibrate a continuous-rotation servo using the deployment configuration."""
import argparse
import signal
from pathlib import Path
import threading
from f1visor.config import load_config
from f1visor.control import ServoController, single_instance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.example.json"))
    parser.add_argument("--run", action="store_true", help="Explicitly enable physical movement")
    args = parser.parse_args()
    config = load_config(args.config)
    if not args.run:
        parser.error("Remove the film load and pass --run to enable movement")
    from gpiozero import Servo
    from gpiozero.pins.pigpio import PiGPIOFactory
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    with single_instance(config["lock_path"]):
        factory = PiGPIOFactory()
        try:
            with Servo(config["servo_gpio"], initial_value=config["servo_neutral"], pin_factory=factory,
                       min_pulse_width=config["min_pulse_width"], max_pulse_width=config["max_pulse_width"]) as servo:
                controller = ServoController(servo, stop, config["servo_seconds"],
                                             config["servo_neutral"], config["servo_speed"])
                try:
                    controller.run()
                finally:
                    servo.value = config["servo_neutral"]
        finally:
            factory.close()


if __name__ == "__main__":
    main()
