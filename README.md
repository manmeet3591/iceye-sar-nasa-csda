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
 STAC search ──► download ──► calibrate σ⁰ ──► Lee filter ──► geocode (UTM 10 m)
 (01_search)   (02_import)          (03_preprocess)
                                                          │
                     USGS 3DEP DEM ─────────────┐         ▼
                                                ├──► water mask (Otsu)
                                                ▼         │
                                         flood depth (FwDET-style)  (04_flood_depth)
```

| Step | Script | Output | Shareable publicly? |
|---|---|---|---|
| 1 | `scripts/01_search.py` | `data/manifest/kentucky_iceye_scenes.csv` + `.geojson` | Yes (public catalog metadata) |
| 2 | download in browser, then `scripts/02_import_downloads.py` | `data/raw/<scene>/…` ICEYE SLC/GRD | **No** |
| 3 | `scripts/03_preprocess.py` | `data/processed/*_sigma0_db.tif` | **No** (value-added) |
| 4 | `scripts/04_flood_depth.py` | `outputs/<scene>/water_mask.tif`, `flood_depth.tif`, `summary.txt` | Generally yes (derived) — label it |

## Quick start

```bash
git clone https://github.com/<owner>/iceye-sar-nasa-csda.git
cd iceye-sar-nasa-csda
conda env create -f environment.yml && conda activate iceye-csda   # or pip install -r requirements.txt
pre-commit install                     # blocks accidental commits of imagery

python scripts/01_search.py              # list ICEYE scenes over Kentucky (no login needed)

# Download the scenes you need from https://csdap.earthdata.nasa.gov (Earthdata login),
# using the scene IDs in data/manifest/kentucky_iceye_scenes.csv, then:
python scripts/02_import_downloads.py ~/Downloads   # sorts files into data/raw/<scene>/
python scripts/03_preprocess.py
python scripts/04_flood_depth.py data/processed/<scene>_sigma0_db.tif
```

### Data available over Kentucky (CSDA STAC, searched Oct 2026)

10 ICEYE stripmap (~3 m, VV) scenes, each delivered as both **GRD** (GeoTIFF, ~0.8 GB)
and **SLC** (HDF5, ~3.6 GB); 22.9 GB total:

| Date (UTC) | Satellite | Area (approx.) |
|---|---|---|
| 2023-12-23 | ICEYE-X23 | Hopkinsville / Clarksville (-87.3 to -86.8°, 36.4–37.0°N) |
| 2023-12-29 | ICEYE-X11 | KY–TN border near Nashville (-86.8 to -86.2°, 36.0–36.7°N) |
| 2024-01-10 | ICEYE-X14 | Hopkinsville / Land Between the Lakes (-87.6 to -87.0°, 36.3–37.0°N) |
| 2024-05-22 | ICEYE-X2  | Henderson / Ohio River (-88.4 to -87.8°, 37.4–38.0°N) |
| 2024-05-22 | ICEYE-X8  | Louisville / Ohio River (-86.1 to -85.5°, 37.9–38.6°N) |

Footprints: [`data/manifest/kentucky_iceye_scenes.geojson`](data/manifest/kentucky_iceye_scenes.geojson).
The 2023-12-23 and 2024-01-10 scenes overlap and can serve as a before/after pair.

Scripted downloads are possible with CSDA API credentials
(`scripts/02b_download_api_optional.py`), but are not required.

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
