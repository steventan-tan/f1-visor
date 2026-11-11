#!/usr/bin/env python3
"""Desktop image, video or webcam inference; never drives hardware."""
import argparse
import json
import random
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(Path(__file__).resolve().parent / "models/visor_fp32.pt"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image", type=Path)
    source.add_argument("--image-dir", type=Path, help="Select one image from a folder using --seed")
    source.add_argument("--video", type=Path)
    source.add_argument("--camera", type=int, default=0)
    parser.add_argument("--headless", action="store_true", help="Print JSON lines without opening a window")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--snapshots", type=Path, help="Press s in the preview to save an unannotated frame here")
    args = parser.parse_args()
    if args.snapshots and (args.headless or args.image or args.image_dir):
        parser.error("--snapshots requires a video/camera preview")
    if args.image_dir:
        from prepare_data import EXTENSIONS
        images = sorted(p for p in args.image_dir.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS)
        if not images:
            parser.error("No supported images found in --image-dir")
        args.image = random.Random(args.seed).choice(images)
    from PIL import Image
    from f1visor.vision import Predictor
    predictor = Predictor(args.model)

    def result(image):
        probability = predictor.predict(image)
        return {"label": "stain" if probability >= predictor.meta["threshold"] else "clean",
                "stain_probability": round(probability, 6), "threshold": predictor.meta["threshold"]}

    if args.image:
        with Image.open(args.image) as image:
            print(json.dumps({"image": str(args.image), **result(image)}))
        return
    import cv2
    capture = cv2.VideoCapture(str(args.video) if args.video else args.camera)
    try:
        if not capture.isOpened():
            raise RuntimeError("Cannot open video or camera")
        count = 0
        previous = time.monotonic()
        while True:
            ok, frame = capture.read()
            if not ok:
                if not args.video or count == 0:
                    raise RuntimeError("Camera disconnected or video contains no readable frames")
                break
            prediction = result(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            now = time.monotonic()
            fps = 1 / max(now - previous, 1e-9)
            previous = now
            print(json.dumps({"frame": count, "fps": round(fps, 2), **prediction}), flush=True)
            count += 1
            if not args.headless:
                raw_frame = frame.copy() if args.snapshots else None
                text = f"{prediction['label']}: {prediction['stain_probability']:.3f} | {fps:.1f} FPS"
                cv2.putText(frame, text, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
                cv2.imshow("F1 Visor - q to quit", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s") and args.snapshots:
                    args.snapshots.mkdir(parents=True, exist_ok=True)
                    path = args.snapshots / f"frame_{time.time_ns()}.png"
                    if not cv2.imwrite(str(path), raw_frame):
                        raise OSError(f"Could not save snapshot: {path}")
    finally:
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
