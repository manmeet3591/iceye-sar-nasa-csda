# Student setup: getting your own ICEYE data access

The ICEYE data is licensed to approved users only. You must download it with
**your own** account; the instructor cannot post or email the files to you.

1. Create a NASA Earthdata Login account: <https://urs.earthdata.nasa.gov/users/new>
2. Request CSDA access: <https://csdap.earthdata.nasa.gov/signup/>
   State that you are a student working under your instructor's U.S.
   Government-funded research/teaching project (name the project and grant).
3. Wait for CSDA approval, then accept the ICEYE End User License Agreement.
4. Generate a token: Earthdata Login → *Generate Token*.
5. Set it in your shell (never put it in code or commit it):
   ```bash
   export EARTHDATA_TOKEN="paste-token-here"
   ```
6. Run:
   ```bash
   pip install -r requirements.txt     # or: conda env create -f environment.yml
   pre-commit install                  # blocks accidental commits of imagery
   python scripts/01_search.py
   python scripts/02_download.py --products GRD
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
