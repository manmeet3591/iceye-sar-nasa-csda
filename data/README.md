# data/

Everything in this folder except `manifest/` is git-ignored.

- `manifest/` — public CMR metadata (granule IDs, dates, footprints). Safe to commit.
- `raw/` — ICEYE products downloaded from CSDA. **Licensed. Never commit or share publicly.**
- `processed/` — calibrated/geocoded imagery. **Value-added = still licensed.**
- `dem/` — USGS 3DEP elevation (public domain).
