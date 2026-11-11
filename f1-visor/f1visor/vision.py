"""The same RGB letterboxing and normalization for training and inference."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch
from PIL import Image

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class ResizeWithPad:
    def __init__(self, size, fill=(123, 123, 123)):
        if type(size) is not int or size <= 0:
            raise ValueError("image size must be a positive integer")
        self.size, self.fill = size, fill

    def __call__(self, image):
        image = image.convert("RGB")
        w, h = image.size
        scale = min(self.size / w, self.size / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = image.resize((nw, nh), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (self.size, self.size), self.fill)
        canvas.paste(resized, ((self.size - nw) // 2, (self.size - nh) // 2))
        return canvas


def preprocess(image, size):
    image = ResizeWithPad(size)(image)
    tensor = torch.from_numpy(np.array(image, dtype=np.float32)).permute(2, 0, 1) / 255
    return (tensor - torch.tensor(MEAN)[:, None, None]) / torch.tensor(STD)[:, None, None]


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def validate_metadata(meta):
    if not isinstance(meta, dict) or meta.get("classes") != ["clean", "stain"]:
        raise ValueError("Model must declare ordered classes ['clean', 'stain']")
    if type(meta.get("image_size")) is not int or not 32 <= meta["image_size"] <= 2048:
        raise ValueError("Model image_size must be an integer in [32, 2048]")
    t = meta.get("threshold")
    if type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= 1:
        raise ValueError("Model threshold must be finite and in [0, 1]")
    if meta.get("preprocessing") != "rgb-letterbox-imagenet-v1":
        raise ValueError("Unsupported preprocessing contract")
    digest = meta.get("sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Model needs a SHA-256 digest")
    return meta


class Predictor:
    def __init__(self, model_path):
        path = Path(model_path)
        self.meta = validate_metadata(json.loads(path.with_suffix(".json").read_text()))
        if sha256(path) != self.meta["sha256"]:
            raise ValueError("Model hash mismatch; use the matching .pt and .json files")
        torch.set_num_threads(1)
        self.model = torch.jit.load(str(path), map_location="cpu").eval()

    def predict(self, image):
        x = preprocess(image, self.meta["image_size"]).unsqueeze(0)
        with torch.inference_mode():
            logits = self.model(x)
            if logits.shape != (1, 2) or not torch.isfinite(logits).all():
                raise ValueError("Expected finite logits of shape [1, 2]")
            return torch.softmax(logits, dim=1)[0, 1].item()
