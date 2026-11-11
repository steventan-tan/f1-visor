#!/usr/bin/env python3
"""Validate owned/lawfully reusable images and create a seeded 70/15/15 split."""
import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path
from PIL import Image

EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def validate_images(groups):
    seen = {}
    records = []
    for group, paths in groups.items():
        if not paths:
            raise ValueError(f"Empty image group: {group}")
        for path in paths:
            with Image.open(path) as image:
                image.verify()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:
                raise ValueError(f"Duplicate image: {path} and {seen[digest]}")
            seen[digest] = path
            records.append({"group": group, "name": path.name, "sha256": digest})
    return records


def split_dataset(source, destination, seed=42):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    classes = sorted(p.name for p in source.iterdir() if p.is_dir())
    if classes != ["clean", "stain"]:
        raise ValueError("Data folders must be exactly clean/ and stain/")
    groups = {label: sorted(p for p in (source / label).iterdir()
                            if p.is_file() and p.suffix.lower() in EXTENSIONS) for label in classes}
    for label, paths in groups.items():
        if len(paths) < 7:
            raise ValueError(f"Need at least 7 unique images in {label} for a three-way split")
    records = validate_images(groups)
    rng = random.Random(seed)
    assignments = {}
    for label, paths in groups.items():
        rng.shuffle(paths)
        a, b = int(len(paths) * .7), int(len(paths) * .15)
        for split, subset in zip(("train", "val", "test"), (paths[:a], paths[a:a+b], paths[a+b:])):
            for path in subset:
                assignments[(label, path.name)] = split
    destination.mkdir(parents=True)
    for record in records:
        record["split"] = assignments[(record["group"], record["name"])]
        target = destination / record["split"] / record["group"] / record["name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / record["group"] / record["name"], target)
    (destination / "manifest.json").write_text(json.dumps({"seed": seed, "images": records}, indent=2))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/split"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    records = split_dataset(args.source, args.output, args.seed)
    print(f"Prepared {len(records)} images in {args.output}")


if __name__ == "__main__":
    main()
