"""Step 5: compare SAR water levels with USGS gauges at the time of the pass.

Run after step 4. Uses outputs/<scene>/water_mask.tif and the two depth maps,
plus the cached 3DEP DEM. Gauge data are public (USGS Water Services).

Outputs in outputs/<scene>/:
  gauge_validation.csv   one row per gauge: gauge WSE, SAR estimates, errors
  gauge_summary.txt      bias / MAE / RMSE per estimate

    python scripts/05_validate_gauges.py data/processed/<scene>_sigma0_db.tif
    python scripts/05_validate_gauges.py <scene> --radius-m 1000 --window-min 60
    python scripts/05_validate_gauges.py <scene> --time 2022-10-07T03:14:00Z

All elevations are NAVD88 metres. Positive error = SAR estimate above the gauge.
Tidal gauges change level quickly, so keep --window-min small near the coast.
"""

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
from iceye_csda import dem as demlib, gauges  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402

ESTIMATES = ("edge", "fwdet", "flexth")


def scene_time(name):
    """Acquisition time from an ICEYE file name (both CSDA and open-data styles)."""
    m = re.search(r"(\d{8}T\d{6})", name)
    if not m:
        raise SystemExit("Cannot read the acquisition time from the file name; pass --time.")
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def fmt(v, nd=2):
    return "" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", type=Path, help="geocoded *_sigma0_db.tif used in step 4")
    ap.add_argument("--time", help="acquisition time, ISO UTC (default: from file name)")
    ap.add_argument("--radius-m", type=float, default=500, help="search radius around gauges")
    ap.add_argument("--window-min", type=int, default=30, help="gauge reading time window")
    ap.add_argument("--config", default="config/kentucky.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)

    import rasterio
    from rasterio.warp import transform, transform_bounds

    when = (datetime.fromisoformat(args.time.replace("Z", "+00:00")) if args.time
            else scene_time(args.scene.name))
    stem = args.scene.stem
    out = cfg["paths"]["outputs"] / stem.replace("_sigma0_db", "")
    if not (out / "water_mask.tif").exists():
        raise SystemExit(f"Run step 4 first: {out}/water_mask.tif not found.")

    with rasterio.open(out / "water_mask.tif") as src:
        classes = src.read(1)
        crs, tf = src.crs, src.transform
        bbox = transform_bounds(crs, "EPSG:4326", *src.bounds)
        px = abs(tf.a)
    depths = {}
    for name in ("fwdet", "flexth"):
        with rasterio.open(out / f"flood_depth_{name}.tif") as src:
            depths[name] = src.read(1)
    dem_path = cfg["paths"]["dem"] / f"{stem}_3dep.tif"
    if not dem_path.exists():
        raise SystemExit(f"DEM not found: {dem_path} (step 4 creates it).")
    dem = demlib.align_to(dem_path, out / "water_mask.tif")
    radius_px = max(1, int(round(args.radius_m / px)))

    print(f"Scene time {when:%Y-%m-%d %H:%M} UTC; searching USGS gauges ...")
    sites = gauges.fetch_sites(bbox)
    xs, ys = transform("EPSG:4326", crs, [float(s["dec_long_va"]) for s in sites],
                       [float(s["dec_lat_va"]) for s in sites]) if sites else ([], [])
    in_scene = []
    for s, x, y in zip(sites, xs, ys):
        col, row = ~tf * (x, y)
        row, col = int(row), int(col)
        if 0 <= row < classes.shape[0] and 0 <= col < classes.shape[1] \
                and classes[row, col] != 255:
            in_scene.append((s, row, col))
    print(f"   {len(sites)} gauges in the bounding box, {len(in_scene)} inside the image")
    levels = gauges.fetch_levels([s["site_no"] for s, _, _ in in_scene], when, args.window_min)

    rows = []
    for s, row, col in in_scene:
        rec = levels.get(s["site_no"], {})
        wse, param, note = gauges.gauge_wse_navd88(s, rec)
        est = gauges.estimates_near(row, col, radius_px, classes, dem, depths)
        r = {"site_no": s["site_no"], "name": s["station_nm"], "type": s.get("site_tp_cd", ""),
             "lat": s["dec_lat_va"], "lon": s["dec_long_va"], "param": param or "",
             "reading_utc": rec[param][1].strftime("%Y-%m-%d %H:%M") if param in rec else "",
             "datum_note": note, "gauge_wse_m": wse,
             "class_at_gauge": int(classes[row, col]),
             "nearest_water_m": est["water_dist_px"] * px}
        for k in ESTIMATES:
            r[f"{k}_wse_m"] = est[k]
            r[f"{k}_n"] = est[f"{k}_n"]
            r[f"{k}_error_m"] = est[k] - wse if wse is not None else np.nan
        rows.append(r)

    fields = ["site_no", "name", "type", "lat", "lon", "param", "reading_utc", "datum_note",
              "gauge_wse_m", "class_at_gauge", "nearest_water_m"]
    for k in ESTIMATES:
        fields += [f"{k}_wse_m", f"{k}_n", f"{k}_error_m"]
    with open(out / "gauge_validation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (fmt(v, 3) if isinstance(v, float) else ("" if v is None else v))
                        for k, v in r.items()})

    lines = [f"scene: {args.scene.name}", f"time: {when:%Y-%m-%d %H:%M} UTC "
             f"(gauge window +/- {args.window_min} min), radius {args.radius_m:.0f} m",
             f"gauges inside image: {len(rows)}; with NAVD88 water level: "
             f"{sum(r['gauge_wse_m'] is not None for r in rows)}", ""]
    lines.append(f"{'site':16s} {'gauge':>7s} " + " ".join(f"{k:>8s}" for k in ESTIMATES)
                 + "  name")
    for r in rows:
        lines.append(f"{r['site_no']:16s} {fmt(r['gauge_wse_m']):>7s} "
                     + " ".join(f"{fmt(r[f'{k}_wse_m']):>8s}" for k in ESTIMATES)
                     + f"  {r['name'][:38]}" + ("" if r["gauge_wse_m"] is not None
                                                else f"  [{r['datum_note']}]"))
    lines.append("")
    for k in ESTIMATES:
        sc = gauges.score([r[f"{k}_error_m"] for r in rows])
        lines.append(f"{k:7s} n={sc['n']:3d}  bias {fmt(sc['bias']):>6s} m  "
                     f"MAE {fmt(sc['mae']):>5s} m  RMSE {fmt(sc['rmse']):>5s} m")
    lines += ["", "Elevations NAVD88 m. Gauge data: USGS Water Services; "
              "NGVD29 conversion: NOAA VDatum."]
    (out / "gauge_summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
