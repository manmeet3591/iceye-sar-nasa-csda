# iceye-sar-nasa-csda

Teaching code for **flood extent and flood depth estimation** in **Kentucky** from
**ICEYE X-band SAR** data obtained through the **NASA Commercial Satellite Data
Acquisition (CSDA) Program**.

> **This repository contains code only. No ICEYE data is included.**
> ICEYE data is licensed (U.S. Government tier EULA). Every user downloads it
> with their own approved CSDA/Earthdata account. See [DATA_LICENSE.md](DATA_LICENSE.md)
> and [docs/STUDENT_ACCESS.md](docs/STUDENT_ACCESS.md).

## Workflow

```
 CMR search ──► download ──► calibrate σ⁰ ──► Lee filter ──► geocode (UTM 10 m)
 (01_search)   (02_download)        (03_preprocess)
                                                          │
                     USGS 3DEP DEM ─────────────┐         ▼
                                                ├──► water mask (Otsu)
                                                ▼         │
                                         flood depth (FwDET-style)  (04_flood_depth)
```

| Step | Script | Output | Shareable publicly? |
|---|---|---|---|
| 1 | `scripts/01_search.py` | `data/manifest/kentucky_iceye_granules.csv` | Yes (public CMR metadata) |
| 2 | `scripts/02_download.py` | `data/raw/…` ICEYE SLC/GRD/CSI/… | **No** |
| 3 | `scripts/03_preprocess.py` | `data/processed/*_sigma0_db.tif` | **No** (value-added) |
| 4 | `scripts/04_flood_depth.py` | `outputs/<scene>/water_mask.tif`, `flood_depth.tif`, `summary.txt` | Generally yes (derived) — label it |

## Quick start

```bash
git clone https://github.com/<owner>/iceye-sar-nasa-csda.git
cd iceye-sar-nasa-csda
conda env create -f environment.yml && conda activate iceye-csda   # or pip install -r requirements.txt
pre-commit install                     # blocks accidental commits of imagery

export EARTHDATA_TOKEN="..."           # from https://urs.earthdata.nasa.gov  (never commit it)

python scripts/01_search.py                         # all ICEYE granules over Kentucky
python scripts/02_download.py --dry-run --limit 5   # preview
python scripts/02_download.py --products GRD        # GRD is what the flood workflow uses
python scripts/03_preprocess.py
python scripts/04_flood_depth.py data/processed/<scene>_sigma0_db.tif
```

Edit `config/kentucky.yaml` to change the bounding box, dates, product types or
flood parameters.

## Method notes (for students)

- **Calibration:** `β⁰ = calibration_factor · DN²`, `σ⁰ = β⁰ · sin(θ)` using the
  incidence angle from ICEYE metadata.
- **Water detection:** open water is a specular reflector and appears dark.
  An automatic Otsu threshold splits the σ⁰ (dB) histogram. Known limitations:
  radar shadow and smooth pavement look like water; flooded forest and urban
  floods can look *bright* (double bounce). Use a pre-flood `--reference` scene
  to remove permanent water bodies (rivers, lakes).
- **Depth:** following FwDET (Cohen et al., 2018, 2019), ground elevations along the
  flood edge approximate the water surface; depth = water surface − DEM.
  Accuracy depends strongly on DEM quality and on a clean flood edge.

### Suggested exercises

1. Compare Otsu thresholds across scenes and incidence angles.
2. Add a slope / HAND mask to remove false positives in hilly eastern Kentucky.
3. Validate depths against USGS stream gauges or high-water marks.
4. Sensitivity of depth to `depth_smoothing_px` and DEM resolution.

## Tests

```bash
pytest -q      # synthetic data only
```

## License & acknowledgment

Code: MIT ([LICENSE](LICENSE)). Data: ICEYE EULA via NASA CSDA ([DATA_LICENSE.md](DATA_LICENSE.md)).

*This work used the data made available through the NASA Commercial Satellite
Data Acquisition (CSDA) Program.* Data products: © ICEYE US, Inc. All Rights Reserved.
