import json
import csv
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from f1visor.config import load_config
from f1visor.training import choose_threshold, metrics
from f1visor.vision import Predictor, ResizeWithPad, preprocess, validate_metadata
from prepare_data import split_dataset

ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_config_paths_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"model":"models/test.pt"}')
            self.assertEqual(load_config(path)["model"], str((Path(directory) / "models/test.pt").resolve()))
            for invalid in ({"servo_seconds": -1}, {"servo_gpio": True}, {"hold_seconds": float("nan")},
                            {"servo_neutral": 2}, {"typo": 1}, {"model": ""}, {"baud": 0}):
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_rgb_padding_and_extreme_aspect_ratio(self):
        image = Image.new("RGB", (4, 2), (255, 0, 0))
        padded = ResizeWithPad(4)(image)
        self.assertEqual(padded.getpixel((0, 0)), (123, 123, 123))
        self.assertEqual(padded.getpixel((0, 1)), (255, 0, 0))
        tensor = preprocess(image, 4)
        self.assertEqual(tuple(tensor.shape), (3, 4, 4))
        self.assertGreater(tensor[0, 1, 0].item(), 2)
        self.assertLess(tensor[2, 1, 0].item(), -1)
        self.assertEqual(ResizeWithPad(32)(Image.new("L", (1, 10000))).size, (32, 32))

    def test_threshold_uses_positive_recall_and_handles_ties(self):
        labels, probs = [0, 0, 1, 1, 1], [.1, .9, .3, .5, .5]
        self.assertEqual(choose_threshold(labels, probs, 1), .3)
        self.assertEqual(choose_threshold(labels, probs, .66), .5)
        report = metrics(labels, probs, .5)
        self.assertEqual(report["confusion_matrix"], [[1, 1], [1, 2]])
        with self.assertRaises(ValueError):
            choose_threshold([1], [.5], .98)

    def test_metadata_and_checksum(self):
        meta = {"classes": ["stain", "clean"], "image_size": 224, "threshold": .4,
                "preprocessing": "rgb-letterbox-imagenet-v1", "sha256": "0" * 64}
        with self.assertRaises(ValueError):
            validate_metadata(meta)
        meta["classes"] = ["clean", "stain"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.pt"
            path.write_bytes(b"not a model")
            path.with_suffix(".json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                Predictor(path)

    def test_split_rejects_duplicates_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, label in enumerate(("clean", "stain")):
                (root / "raw" / label).mkdir(parents=True)
                for n in range(7):
                    Image.new("RGB", (8, 8), (index * 100, n * 10, 20)).save(root / "raw" / label / f"{n}.png")
            first = split_dataset(root / "raw", root / "split1")
            second = split_dataset(root / "raw", root / "split2")
            self.assertEqual(first, second)
            self.assertEqual(len(first), 14)
            with self.assertRaises(FileExistsError):
                split_dataset(root / "raw", root / "split1")
            (root / "raw" / "stain" / "0.png").write_bytes((root / "raw" / "clean" / "0.png").read_bytes())
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                split_dataset(root / "raw", root / "split3")
            (root / "raw" / "stain" / "0.png").write_bytes(b"invalid image")
            with self.assertRaises(OSError):
                split_dataset(root / "raw", root / "split3")
            self.assertFalse((root / "split3").exists())

    def test_training_export_and_image_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rng = np.random.default_rng(42)
            for label in ("clean", "stain"):
                (root / "raw" / label).mkdir(parents=True)
                for index in range(14):
                    Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(
                        root / "raw" / label / f"{index}.png")
            split_dataset(root / "raw", root / "split")

            def run(script, *args):
                result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=240)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            run("train.py", "--data", root / "split", "--output", root / "run", "--weights", "none",
                "--epochs", 2, "--freeze-epochs", 1, "--image-size", 64, "--batch-size", 4)
            report = json.loads((root / "run" / "metrics.json").read_text())
            self.assertEqual(report["test"]["samples"], 6)
            self.assertGreaterEqual(report["validation"]["recall"], .98)
            with (root / "run" / "predictions.csv").open() as handle:
                predictions = list(csv.DictReader(handle))
            self.assertEqual(len(predictions), 10)
            self.assertEqual(sum(row['split'] == 'test' for row in predictions), 6)
            self.assertTrue(all(not Path(row['path']).is_absolute() for row in predictions))
            if importlib.util.find_spec('sklearn') and importlib.util.find_spec('matplotlib'):
                run('evaluation_plots.py', '--run', root / 'run', '--data', root / 'split')
                plotted = json.loads((root / 'run' / 'figures' / 'report.json').read_text())
                self.assertEqual(plotted['accuracy'], report['test']['accuracy'])
                self.assertEqual(plotted['threshold'], report['test']['threshold'])
            run("export_model.py", "--checkpoint", root / "run" / "best.pt", "--output", root / "model.pt")
            output = run("detect_video.py", "--model", root / "model.pt", "--image", root / "raw" / "clean" / "0.png")
            prediction = json.loads(output)
            self.assertIn(prediction["label"], ("clean", "stain"))
            self.assertTrue(0 <= prediction["stain_probability"] <= 1)
            self.assertEqual(json.loads((root / "model.json").read_text())["image_size"], 64)
            a = run("detect_video.py", "--model", root / "model.pt", "--image-dir", root / "raw" / "clean", "--seed", 42)
            b = run("detect_video.py", "--model", root / "model.pt", "--image-dir", root / "raw" / "clean", "--seed", 42)
            self.assertEqual(json.loads(a), json.loads(b))


if __name__ == "__main__":
    unittest.main()
