"""Testbed phase 1a: download Sentinel-1 OPERA RTC + DSWx-S1 and put them on the county grid.

    python scripts/t1_prepare_s1.py                 # all dates in config phase1.tracks

Writes data/testbed/<name>/s1/ (git-ignored):
  <date>_T<track>_VV_db.tif, _VH_db.tif   gamma0 (dB), mean of overlapping bursts
  <date>_T<track>_valid.tif               1 = valid, not layover/shadow
  <date>_dswx_wtr.tif                     OPERA DSWx-S1 WTR classes (newest version per tile)
  ancillary: dem.tif (USGS 3DEP), hand.tif (GLO-30 HAND), slope.tif, jrc_occurrence.tif,
             aoi.tif (1 inside the county)
Sentinel-1 / OPERA products are open data (NASA/ESA), not CSDA-licensed.
"""

import sys

import numpy as np

sys.path.insert(0, "src")
from iceye_csda import ancillary, dem as demlib, s1rtc  # noqa: E402
from iceye_csda import testbed as tb  # noqa: E402
from iceye_csda.auth import EarthdataSession  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402



def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1 = cfg["phase1"]
    base = cfg["paths"]["testbed"]
    raw, out = base / "s1_raw", base / "s1"
    aoi = tb.county_boundary(cfg["county_geoid"], base / "boundary.geojson")
    grid = s1rtc.county_grid(aoi, p1["grid_res_m"], p1["grid_crs"])
    print(f"grid {grid[2]} at {p1['grid_res_m']} m, {grid[0]}")
    session = EarthdataSession()
    bbox = cfg["bbox"]

    # ancillary layers -------------------------------------------------------
    s1rtc.write_grid(out / "aoi.tif", s1rtc.aoi_mask(aoi, grid).astype("uint8"), grid,
                     nodata=None, dtype="uint8")
    pad = (bbox[0] - 0.02, bbox[1] - 0.02, bbox[2] + 0.02, bbox[3] + 0.02)
    for name, fetch, res in (("dem", demlib.fetch_3dep, "average"),
                             ("hand", ancillary.fetch_hand, "bilinear"),
                             ("jrc_occurrence", ancillary.fetch_permanent_water, "average")):
        dst = out / f"{name}.tif"
        if dst.exists():
            continue
        src = raw / f"{name}_wgs84.tif"
        if not src.exists():
            print(f"fetching {name} ...")
            raw.mkdir(parents=True, exist_ok=True)
            fetch(pad, out_path=src)
        s1rtc.write_grid(dst, s1rtc.to_grid(src, grid, res), grid)
    if not (out / "slope.tif").exists():
        s1rtc.write_grid(out / "slope.tif",
                         ancillary.slope_deg(s1rtc.read_grid(out / "dem.tif"), p1["grid_res_m"]),
                         grid)

    # per date ---------------------------------------------------------------
    for track, t in p1["tracks"].items():
        for day in t["dates"]:
            n = s1rtc.prepare_pass(day, track, grid, bbox, raw, out, session)
            if n >= 0:
                print(f"{day} T{track}: {n} bursts")
            n = s1rtc.prepare_dswx(day, grid, bbox, raw, out, session)
            if n >= 0:
                print(f"{day}: DSWx-S1 tiles {n}")
    print("done:", out)


if __name__ == "__main__":
    main()
