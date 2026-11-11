# Model card

## Intended use

Binary whole-image classification for a bench prototype of a visor film-changing device. Output column 1 is interpreted as `stain`; column 0 as `clean`. This is not object detection, stain segmentation, a calibrated risk score or an autonomous driving model.

## Architecture and inputs

EfficientNet-B0 features → adaptive average pool → flatten → dropout (0.5) → linear (1280 to 2). RGB images are resized with gray padding and ImageNet normalization. The original notebook trained at 384 pixels; original deployment scripts requested 224 pixels. The reorganized pipeline stores and preserves the size used for each new experiment.

## Supplied artifacts inspected

| Original file | Finding on the repository-preparation computer |
| --- | --- |
| `best_safe.pt` | 360-entry state dictionary; loads with `weights_only=True`, fits the reconstructed original architecture and can be re-exported |
| `deploy_exports/model_fp32_simple.pt` | Loads and produces finite `[1, 2]` logits on a 224-pixel test input |
| `model_script_fp32.pt` | Fails with an unavailable `prim::ConstantMKLDNNTensor` operator |
| `model_dynamic_int8.pt` | Fails with `Unknown qengine` |
| `deploy_exports/model_dynamic_int8_simple.pt` | Fails with `Unknown qengine` |

Failures above describe this host and its PyTorch build; they do not prove universal artifact corruption. The public code uses the portable FP32 export path. A successfully loaded model has not thereby demonstrated recognition quality.

The local `models/visor_fp32.pt` is an unchanged copy of `deploy_exports/model_fp32_simple.pt`. Its sidecar records the file's hash. `clean=0, stain=1` follows the original inference code and is also present in the subsequently supplied training logs. However, this particular checkpoint has not been linked to a logged run. `0.4` is the original manual deployment setting, not one of the recovered validation thresholds. These assumptions must be checked against labeled images before a new deployment.

## Training data, scores and provenance

The additional notebooks recover acquisition code, class counts and saved historical scores; see [HISTORY.md](HISTORY.md). The v3 log reports 289 images and a thresholded test accuracy of 93.33% on 45 images, separate from its argmax accuracy of 95.56%. These are historical notebook outputs, not independently reproduced scores for the supplied deployment checkpoint. Raw images, split membership and per-image historical predictions are still absent. The v3 training loop does not save the `best_safe.pt` file later loaded by the earlier export notebook, so that checkpoint cannot be linked to a specific run from the available files. No Raspberry Pi latency is asserted.

New runs write the missing metadata and metrics. The initial `0.98` recall value is a selection target. Synthetic integration-test results are never published as real evaluation scores. Future releases should include a data provenance statement, capture-session-aware split description and held-out evaluation at the actual deployment resolution.

## Distribution and limits

Weights and datasets are excluded from the source archive and Git. Use your own trained pair, or obtain separately licensed artifacts from the author. Only load trusted checkpoints and TorchScript files: matching a sidecar digest detects accidental mismatches, not malicious model code.

There is no evidence of robustness to all rain, mud, glare, vibration or camera changes. Time-based actuation cannot detect a jam, film exhaustion or partial advance. The manual path shares the Pi, power and motor with the automatic path. These limits are part of the prototype's scope.
