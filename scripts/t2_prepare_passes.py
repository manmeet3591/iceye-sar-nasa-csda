"""Testbed phase 2a: find every high-water Sentinel-1 pass since 2016 and grid it.

    python scripts/t2_prepare_passes.py

1. Lists all OPERA RTC-S1 bursts over the county (CMR) and groups them into passes.
2. Reads both USGS gauges at each pass time from the full 15-minute record.
3. Keeps passes where either gauge was >= phase2.min_stage_ft, downloads and grids them
   onto the phase-1 30 m grid (and DSWx-S1 where it exists, Aug 2024 onwards).

Large files go to phase2.store (e.g. /data1). Writes <store>/s1_passes_stage.csv
(every pass with both gauge levels) and <store>/high_water_passes.csv.
"""

import collections
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")
from iceye_csda import s1rtc  # noqa: E402
from iceye_csda import testbed as tb  # noqa: E402
from iceye_csda.auth import EarthdataSession  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2 = cfg["phase1"], cfg["phase2"]
    store = Path(p2["store"])
    raw, out = store / "s1_raw", store / "s1"
    aoi = tb.county_boundary(cfg["county_geoid"], cfg["paths"]["testbed"] / "boundary.geojson")
    grid = s1rtc.county_grid(aoi, p1["grid_res_m"], p1["grid_crs"])
    gauges = [p1["calibration_gauge"], p1["validation_gauge"]]

    iv = {s: tb.gauge_iv(s, cfg["start"], cache=store / f"iv_{s}.csv") for s in gauges}
    passes = collections.defaultdict(list)
    for e in tb.cmr_granules(s1rtc.RTC, cfg["bbox"], cfg["start"]):
        t = s1rtc.track_of(e["title"])
        if t in p2["tracks"]:
            passes[(t, e["time_start"][:10])].append(pd.Timestamp(e["time_start"]))
    rows = []
    for (t, d), ts in passes.items():
        tm = min(ts) + (max(ts) - min(ts)) / 2
        rows.append({"track": t, "date": d, "time_utc": tm.isoformat(), "bursts": len(ts),
                     **{f"stage_{s}_ft": tb.stage_at(iv[s], tm) for s in gauges}})
    allp = pd.DataFrame(rows).sort_values(["date", "track"])
    allp.to_csv(store / "s1_passes_stage.csv", index=False)
    high = allp[(allp[[f"stage_{s}_ft" for s in gauges]] >= p2["min_stage_ft"]).any(axis=1)]
    high.to_csv(store / "high_water_passes.csv", index=False)
    print(f"{len(allp)} passes on tracks {p2['tracks']}; {len(high)} with a gauge >= "
          f"{p2['min_stage_ft']} ft")

    session = EarthdataSession()
    for r in high.itertuples():
        n = s1rtc.prepare_pass(r.date, r.track, grid, cfg["bbox"], raw, out, session)
        k = s1rtc.prepare_dswx(r.date, grid, cfg["bbox"], raw, out, session)
        print(f"  {r.date} T{r.track}: bursts {n if n >= 0 else 'cached'}, DSWx tiles "
              f"{k if k >= 0 else 'cached'}  (Barren {getattr(r, f'stage_{gauges[0]}_ft'):.1f} ft, "
              f"Drakes {getattr(r, f'stage_{gauges[1]}_ft'):.1f} ft)")
    print("done:", out)


if __name__ == "__main__":
    main()
