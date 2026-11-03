"""Testbed phase 3a: optical QA data - OPERA DSWx-HLS near every high-water Sentinel-1 pass.

    python scripts/t3_prepare_hls.py

For each pass in <phase2.store>/high_water_passes.csv, finds DSWx-HLS granules
(Landsat 8/9 + Sentinel-2, 30 m) from the day before to the day after, downloads
the WTR layer, and grids each acquisition onto the phase-1 county grid:
  <store>/hls/<pass date>__<HLS time>_wtr.tif
Also records both gauge levels at the HLS time (the river moves between the
optical morning pass and the ~23:40 UTC radar pass) in <store>/hls_scenes.csv.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, "src")
from iceye_csda import s1rtc  # noqa: E402
from iceye_csda import testbed as tb  # noqa: E402
from iceye_csda.auth import EarthdataSession  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402

HLS = "OPERA_L3_DSWX-HLS_V1"


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2 = cfg["phase1"], cfg["phase2"]
    store = Path(p2["store"])
    raw, out = store / "hls_raw", store / "hls"
    out.mkdir(parents=True, exist_ok=True)
    aoi = tb.county_boundary(cfg["county_geoid"], cfg["paths"]["testbed"] / "boundary.geojson")
    grid = s1rtc.county_grid(aoi, p1["grid_res_m"], p1["grid_crs"])
    gauges = [p1["calibration_gauge"], p1["validation_gauge"]]
    iv = {s: tb.gauge_iv(s, cfg["start"], cache=store / f"iv_{s}.csv") for s in gauges}
    session = EarthdataSession()
    rows = []
    for r in pd.read_csv(store / "high_water_passes.csv").itertuples():
        d = date.fromisoformat(r.date)
        ents = requests.get(tb.CMR, timeout=120, params={
            "short_name": HLS, "bounding_box": ",".join(map(str, cfg["bbox"])), "page_size": 200,
            "temporal": f"{d - timedelta(days=1)}T00:00:00Z,{d + timedelta(days=2)}T00:00:00Z"}).json()["feed"]["entry"]
        by_time = {}
        for e in ents:
            by_time.setdefault(e["time_start"][:16], []).append(e)
        for t, es in sorted(by_time.items()):
            stem = f"{r.date}__{t.replace(':', '').replace('-', '')}"
            dst = out / f"{stem}_wtr.tif"
            if not dst.exists():
                paths = []
                for e in es:
                    u = s1rtc.https_links(e, ("_B01_WTR.tif",)).get("_B01_WTR.tif")
                    if u:
                        paths.append(s1rtc.download(u, raw / u.rsplit("/", 1)[-1], session))
                if not paths:
                    continue
                s1rtc.write_grid(dst, s1rtc.mosaic_first(paths, grid, nodata_values=(255,)), grid)
            rows.append({"pass_date": r.date, "track": r.track, "hls_time_utc": t, "tiles": len(es),
                         "file": dst.name,
                         **{f"stage_{s}_ft_at_hls": tb.stage_at(iv[s], pd.Timestamp(t + "Z")) for s in gauges},
                         **{f"stage_{s}_ft_at_sar": getattr(r, f"stage_{s}_ft") for s in gauges}})
            print(f"{r.date} T{r.track}: HLS {t} UTC, {len(es)} tiles")
    pd.DataFrame(rows).to_csv(store / "hls_scenes.csv", index=False)


if __name__ == "__main__":
    main()
