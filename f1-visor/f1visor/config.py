"""Validated local hardware configuration; paths resolve beside the JSON file."""
import json
import math
from pathlib import Path

DEFAULTS = {
    "model": "models/visor_fp32.pt",
    "serial_port": "/dev/rfcomm0",
    "baud": 9600,
    "servo_gpio": 13,
    "servo_seconds": 3.0,
    "servo_neutral": 0.0,
    "servo_speed": 1.0,
    "min_pulse_width": 0.0005,
    "max_pulse_width": 0.0025,
    "hold_seconds": 3.0,
    "cooldown_seconds": 3.0,
    "lock_path": "~/.cache/f1-visor/controller.lock",
}


def load_config(path):
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.keys() - DEFAULTS.keys():
        raise ValueError("Config must be an object with only documented keys")
    values = {**DEFAULTS, **raw}
    for key in ("baud", "servo_gpio"):
        if type(values[key]) is not int:
            raise ValueError(f"{key} must be an integer")
    if values["baud"] <= 0 or not 0 <= values["servo_gpio"] <= 27:
        raise ValueError("Invalid baud rate or BCM GPIO")
    for key in ("servo_seconds", "min_pulse_width", "max_pulse_width", "hold_seconds", "cooldown_seconds"):
        v = values[key]
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"{key} must be positive and finite")
    if not values["min_pulse_width"] < values["max_pulse_width"] < 0.02:
        raise ValueError("Pulse widths must satisfy min < max < 0.02 seconds")
    for key in ("servo_neutral", "servo_speed"):
        v = values[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1:
            raise ValueError(f"{key} must be in [-1, 1]")
    if values["servo_neutral"] == values["servo_speed"]:
        raise ValueError("servo_speed must differ from servo_neutral")
    for key in ("model", "lock_path", "serial_port"):
        if not isinstance(values[key], str) or not values[key].strip():
            raise ValueError(f"{key} must be a nonempty path")
    for key in ("model", "lock_path"):
        values[key] = str((path.parent / Path(values[key]).expanduser()).resolve())
    return values
