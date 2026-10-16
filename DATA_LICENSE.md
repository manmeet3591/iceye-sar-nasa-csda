# Data license and compliance

The **code** in this repository is released under the MIT License (see `LICENSE`).

The **ICEYE SAR data** used by this code is **not** included and is **not** covered
by the MIT License. It is distributed by the NASA Commercial Satellite Data
Acquisition (CSDA) Program under ICEYE's End User License Agreement (U.S. Government
tier). Each user must obtain the data themselves through their own approved CSDA
account.

## What may and may not be shared publicly

| Item | Public repo? | Reason |
|---|---|---|
| Source code, notebooks without embedded imagery | Yes | Not licensed material |
| Scene IDs / footprints from the CSDA STAC catalog (`data/manifest/`) | Yes | Catalog metadata is publicly searchable; no imagery or thumbnails |
| Raw ICEYE products (SLC, GRD, CSI, QLK, metadata sidecars) | **No** | Licensed material |
| Calibrated / geocoded / cropped / filtered imagery, image previews | **No** | "Value-added products" are still licensed material |
| Binary flood masks, flood-depth rasters, summary statistics | Generally yes* | "Derived products" (source not recoverable) |

\* Confirm with the CSDA program before publishing, and label with the notice below.

## Required notices

- Imagery or figures showing ICEYE pixels: `© ICEYE US, Inc., YYYY. All Rights Reserved.`
- Derived products: `Includes copyrighted material of ICEYE US, Inc. All rights reserved.`
- Acknowledgment in reports/publications: *"This work used the data made available
  through the NASA Commercial Satellite Data Acquisition (CSDA) Program."*
- Preserve ICEYE copyright metadata in any files shared among authorized users.
- No commercial or revenue-generating use of the data or derived products.
- Send a courtesy copy of publications using the data to the CSDA program.

## Guards in this repository

- `.gitignore` excludes raster/SAR formats and the `data/` directory.
- `tools/check_no_licensed_data.py` runs as a pre-commit hook and in GitHub Actions
  and fails if raster files, ICEYE sidecars or large binaries are committed.

Request access: <https://csdap.earthdata.nasa.gov/signup/>
