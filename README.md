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
  USGS 3DEP DEM, GLO-30 HAND, JRC water ──┐         ▼
                                          ├──► water mask (tile threshold + region growing,
                                          │     HAND / slope / permanent-water masks)
                                          ▼         │
                          flood depth: FwDET and FLEXTH-style       (04_flood_depth)
```

| Step | Script | Output | Shareable publicly? |
|---|---|---|---|
| 1 | `scripts/01_search.py` | `data/manifest/kentucky_iceye_scenes.csv` + `.geojson` | Yes (public catalog metadata) |
| 2 | download in browser, then `scripts/02_import_downloads.py` | `data/raw/<scene>/…` ICEYE SLC/GRD | **No** |
| 2 (no CSDA account) | `scripts/02c_get_open_data.py <scene>` | `data/raw/<scene>/…` ICEYE Open Data | CC BY 4.0, with attribution |
| 3 | `scripts/03_preprocess.py` | `data/processed/*_sigma0_db.tif` | **No** (value-added) |
| 4 | `scripts/04_flood_depth.py` | `outputs/<scene>/water_mask.tif`, `flood_depth_fwdet.tif`, `flood_depth_flexth.tif`, `summary.txt` | Generally yes (derived) — label it |
| 5 | `scripts/05_validate_gauges.py` | `outputs/<scene>/gauge_validation.csv`, `gauge_summary.txt` | Yes (USGS data + derived levels) |

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
python scripts/05_validate_gauges.py data/processed/<scene>_sigma0_db.tif   # USGS gauges
```

**No CSDA account yet?** Practise on a free ICEYE Open Data scene (same formats,
CC BY 4.0, no login). Lake Borgne / Pearl River, Mississippi–Louisiana, 13 Aug 2025:

```bash
python scripts/02c_get_open_data.py ICEYE_DJ27J0_20250813T103121Z_5743224_X13_SM   # 0.7 GB GRD
python scripts/03_preprocess.py --input data/raw/ICEYE_DJ27J0_20250813T103121Z_5743224_X13_SM/*_GRD.tif
python scripts/04_flood_depth.py data/processed/ICEYE_DJ27J0_20250813T103121Z_5743224_X13_SM_GRD_sigma0_db.tif
```

Outputs from an open-data scene carry the CC BY 4.0 notice; outputs from CSDA
scenes carry the ICEYE copyright and CSDA acknowledgment. The source is read
from `data/raw/<scene>/DATA_SOURCE` (written by `02c`); CSDA is assumed otherwise.

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

**Illustrated guide to 14 flood-depth papers:** [docs/figures/README.md](docs/figures/README.md)


- **Calibration:** `β⁰ = calibration_factor · DN²`, `σ⁰ = β⁰ · sin(θ)` using the
  incidence angle from ICEYE metadata.
- **Water detection:** open water is a specular reflector and appears dark.
  - *Tile (split-based) threshold* (Martinis et al. 2009; Chini et al. 2017): the
    scene is cut into ~2.5 km tiles and only tiles that clearly contain both water
    and land are used to choose the threshold, so a scene that is mostly lake or
    mostly land still gets a sensible value. Falls back to whole-scene Otsu.
  - *Region growing:* water grows into connected pixels up to 1 dB brighter than
    the threshold (rough water near shore).
  - *Masks:* water more than 15 m above the nearest drainage (GLO-30 HAND) or on
    slopes over 5° (usually radar shadow) is rejected. Permanent water (JRC Global
    Surface Water, occurrence ≥ 80 %) is labelled separately, so a lake that the
    radar misses (wind-roughened water looks bright) is still known to be water.
  - Known limitations: smooth pavement looks like water; flooded forest and urban
    floods can look *bright* (double bounce). Seasonal water (marsh ponds, tidal
    flats) is not "permanent" in JRC, so on a non-flood day it shows up as "flood";
    use a pre-flood `--reference` scene to remove it.
- **Depth, two ways** (compare them in `summary.txt`):
  - *FwDET* (Cohen et al. 2018, 2019): each flooded pixel takes the ground elevation
    of the nearest flood-edge pixel as its water surface; depth = water surface − DEM.
  - *FLEXTH-style* (concept of Betterle & Salamon 2024; our own implementation):
    flood-edge pixels on steep ground or out of line with their neighbours (trees,
    levees, buildings) are dropped; the water level is an inverse-distance average
    of nearby edge pixels **of the same water body**; small dry holes inside the
    flood are not treated as shorelines; and the flood may extend up to 500 m into
    connected ground lying at most 1.5 m below the water level (`water_mask.tif`
    class 3; SAR misses shallow water, while deep open water would look dark).
  - Accuracy depends strongly on DEM quality and on a clean flood edge.
- **water_mask.tif classes:** 0 dry · 1 flood water (SAR) · 2 permanent water ·
  3 flood added by FLEXTH · 255 no data. Ancillary layers are cached in `data/dem/`;
  `--no-ancillary` skips HAND and JRC (DEM-only).

- **Validation with USGS gauges** (`05_validate_gauges.py`): for every USGS gauge
  inside the image, the water-surface elevation at the satellite pass (±30 min)
  is compared with three SAR estimates within 500 m: the median elevation of the
  water edge, and the FwDET and FLEXTH water levels (depth + ground). Everything
  is converted to NAVD88 metres, the 3DEP datum: gage height + gage datum, and
  NGVD29 values through NOAA VDatum. Gauges with an unknown datum are listed but
  not scored. Gauges are *not* used to set the water threshold, so they remain an
  independent check; if you ever tune thresholds to gauges, keep some gauges back.

### Suggested exercises

1. Compare whole-scene Otsu (`threshold_method: otsu`) with the tile threshold.
2. Vary `hand_max_m` and `slope_max_deg` in hilly eastern Kentucky; count false positives.
3. Run `05_validate_gauges.py` with different `--radius-m`; add USGS high-water marks (STN).
4. Sensitivity of depth to `depth_smoothing_px`, `flexth.extend_dist_m` and DEM resolution.

## Tests

```bash
pytest -q      # synthetic data only
```

## License & acknowledgment

Code: MIT ([LICENSE](LICENSE)). Data: ICEYE EULA via NASA CSDA ([DATA_LICENSE.md](DATA_LICENSE.md)).

*This work used the data made available through the NASA Commercial Satellite
Data Acquisition (CSDA) Program.* Data products: © ICEYE US, Inc. All Rights Reserved.
