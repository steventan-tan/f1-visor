# Hardware and Raspberry Pi deployment

## Prototype topology

The original project documents a Raspberry Pi Zero 2 W, a CSI camera, a continuous-rotation 360° servo, a film spool mechanism, a classic Arduino Nano and an HC-06 Bluetooth serial module. Training runs on a computer; the Pi performs inference and receives manual commands. The author has confirmed the manual button/Bluetooth interaction on the prototype.

This guide targets a **64-bit Raspberry Pi OS installation with Python 3.11 and the pigpio backend**. Package availability depends on OS and CPU architecture. Do not assume desktop PyTorch wheels work on 32-bit Pi OS. The small memory budget of Zero 2 W also requires measuring memory and latency on the actual board. The pigpio deployment is not a Pi 5 compatibility claim.

## Connections

| Component | Connection used by the reference code |
| --- | --- |
| Pi CSI camera | Pi camera connector; use the correct Zero camera cable |
| Servo signal | BCM13, physical header pin 33; configurable |
| Servo supply | Regulated supply sized for the servo's load and stall current |
| Servo ground | Common ground with the Pi and servo supply |
| Nano button | D2 to GND, internal pull-up enabled |
| Nano D1 / TX | HC-06 RX through suitable 5 V → 3.3 V level shifting |
| HC-06 TX | Nano D0 / RX, check the module's signal specifications |
| Nano / HC-06 ground | Common ground |
| HC-06 power | Follow the exact breakout's voltage specification |

Do not power the motor from a GPIO signal pin. The bare HC-06 radio and breakouts can have different supply arrangements; inspect the actual module. Disconnect the Bluetooth TX/RX wires while uploading via the Nano USB port, then reconnect. The sketch uses hardware UART pins D0/D1 as in the portfolio; it does not use SoftwareSerial.

`servo_neutral=0.0` is only the starting calibration for a continuous-rotation servo. A positional servo interprets these values as angles, so it is not interchangeable without changing the control strategy. Calibrate neutral, direction, pulse width and time with the film load removed. There is no encoder, end-stop or jam detection in this version.

## Install on the Pi

From the repository root on the Pi:

```bash
sudo apt update
sudo apt install python3-venv python3-picamera2 python3-gpiozero python3-pigpio pigpio python3-numpy python3-pil bluez
sudo systemctl enable --now bluetooth pigpiod
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-pi.txt
python -c "import torch, numpy, PIL, picamera2, gpiozero, serial; print(torch.__version__)"
```

Picamera2 and its native camera libraries come from the OS. `--system-site-packages` exposes them to the virtual environment, and the Pi requirements deliberately reuse apt NumPy/Pillow. If apt does not provide `pigpio` or PyTorch reports no compatible distribution, resolve the OS / architecture mismatch before continuing; do not silently install a different backend. See [PyTorch's official version matrix](https://pytorch.org/get-started/previous-versions/).

Copy a trusted `visor_fp32.pt` and its matching `visor_fp32.json` into `models/`. Run image inference first to verify that the model loads on the board:

```bash
python detect_video.py --image path/to/bench-test.jpg
cp config.example.json config.local.json
```

Edit `config.local.json`. Paths inside it resolve relative to the configuration file; hardware settings never need to be edited in Python. Threshold and image size are read from model metadata. Re-evaluate the model if either is changed.

## Pair and bind Bluetooth

On the Pi, use `bluetoothctl` interactively:

```text
power on
agent on
default-agent
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
scan off
quit
```

Replace the example address with the address actually discovered, and enter your module's configured PIN when prompted. The HC-06 exposes a Bluetooth Classic serial link; the Pi is the connecting host. It is not a BLE characteristic protocol.

```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
sudo usermod -aG dialout,video,gpio "$(id -un)"
```

Log out and back in after changing groups. The reference channel is `1`; check the module's SPP service if it differs. Keep the module at 9600 baud or update both the sketch and configuration. Pairing persists; the bind command above is for a manual session. The service below restores the binding after reboot. Python reopens the serial port with bounded backoff; it does not invoke `sudo` or change system pairing.

## Calibrate and run

```bash
python servo_test.py --config config.local.json --run
python detect.py --config config.local.json
```

Check that neutral actually stops the motor. An `S` or `s` from a button press triggers a movement immediately when idle. Holding the button does not repeat. Vision requires consecutive positive observations for `hold_seconds`; any clean result or camera failure resets that timer. Manual and visual inputs share the actuator lock. Commands received while it moves are discarded; the vision timer restarts after movement and cooldown. A manual press bypasses the vision threshold/cooldown but cannot interrupt an ongoing movement. The shared actuator also rejects an automatic decision whose detection interval predates a newer manual movement, including a movement that completes just before the actuator lock is acquired.

Ctrl+C or SIGTERM requests shutdown, interrupts the timed movement, commands neutral and closes resources. A lock prevents two instances under the same account and configuration. Run the calibration script and service as the same account so they use the same lock. SIGKILL, power loss or a jam cannot be made safe by a Python `finally` block; provide an accessible physical power disconnect on the bench.

## Start on boot (optional)

The templates assume a repository at `/opt/f1-visor`. Place the project there under the intended user's ownership, create its virtual environment there using the commands above, and copy the model pair and local configuration into that installation. Do not move an existing virtual environment from another path or machine.

```bash
sudo install -d -m 755 /etc/f1-visor
sudo install -m 600 deploy/bluetooth.env.example /etc/f1-visor/bluetooth.env
sudoedit /etc/f1-visor/bluetooth.env
# Set the real BT_MAC and BT_CHANNEL in this file.
sudo install -m 644 deploy/f1-rfcomm.service /etc/systemd/system/f1-rfcomm.service
sudo install -m 644 deploy/f1-visor.service /etc/systemd/system/f1-visor.service
sudoedit /etc/systemd/system/f1-visor.service
# Change User/Group to the installation owner; adjust all paths if necessary.
sudo systemctl daemon-reload
sudo systemctl enable --now f1-rfcomm.service f1-visor.service
journalctl -u f1-visor.service -f
```

Stop the service before calibration: `sudo systemctl stop f1-visor`. Model or inference errors exit nonzero for systemd restart; camera and serial disconnections retry. Verify startup, repeated button presses, camera disconnect/reconnect, Bluetooth disconnect/reconnect and service stop on the assembled prototype.

## Technical references

- [Picamera2 documentation and channel order](https://github.com/raspberrypi/picamera2/blob/main/picamera2/request.py): `BGR888` is interpreted as RGB data by the array-to-image path. The controller requests that format to match training.
- [gpiozero Servo API](https://gpiozero.readthedocs.io/en/stable/api_output.html#servo): pulse widths, initial value and BCM numbering.
- [Arduino debounce example](https://docs.arduino.cc/built-in-examples/digital/Debounce/): stable button-state detection.
