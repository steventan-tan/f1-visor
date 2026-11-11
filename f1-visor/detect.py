#!/usr/bin/env python3
"""Raspberry Pi camera + Bluetooth receiver + continuous-rotation servo."""
import argparse
import logging
import signal
import threading
import time
from contextlib import ExitStack
from pathlib import Path

from f1visor.config import load_config
from f1visor.control import DetectionGate, ServoController, is_manual_trigger, single_instance

LOG = logging.getLogger("f1visor")


def bluetooth_loop(config, controller, stop):
    import serial
    backoff = 1
    while not stop.is_set():
        try:
            with serial.Serial(config["serial_port"], config["baud"], timeout=0.2) as port:
                port.reset_input_buffer()
                LOG.info("Bluetooth connected: %s", config["serial_port"])
                backoff = 1
                while not stop.is_set():
                    if is_manual_trigger(port.read(1)):
                        LOG.info("Manual trigger")
                        try:
                            controller.run()
                        except Exception as exc:
                            raise RuntimeError("Servo actuation failed") from exc
                        # Discard commands accumulated while moving: no delayed motion.
                        port.reset_input_buffer()
        except (serial.SerialException, OSError) as exc:
            LOG.warning("Bluetooth unavailable: %s; retry in %ss", exc, backoff)
            stop.wait(backoff)
            backoff = min(backoff * 2, 30)


def open_camera(size):
    from picamera2 import Picamera2
    camera = Picamera2()
    try:
        # Picamera2 BGR888 produces RGB channel order in its NumPy array.
        camera.configure(camera.create_preview_configuration(
            main={"format": "BGR888", "size": (size, size)}))
        camera.start()
        return camera
    except Exception:
        camera.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.example.json"))
    args = parser.parse_args()
    config = load_config(args.config)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from PIL import Image
    from gpiozero import Servo
    from gpiozero.pins.pigpio import PiGPIOFactory
    from f1visor.vision import Predictor

    stop = threading.Event()
    failures = []
    previous = {s: signal.signal(s, lambda *_: stop.set()) for s in (signal.SIGINT, signal.SIGTERM)}
    camera = None
    try:
        with ExitStack() as resources:
            resources.enter_context(single_instance(config["lock_path"]))
            predictor = Predictor(config["model"])
            factory = PiGPIOFactory()
            resources.callback(factory.close)
            servo = Servo(config["servo_gpio"], initial_value=config["servo_neutral"],
                          pin_factory=factory, min_pulse_width=config["min_pulse_width"],
                          max_pulse_width=config["max_pulse_width"])
            resources.callback(servo.close)
            controller = ServoController(servo, stop, config["servo_seconds"],
                                         config["servo_neutral"], config["servo_speed"])
            gate = DetectionGate(predictor.meta["threshold"], config["hold_seconds"], config["cooldown_seconds"])

            def listen():
                try:
                    bluetooth_loop(config, controller, stop)
                except Exception as exc:
                    failures.append(exc)
                    LOG.exception("Bluetooth worker failed")
                    stop.set()

            worker = threading.Thread(target=listen, name="bluetooth")
            worker.start()

            def stop_worker():
                stop.set()
                worker.join()
                servo.value = config["servo_neutral"]

            resources.callback(stop_worker)
            observed_finish = None
            log_at = 0
            try:
                while not stop.is_set():
                    if camera is None:
                        try:
                            camera = open_camera(predictor.meta["image_size"])
                        except Exception as exc:
                            LOG.warning("Camera unavailable: %s", exc)
                            gate.reset()
                            stop.wait(2)
                            continue
                    try:
                        frame = camera.capture_array()
                    except Exception as exc:
                        LOG.warning("Camera read failed: %s", exc)
                        try:
                            camera.close()
                        finally:
                            camera = None
                            gate.reset()
                        stop.wait(1)
                        continue
                    probability = predictor.predict(Image.fromarray(frame))
                    now = time.monotonic()
                    if controller.last_finished != observed_finish:
                        observed_finish = controller.last_finished
                        gate.actuated(observed_finish)
                    if controller.lock.locked():
                        gate.reset()
                    elif gate.update(probability, now):
                        if controller.run(automatic_since=gate.since):
                            LOG.info("Visual servo pulse completed: p(stain)=%.3f", probability)
                            gate.actuated(controller.last_finished)
                        else:
                            gate.reset()
                    if now >= log_at:
                        LOG.info("p(stain)=%.3f threshold=%.3f", probability, gate.threshold)
                        log_at = now + 1
                    stop.wait(0.05)
            finally:
                stop.set()
                if camera is not None:
                    camera.close()
        if failures:
            raise RuntimeError("Bluetooth worker failed") from failures[0]
    finally:
        stop.set()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    main()
