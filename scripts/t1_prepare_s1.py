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

RTC = "OPERA_L2_RTC-S1_V1"
DSWX = "OPERA_L3_DSWX-S1_V1"


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
            stem = out / f"{day}_T{int(track):03d}"
            if not (stem.parent / f"{stem.name}_VV_db.tif").exists():
                ents = [e for e in s1rtc.day_granules(RTC, bbox, day)
                        if s1rtc.track_of(e["title"]) == int(track)]
                files = {"VV": [], "VH": [], "mask": []}
                for e in ents:
                    links = s1rtc.https_links(e, ("_VV.tif", "_VH.tif", "_mask.tif"))
                    for key, suf in (("VV", "_VV.tif"), ("VH", "_VH.tif"), ("mask", "_mask.tif")):
                        if suf in links:
                            u = links[suf]
                            files[key].append(s1rtc.download(u, raw / day / u.rsplit("/", 1)[-1],
                                                             session))
                print(f"{day} T{track}: {len(ents)} bursts")
                # mask: 0 = valid in OPERA RTC; anything else is shadow/layover/invalid
                bad = np.zeros(grid[2], bool)
                for m in files["mask"]:
                    a = s1rtc.to_grid(m, grid, "nearest", src_nodata=255)
                    bad |= np.isfinite(a) & (a > 0)
                for pol in ("VV", "VH"):
                    lin = s1rtc.mosaic_mean(files[pol], grid)
                    s1rtc.write_grid(stem.parent / f"{stem.name}_{pol}_db.tif", s1rtc.db(lin), grid)
                vv = s1rtc.read_grid(stem.parent / f"{stem.name}_VV_db.tif")
                s1rtc.write_grid(stem.parent / f"{stem.name}_valid.tif",
                                 (np.isfinite(vv) & ~bad).astype("uint8"), grid, nodata=None,
                                 dtype="uint8")
                (stem.parent / f"{stem.name}_time.txt").write_text(
                    str(s1rtc.acquisition_time(ents)))
            dsw = out / f"{day}_dswx_wtr.tif"
            if not dsw.exists():
                ents = s1rtc.newest_per_tile([e for e in s1rtc.day_granules(DSWX, bbox, day)])
                paths = []
                for e in ents:
                    u = s1rtc.https_links(e, ("_B01_WTR.tif",)).get("_B01_WTR.tif")
                    if u:
                        paths.append(s1rtc.download(u, raw / day / u.rsplit("/", 1)[-1], session))
                if paths:
                    s1rtc.write_grid(dsw, s1rtc.mosaic_first(paths, grid), grid)
                print(f"{day}: DSWx-S1 tiles {len(paths)}")
    print("done:", out)


if __name__ == "__main__":
    main()
