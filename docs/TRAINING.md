# Training and experiment reproduction

## Data contract

```text
data/raw/
├── clean/   # Unobstructed view
└── stain/   # View obstructed by the project's target dirt/water conditions
```

These are the exact names and order: `clean=0`, `stain=1`. Use at least seven unique images per class for the split utility to allocate all three subsets. That minimum is for tool operation, not an adequate research dataset. Formats: JPEG, PNG, BMP and WebP. Corrupt files and byte-identical duplicates are rejected before copying. Existing outputs are never overwritten.

The raw original dataset remains unavailable. The subsequently supplied collection notebook is now integrated as `collect_images.py`; see [collection and labeling](COLLECTION.md). Obtain permission for your images and record their source, capture setup and license. A search keyword does not assign a class or establish redistribution rights.

`prepare_data.py` produces a seeded 70/15/15 split, rounded per class, plus a checksum manifest. It prevents identical-image leakage, **not near-duplicate or scene leakage**. If the source contains adjacent video frames, repeated backgrounds or the same capture session, manually assign whole sessions to `train/`, `val/` and `test/` first. Training accepts that same folder structure and checks for exact duplicates across splits. Evaluate on sessions, lighting and obstruction types that were not used for tuning.

## Pipeline

```bash
python prepare_data.py --source data/raw --output data/split --seed 42
python train.py --data data/split --output runs/experiment-01
python export_model.py --checkpoint runs/experiment-01/best.pt --output models/visor_fp32.pt
```

Training retains the original EfficientNet-B0 backbone + adaptive average pool + dropout (0.5) + two-output linear head. Defaults are 384-pixel inputs, batch size 32, 40 epochs, AdamW, an initial 5-epoch frozen backbone, cosine scheduling, class-weighted loss and early stopping after 7 unimproved validation losses. CUDA uses AMP; CPU does not. A fixed seed improves repeatability but is not a promise of identical results across devices or library versions.

Images are converted to RGB, resized proportionally and padded with `(123,123,123)`. Training adds spatial and color augmentation. Evaluation and deployment use the same deterministic padding and ImageNet normalization. Training no longer replaces corrupt images with gray images carrying the original label.

The best **validation-loss** checkpoint is restored. Among thresholds attaining the requested validation recall, the largest observed feasible threshold is selected; the default target is `0.98`. Test-set labels do not influence the selected checkpoint or threshold. That recall target does not guarantee test performance, and high recall can increase false activations.

## Outputs

| File | Meaning |
| --- | --- |
| `best.pt` | Best checkpoint's state dictionary |
| `best.json` | Class order, input size, selected threshold and preprocessing contract |
| `history.csv` | Per-epoch training/validation losses and argmax accuracies |
| `metrics.json` | Validation/test confusion matrices, precision, recall, F1, accuracy and settings |
| `predictions.csv` | Per-image validation/test labels, probabilities and paths relative to the split root |
| Exported `.pt` + `.json` | Reload-checked TorchScript model and matching SHA-256 metadata |

The exporter preserves the checkpoint's image size and threshold. It does not use CPU-specific inference optimization or speculative quantization. The new pair must be copied together. To reduce input size for a Pi, train/evaluate an experiment at that size and compare held-out results before use; do not simply reuse a threshold calibrated at another resolution.

```bash
python train.py --data data/split --output runs/224px --image-size 224
python export_model.py --checkpoint runs/224px/best.pt --output models/visor_224.pt
```

For an offline pipeline smoke test, use `--weights none --epochs 2 --freeze-epochs 1 --image-size 64 --batch-size 4`. This trains from random initialization, so its accuracy is not meaningful. The automated test creates temporary synthetic images and uses this exact approach.

## Evaluation plots

```bash
python -m pip install -r requirements-analysis.txt
python evaluation_plots.py --run runs/experiment-01 --data data/split
```

The command writes `figures/learning_curves.png`, `evaluation.png`, `report.json` and `hard_examples.csv`. With `--data`, it also writes `hard_examples.png`. It uses the saved validation threshold exactly, never tunes on test data, rejects incomplete predictions and refuses to overwrite an existing report directory. Use `--output` to choose a new directory. Without original image files, omit `--data` to retain all numerical plots and the hard-example list.

Runs from the earlier repository version lack `predictions.csv`; they need a new run or the original per-image predictions before PR/ROC can be drawn. Summary accuracy/confusion matrices cannot reconstruct these curves. Historical Notebook outputs are documented separately in [HISTORY.md](HISTORY.md).

Metrics use [scikit-learn precision-recall](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_curve.html) and [ROC](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_curve.html) implementations. The threshold marker is computed from exact classifications, not the nearest sampled curve point.

## Notebook and evidence

```bash
python -m pip install -r requirements-notebook.txt
jupyter lab notebooks/experiment.ipynb
```

The notebook reads real training outputs and renders the loss history and test confusion matrix; it contains no prefilled scores. In a portfolio, report the dataset source and counts, split method, capture conditions, image size, chosen threshold, false positives/negatives and the device used for timing. The author keeps a local pre-edit source archive; original filenames now open the unified workflows. Use `notebooks/training.ipynb` for an executable staged training workflow or `notebooks/collection.ipynb` for acquisition. Repeated model definitions from the old notebooks are not maintained.
