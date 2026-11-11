#!/usr/bin/env python3
"""Export a checkpoint + metadata pair to a portable FP32 TorchScript pair."""
import argparse
import json
from pathlib import Path
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("models/visor_fp32.pt"))
    args = parser.parse_args()
    if args.output.suffix != ".pt":
        parser.error("output must end in .pt")
    if args.output.exists() or args.output.with_suffix(".json").exists():
        parser.error("Output exists; choose a new model filename")
    import torch
    from f1visor.training import build_model
    from f1visor.vision import sha256, validate_metadata
    metadata = json.loads(args.checkpoint.with_suffix(".json").read_text())
    validate_metadata({**metadata, "sha256": "0" * 64})
    torch.set_num_threads(1)
    model = build_model()
    model.load_state_dict(torch.load(args.checkpoint, map_location="cpu", weights_only=True))
    model.eval()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as directory:
        temporary = Path(directory) / "model.pt"
        with torch.inference_mode():
            example = torch.randn(1, 3, metadata["image_size"], metadata["image_size"])
            # Avoid optimize_for_inference: it can serialize CPU-specific operators.
            scripted = torch.jit.trace(model, example)
            scripted.save(str(temporary))
            restored = torch.jit.load(str(temporary), map_location="cpu").eval()
            torch.testing.assert_close(restored(example), model(example), rtol=1e-4, atol=1e-5)
        metadata.update(sha256=sha256(temporary), format="torchscript-fp32", torch=torch.__version__)
        temporary.replace(args.output)
    args.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    print(f"Exported and reload-checked: {args.output}")


if __name__ == "__main__":
    main()
