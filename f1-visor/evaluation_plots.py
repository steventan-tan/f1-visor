#!/usr/bin/env python3
"""Render learning curves, held-out evaluation and hard examples from a saved run."""
import argparse
import csv
import json
import math
from pathlib import Path


def load_test_predictions(run):
    run = Path(run)
    metadata = json.loads((run / "best.json").read_text())
    threshold = metadata.get("threshold")
    if metadata.get("classes") != ["clean", "stain"]:
        raise ValueError("Expected clean=0, stain=1")
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid saved validation threshold")
    records, seen = [], set()
    with (run / "predictions.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["split"] != "test":
                continue
            label, probability = int(row["label"]), float(row["stain_probability"])
            if label not in (0, 1) or not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Invalid test label or probability")
            if row["path"] in seen:
                raise ValueError("Duplicate test image path")
            seen.add(row["path"])
            records.append({"path": row["path"], "label": label, "stain_probability": probability})
    if {r["label"] for r in records} != {0, 1}:
        raise ValueError("Evaluation plots require test samples from both classes")
    return records, threshold


def render_report(run, output, data_root=None):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import (precision_recall_curve, average_precision_score, roc_curve,
                                 roc_auc_score, confusion_matrix, classification_report)
    records, threshold = load_test_predictions(run)
    with (Path(run) / "history.csv").open(newline="") as handle:
        history = list(csv.DictReader(handle))
    if not history:
        raise ValueError("Training history is empty")
    output = Path(output)
    if output.exists():
        raise FileExistsError("Report directory exists; choose a new output directory")
    # Validate image paths before creating output or reading any supplied images.
    paths = []
    if data_root is not None:
        root = Path(data_root).resolve()
        for record in records:
            path = (root / record["path"]).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError("Prediction path is missing or outside --data")
            paths.append(path)
    y = np.array([r["label"] for r in records])
    p = np.array([r["stain_probability"] for r in records])
    predicted = (p >= threshold).astype(int)
    report = classification_report(y, predicted, labels=[0, 1], target_names=["clean", "stain"],
                                   output_dict=True, zero_division=0)
    report.update(threshold=threshold, average_precision=float(average_precision_score(y, p)),
                  roc_auc=float(roc_auc_score(y, p)), samples=len(records))
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(report, indent=2))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    epochs = [int(row["epoch"]) for row in history]
    for key in ("train_loss", "val_loss"):
        axes[0].plot(epochs, [float(row[key]) for row in history], label=key)
    axes[0].set(xlabel="Epoch", ylabel="Loss", title="Learning curve")
    axes[0].legend()
    if {"train_accuracy", "val_accuracy"} <= history[0].keys():
        for key in ("train_accuracy", "val_accuracy"):
            axes[1].plot(epochs, [float(row[key]) for row in history], label=key)
        axes[1].legend()
    else:
        axes[1].text(.1, .5, "Accuracy not recorded in this older run")
    axes[1].set(xlabel="Epoch", ylabel="Argmax accuracy", ylim=(0, 1), title="Training / validation accuracy")
    fig.savefig(output / "learning_curves.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
    precision, recall, _ = precision_recall_curve(y, p)
    axes[0, 0].step(recall, precision, where="post", label=f"AP={report['average_precision']:.3f}")
    # Plot the exact saved threshold's metrics, not a nearby PR-curve threshold.
    axes[0, 0].scatter(report["stain"]["recall"], report["stain"]["precision"], color="red",
                       label=f"validation threshold={threshold:.4f}")
    axes[0, 0].set(xlabel="Recall", ylabel="Precision", title="Test precision-recall", xlim=(0, 1), ylim=(0, 1.05))
    axes[0, 0].legend(fontsize=8)
    fpr, tpr, _ = roc_curve(y, p)
    axes[0, 1].plot(fpr, tpr, label=f"AUC={report['roc_auc']:.3f}")
    axes[0, 1].plot([0, 1], [0, 1], "--", color="gray")
    axes[0, 1].set(xlabel="False positive rate", ylabel="True positive rate", title="Test ROC")
    axes[0, 1].legend()
    cm = confusion_matrix(y, predicted, labels=[0, 1])
    for ax, values, title in ((axes[0, 2], cm, "Confusion matrix"),
                              (axes[1, 0], cm / cm.sum(axis=1, keepdims=True), "Normalized confusion matrix")):
        maximum = 1.0 if values.dtype.kind == "f" else max(1, int(values.max()))
        ax.imshow(values, cmap="Blues", vmin=0, vmax=maximum)
        for row in range(2):
            for col in range(2):
                value = values[row, col]
                ax.text(col, row, f"{value:.2f}" if values.dtype.kind == "f" else str(value),
                        ha="center", va="center", color="white" if value > maximum / 2 else "black")
        ax.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["clean", "stain"], yticklabels=["clean", "stain"],
               xlabel="Predicted", ylabel="Actual", title=title)
    for label, name in enumerate(("clean", "stain")):
        axes[1, 1].hist(p[y == label], bins=np.linspace(0, 1, 21), alpha=.6, label=name)
    axes[1, 1].axvline(threshold, linestyle="--", color="black")
    axes[1, 1].set(xlabel="p(stain)", ylabel="Samples", title="Test probability distribution")
    axes[1, 1].legend()
    axes[1, 2].axis("off")
    axes[1, 2].text(.05, .9, f"Held-out test: {len(y)} images\n\nAccuracy: {report['accuracy']:.4f}\n"
                           f"Stain precision: {report['stain']['precision']:.4f}\n"
                           f"Stain recall: {report['stain']['recall']:.4f}\n"
                           f"Stain F1: {report['stain']['f1-score']:.4f}\n\n"
                           "Threshold selected on validation.\nNo test-set threshold tuning.", va="top")
    fig.savefig(output / "evaluation.png", dpi=160)
    plt.close(fig)
    errors = np.flatnonzero(predicted != y).tolist()
    nearest = np.argsort(np.abs(p - threshold), kind="stable").tolist()
    selected = list(dict.fromkeys(errors[:5] + nearest))[:10]
    with (output / "hard_examples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("path", "label", "stain_probability", "prediction", "is_error"))
        writer.writeheader()
        for index in selected:
            writer.writerow({**records[index], "prediction": int(predicted[index]), "is_error": bool(y[index] != predicted[index])})
    if paths:
        from PIL import Image
        fig, axes = plt.subplots(2, 5, figsize=(15, 6), constrained_layout=True)
        for ax in axes.flat:
            ax.axis("off")
        for ax, index in zip(axes.flat, selected):
            with Image.open(paths[index]) as image:
                ax.imshow(image.convert("RGB"))
            ax.set_title(f"true={y[index]} pred={predicted[index]}\np(stain)={p[index]:.3f}", fontsize=9)
        fig.savefig(output / "hard_examples.png", dpi=160)
        plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data", type=Path, help="Original split root; enables hard-example image grid")
    args = parser.parse_args()
    output = args.output or args.run / "figures"
    render_report(args.run, output, args.data)
    print(f"Saved evaluation report to {output}")


if __name__ == "__main__":
    main()
