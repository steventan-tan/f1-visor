# Model artifacts

Public source contains no trained model binaries. Generate a matched pair:

```bash
python export_model.py --checkpoint runs/experiment-01/best.pt --output models/visor_fp32.pt
```

Then copy both `visor_fp32.pt` and `visor_fp32.json` to the target machine. They are ignored by Git intentionally. The author's prepared local folder also contains an unchanged copy of the supplied FP32 deployment model and provisional metadata; see [the model card](../docs/MODEL_CARD.md).

If model/data rights are established, these files may be distributed separately as a GitHub Release asset with their provenance and evaluation. No public download URL is invented here.
