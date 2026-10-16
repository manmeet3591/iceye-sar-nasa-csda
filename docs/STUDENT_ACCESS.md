# Student setup: getting your own ICEYE data access

The ICEYE data is licensed to approved users only. You must download it with
**your own** account; the instructor cannot post or email the files to you.

1. Create a NASA Earthdata Login account: <https://urs.earthdata.nasa.gov/users/new>
2. Request CSDA access: <https://csdap.earthdata.nasa.gov/signup/>
   State that you are a student working under your instructor's U.S.
   Government-funded research/teaching project (name the project and grant).
3. Wait for CSDA approval, then accept the ICEYE End User License Agreement.
4. Set up the code and list the scenes:
   ```bash
   pip install -r requirements.txt     # or: conda env create -f environment.yml
   pre-commit install                  # blocks accidental commits of imagery
   python scripts/01_search.py         # writes data/manifest/kentucky_iceye_scenes.csv
   ```
5. Download in your browser: log in at <https://csdap.earthdata.nasa.gov>,
   open the ICEYE collection, find each scene by its ID from the manifest
   (e.g. `ICEYE_X23_GRD_SM_3146847_20231223T063544`) and download its `.tif`
   (GRD) or `.h5` (SLC) plus the `.xml` metadata file. GRD scenes are ~0.8 GB
   each; start with GRD.
6. Run:
   ```bash
   python scripts/02_import_downloads.py ~/Downloads   # moves files into data/raw/<scene>/
   python scripts/03_preprocess.py
   python scripts/04_flood_depth.py data/processed/<scene>_sigma0_db.tif
   ```

## Rules

- Do not upload ICEYE imagery, calibrated images, or screenshots of them to
  GitHub, Slack, Google Drive, or social media.
- Flood masks / depth maps you produce are derived products; label them with
  "Includes copyrighted material of ICEYE US, Inc. All rights reserved."
- Figures showing ICEYE imagery in reports: add "© ICEYE US, Inc., YYYY. All Rights Reserved."
- Acknowledge: "This work used the data made available through the NASA
  Commercial Satellite Data Acquisition (CSDA) Program."
- No commercial use.
