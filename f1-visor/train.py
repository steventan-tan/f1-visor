#!/usr/bin/env python3
"""Train on a fixed split, select threshold on validation, evaluate test once."""
import argparse
import csv
import json
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/split"))
    parser.add_argument("--output", type=Path, default=Path("runs/experiment-01"))
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--image-size", type=int, default=384)
    parser.add_argument("--freeze-epochs", type=int, default=5)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--target-recall", type=float, default=0.98)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--weights", choices=("imagenet", "none"), default="imagenet",
                        help="none is intended for an offline smoke test")
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 2 or args.patience < 1 or args.freeze_epochs < 0:
        parser.error("epochs/patience >= 1, batch-size >= 2, freeze-epochs >= 0 required")
    if not 32 <= args.image_size <= 2048 or not 0 < args.target_recall <= 1:
        parser.error("image-size must be 32..2048 and target-recall in (0, 1]")
    if args.output.exists():
        parser.error("Output already exists; choose a new experiment directory")

    import numpy as np
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision import transforms
    from torchvision.datasets import ImageFolder
    from f1visor.training import build_model, choose_threshold, evaluate, metrics
    from f1visor.vision import MEAN, STD, ResizeWithPad
    from prepare_data import validate_images

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(2)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    normalize = [transforms.ToTensor(), transforms.Normalize(MEAN, STD)]
    train_tf = transforms.Compose([ResizeWithPad(args.image_size),
        transforms.RandomResizedCrop(args.image_size, scale=(.7, 1.0)),
        transforms.ColorJitter(.2, .2, .1, .05), transforms.RandomHorizontalFlip(),
        transforms.GaussianBlur(3, sigma=(.1, 1.5)), *normalize])
    eval_tf = transforms.Compose([ResizeWithPad(args.image_size), *normalize])
    datasets = {split: ImageFolder(args.data / split, transform=train_tf if split == "train" else eval_tf)
                for split in ("train", "val", "test")}
    if any(ds.class_to_idx != {"clean": 0, "stain": 1} for ds in datasets.values()):
        raise ValueError("Every split must use clean=0, stain=1")
    validate_images({split: [Path(p) for p, _ in ds.samples] for split, ds in datasets.items()})
    # A final singleton batch fails BatchNorm at small smoke-test resolutions.
    loaders = {split: DataLoader(ds, batch_size=args.batch_size, shuffle=(split == "train"),
                                num_workers=0, drop_last=(split == "train" and len(ds) % args.batch_size == 1))
               for split, ds in datasets.items()}
    model = build_model(pretrained=args.weights == "imagenet").to(device)
    counts = torch.bincount(torch.tensor(datasets["train"].targets), minlength=2).float()
    weights = 1 / counts
    criterion = nn.CrossEntropyLoss(weight=(weights / weights.mean()).to(device))
    for p in model[0].parameters():
        p.requires_grad = args.freeze_epochs == 0
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    args.output.mkdir(parents=True)
    best_loss, stale, history = float("inf"), 0, []
    checkpoint = args.output / "best.pt"
    for epoch in range(args.epochs):
        if epoch == args.freeze_epochs and epoch > 0:
            for p in model.parameters():
                p.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs - epoch)
        model.train()
        if epoch < args.freeze_epochs:
            model[0].eval()
        total, count, correct = 0.0, 0, 0
        for x, y in loaders["train"]:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                logits = model(x)
                loss = criterion(logits, y)
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 1)
            scaler.step(optimizer)
            scaler.update()
            total += loss.item() * len(y)
            count += len(y)
            correct += (logits.argmax(1) == y).sum().item()
        val_loss, epoch_labels, epoch_probs = evaluate(model, loaders["val"], criterion, device)
        # Column zero wins argmax ties, so the positive comparison is strictly > 0.5.
        val_accuracy = sum(int(p > .5) == y for y, p in zip(epoch_labels, epoch_probs)) / len(epoch_labels)
        history.append({"epoch": epoch + 1, "train_loss": total / count, "val_loss": val_loss,
                        "train_accuracy": correct / count, "val_accuracy": val_accuracy})
        print(json.dumps(history[-1]), flush=True)
        scheduler.step()
        if val_loss < best_loss:
            best_loss, stale = val_loss, 0
            torch.save(model.state_dict(), checkpoint)
        else:
            stale += 1
        if stale >= args.patience:
            break
    model.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=True))
    _, val_labels, val_probs = evaluate(model, loaders["val"], criterion, device)
    threshold = choose_threshold(val_labels, val_probs, args.target_recall)
    _, test_labels, test_probs = evaluate(model, loaders["test"], criterion, device)
    metadata = {"classes": ["clean", "stain"], "image_size": args.image_size,
                "threshold": threshold, "preprocessing": "rgb-letterbox-imagenet-v1",
                "threshold_source": "validation", "seed": args.seed}
    checkpoint.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    report = {"validation": metrics(val_labels, val_probs, threshold),
              "test": metrics(test_labels, test_probs, threshold),
              "settings": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              "torch": torch.__version__, "device": device}
    (args.output / "metrics.json").write_text(json.dumps(report, indent=2))
    with (args.output / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("split", "path", "label", "stain_probability"))
        writer.writeheader()
        for split, labels, probabilities in (("val", val_labels, val_probs), ("test", test_labels, test_probs)):
            for (path, _), label, probability in zip(datasets[split].samples, labels, probabilities):
                writer.writerow({"split": split, "path": Path(path).relative_to(args.data).as_posix(),
                                 "label": label, "stain_probability": probability})
    with (args.output / "history.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(history[0]))
        writer.writeheader()
        writer.writerows(history)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
