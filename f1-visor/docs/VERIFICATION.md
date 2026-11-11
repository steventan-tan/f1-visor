# Verification record

Repository preparation: **2026-11-11**. Local host: macOS ARM64, Python 3.9.6, PyTorch 2.8.0, torchvision 0.23.0. Python 3.11 is the recommended installation baseline and the configured GitHub Actions version; the hosted Actions run is not claimed to have occurred locally.

## Completed software checks

- **20 Python tests passed**, including timing/cooldown resets, serial byte filtering, actuator mutual exclusion and neutral cleanup, lock release, invalid configuration, RGB padding, metadata/hash validation, duplicate/corrupt image handling, threshold selection and mocked controller startup/inference failure cleanup.
- The integration test generated temporary synthetic data, trained EfficientNet-B0 for two CPU epochs (including backbone unfreezing), wrote the best checkpoint, per-image predictions and metrics, exported FP32 TorchScript, reloaded it and performed image inference through the public CLI. The full test configuration also renders the saved run's evaluation report and checks it against training metrics. This validates the code path, not classification quality.
- Collector tests use synthetic image bytes and mocked HTTP/DNS responses: strict JSON parsing, private-address/redirect rejection, content/size limits, format preservation, deduplication and resume after failure. They do not contact Google, Bing or image hosts.
- Evaluation tests cover exact saved-threshold metrics, PR/ROC/report generation, PNG readability, safe hard-example paths and overwrite refusal. Desktop tests cover reproducible folder selection, unannotated snapshots and camera cleanup after a save error, using a mocked camera.
- The actuator test also covers a manual movement finishing between the visual decision and actuator lock: stale visual requests are rejected, while fresh visual requests and manual presses remain available. Original-file compatibility entrypoints and all workflow notebook cells were syntax/CLI checked after migration.
- The Arduino sketch passed a host-side C++ assertion harness for bounce filtering, one event per press, no repeated event while held and no event when the button is held at boot. This is a logic check with stubs, separate from an AVR build or an on-device test.
- Python files passed bytecode compilation.
- The original FP32 model was loaded and produced finite two-class output. The original state dictionary was re-exported through the new script and compared with the supplied FP32 export on the same test input.

## Prototype evidence and scope

The original portfolio and linked video document physical prototype work. The project author explicitly confirmed that the Arduino button/Bluetooth interaction had been validated. The reference firmware implements that protocol with one command per press. The rewritten combined controller's camera/serial reconnect behavior and calibrated motion still need regression testing on the assembled hardware.

No Raspberry Pi, camera, Bluetooth radio or servo was connected during repository preparation. No live Edge/Bing search or bulk image download, new full-dataset training run, measured recognition score, Raspberry Pi benchmark, AVR board compilation or physical actuator test was performed here. Historical notebook scores in `HISTORY.md` are explicitly separate from these tests. Arduino target compilation and Python checks are configured in `.github/workflows/checks.yml`; inspect their real status after upload.

## Run again

```bash
python -m pip install -r requirements-analysis.txt -r requirements-collect.txt
python -m unittest discover -s tests -v
python -m compileall -q f1visor detect.py detect_video.py train.py prepare_data.py export_model.py servo_test.py collect_images.py evaluation_plots.py
c++ -std=c++11 tests/nano_button_test.cpp -o /tmp/nano-test
/tmp/nano-test
```

Without optional analysis/collection dependencies, the relevant tests report a skip. The local Apple system Python also emitted a Requests/LibreSSL compatibility warning; these mocked HTTP checks do not validate that SSL stack. Use the recommended Python 3.11 environment with a supported OpenSSL build for actual downloads.

For an actual Nano build, install Arduino CLI and the AVR core, then run:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:nano firmware/nano_button
```

Before a hardware demonstration, confirm motor neutral/direction, manual and automatic triggers, held-button behavior, camera loss, Bluetooth loss, Ctrl+C/service stop and restart. Refer to [HARDWARE.md](HARDWARE.md) for the expected behavior and physical limitations.
