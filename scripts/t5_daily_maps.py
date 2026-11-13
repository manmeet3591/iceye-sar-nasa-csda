"""Testbed phase 5: daily flood maps for the Barren River at Bowling Green from gauge + 1 m lidar.

Run after the phase 2 and 3 scripts (it reuses their Sentinel-1 and DSWx-HLS grids).

    python scripts/t5_daily_maps.py

1. USGS 3DEP 1 m lidar (KY_WesternKY_A22, 4 tiles in <store>/lidar_1m) averaged to 3 m
   on a grid that nests exactly in the 30 m county grid (10 x 10 cells per 30 m pixel).
2. Barren River channel = USGS NHD flowline + river area, widened 9 m (JRC water is too
   patchy for a 50-70 m wide, tree-lined river: 134 pieces at this scale).
   For every pixel: the river rise at which it floods and is connected to the river
   (floodmodel.connected_level).
3. Rise at the gauge = gauge water surface (stage + NAVD88 datum) - lidar river surface at
   the gauge + offset. The offset is calibrated against Sentinel-1 water on open fields
   (grass/cropland) for the 16 high-water passes, with leave-one-pass-out.
4. Independent check: the cloud-free DSWx-HLS scene of 14 Feb 2020, all land covers.
5. Daily flooded area for every day since 2016 (daily max stage) and depth maps for the
   three highest days.

Large rasters go to <store>/phase5; summary, CSV and figures to outputs/<name>/phase5.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from iceye_csda import floodmodel as fm  # noqa: E402
from iceye_csda import gauges, s1rtc  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402

FT = 0.3048
FINE = 3.0                 # m
FACTOR = 10                # 3 m -> 30 m


def lidar_grid(tiles, county_tf, crs):
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    bs = []
    for t in tiles:
        with rasterio.open(t) as s:
            bs.append(transform_bounds(s.crs, crs, *s.bounds))
    w, s_, e, n = min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)
    c0, f0 = county_tf.c, county_tf.f
    w = c0 + np.ceil((w - c0) / 30) * 30
    e = c0 + np.floor((e - c0) / 30) * 30
    n = f0 - np.ceil((f0 - n) / 30) * 30
    s_ = f0 - np.floor((f0 - s_) / 30) * 30
    shape = (int(round((n - s_) / FINE)), int(round((e - w) / FINE)))
    return crs, from_origin(w, n, FINE, FINE), shape


def mosaic_dem(tiles, grid):
    import rasterio
    from rasterio.warp import Resampling, reproject

    crs, tf, shape = grid
    out = np.full(shape, np.nan, "float32")
    for t in tiles:
        tmp = np.full(shape, np.nan, "float32")
        with rasterio.open(t) as s:
            reproject(rasterio.band(s, 1), tmp, src_nodata=s.nodata, dst_transform=tf, dst_crs=crs,
                      dst_nodata=np.nan, resampling=Resampling.average)
        fill = np.isnan(out) & np.isfinite(tmp)
        out[fill] = tmp[fill]
    return out


def coarse_window(grid, county_grid):
    """Rows/cols of the 30 m county grid covered by the 3 m grid."""
    _, tf, shape = grid
    _, ctf, _ = county_grid
    r0 = int(round((ctf.f - tf.f) / 30))
    c0 = int(round((tf.c - ctf.c) / 30))
    return slice(r0, r0 + shape[0] // FACTOR), slice(c0, c0 + shape[1] // FACTOR)


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2 = cfg["phase1"], cfg["phase2"]
    store = Path(p2["store"])
    prod, out = store / "phase5", cfg["paths"]["outputs"] / "phase5"
    prod.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    anc = cfg["paths"]["testbed"] / "s1"
    import rasterio
    with rasterio.open(anc / "aoi.tif") as s:
        county = (s.crs, s.transform, s.shape)
    tiles = sorted((store / "lidar_1m").glob("USGS_1M_*.tif"))
    grid = lidar_grid(tiles, county[1], county[0])
    win = coarse_window(grid, county)
    print(f"3 m grid {grid[2]} over {len(tiles)} lidar tiles; 30 m window rows {win[0]}, cols {win[1]}")

    dem_p = prod / "dem_3m.tif"
    if not dem_p.exists():
        s1rtc.write_grid(dem_p, mosaic_dem(tiles, grid), grid)
    dem = s1rtc.read_grid(dem_p)
    info = gauges.fetch_sites_by_id([p1["calibration_gauge"]])[p1["calibration_gauge"]]
    gr, gc = s1rtc.gauge_pixel(float(info["dec_long_va"]), float(info["dec_lat_va"]), grid)
    from rasterio.warp import transform_bounds
    fc = fm.nhd_river(transform_bounds(grid[0], "EPSG:4326", grid[1].c, grid[1].f - grid[2][0] * FINE,
                                       grid[1].c + grid[2][1] * FINE, grid[1].f), "Barren River",
                      cache=prod / "nhd_barren_river.geojson")
    channel = fm.channel_from_nhd(fc, grid, widen_px=3) & np.isfinite(dem)
    cy, cx = np.nonzero(channel)
    k = np.argmin(np.hypot(cy - gr, cx - gc))
    from scipy import ndimage
    n_pieces = ndimage.label(channel)[1]
    print(f"channel (USGS NHD Barren River, widened 9 m): {channel.sum()} px in {n_pieces} piece(s); "
          f"gauge {np.hypot(cy[k] - gr, cx[k] - gc) * FINE:.0f} m from it")
    wy, wx = cy, cx

    lvl_p = prod / "flood_level_3m.tif"
    surf = fm.river_surface(dem, channel, window_px=11)
    if not lvl_p.exists():
        fa = fm.flood_at(dem, surf, max_dist_px=int(2000 / FINE))
        s1rtc.write_grid(prod / "flood_at_3m.tif", fa, grid)
        s1rtc.write_grid(lvl_p, fm.connected_level(fa, channel), grid,
                         tags={"DESCRIPTION": "river rise (m above the lidar survey-day water surface) at which "
                                              "the pixel floods and is connected to the Barren River"})
    fa = s1rtc.read_grid(prod / "flood_at_3m.tif")
    lvl = s1rtc.read_grid(lvl_p)
    near = s1rtc.reach_mask(wy[k], wx[k], grid, 60) & np.isfinite(surf)
    z0 = float(np.nanmedian(surf[near]))
    alt = float(info["alt_va"])
    print(f"lidar river surface at the gauge {z0:.2f} m NAVD88 = gage height {z0 / FT - alt:.1f} ft")

    def dh(stage_ft, offset):
        return (stage_ft + alt) * FT - z0 + offset

    # ---- calibration against Sentinel-1 water on open fields ------------------------
    lc = s1rtc.read_grid(anc / "worldcover_2021.tif")[win]
    open_ = np.isin(lc, (30, 40))
    nr, nc = lvl.shape[0] // FACTOR, lvl.shape[1] // FACTOR
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            lvl_min30 = np.nanmin(lvl[:nr * FACTOR, :nc * FACTOR].reshape(nr, FACTOR, nc, FACTOR), axis=(1, 3))
    domain = open_ & np.isfinite(lvl_min30) & (lvl_min30 < 8)
    passes = pd.read_csv(store / "high_water_passes.csv")
    cut = float(pd.read_csv(cfg["paths"]["outputs"] / "phase2" / "per_pass.csv").loo_db.median())
    sar = []
    for r in passes.itertuples():
        stem = store / "s1" / f"{r.date}_T{int(r.track):03d}"
        vv = s1rtc.read_grid(Path(f"{stem}_VV_db.tif"))[win]
        valid = (s1rtc.read_grid(Path(f"{stem}_valid.tif")) == 1)[win]
        sar.append({"date": r.date, "stage": getattr(r, f"stage_{p1['calibration_gauge']}_ft"),
                    "wet": np.nan_to_num(vv, nan=99) < cut, "valid": valid & domain})
    offsets = np.round(np.arange(-2.0, 2.01, 0.1), 2)
    model_cache = {}

    def model30(d):
        key = round(d, 2)
        if key not in model_cache:
            model_cache[key] = fm.aggregate_fraction(lvl < d, FACTOR) >= 0.5
        return model_cache[key]

    conf = np.zeros((len(offsets), len(sar), 3), int)
    for i, o in enumerate(offsets):
        for j, s in enumerate(sar):
            conf[i, j] = s1rtc.confusion(model30(dh(s["stage"], o)), s["wet"], s["valid"])
    f1 = lambda c: s1rtc.scores(*c)[0]  # noqa: E731
    pooled_f1 = np.array([f1(conf[i].sum(0)) for i in range(len(offsets))])
    best = offsets[int(np.nanargmax(pooled_f1))]
    loo = []
    for j in range(len(sar)):
        others = np.array([f1(np.delete(conf[i], j, 0).sum(0)) for i in range(len(offsets))])
        oj = offsets[int(np.nanargmax(others))]
        loo.append({"date": sar[j]["date"], "stage_ft": sar[j]["stage"], "offset_m": oj,
                    "f1_heldout": f1(conf[list(offsets).index(oj), j]),
                    "f1_zero_offset": f1(conf[list(offsets).index(0.0), j])})
    loo = pd.DataFrame(loo)
    loo.to_csv(out / "calibration_loo.csv", index=False)

    # Agreement by distance from the gauge: the 'same rise everywhere' assumption holds near it.
    yy, xx = np.mgrid[:nr, :nc]
    dist_km = np.hypot(yy * FACTOR + FACTOR / 2 - gr, xx * FACTOR + FACTOR / 2 - gc) * FINE / 1000
    rings = [(0, 3), (3, 6), (6, 10), (10, 15)]
    ring_rows = []
    for a, b in rings:
        c = np.zeros(3, int)
        for sv in sar:
            m = model30(dh(sv["stage"], best))
            c += np.array(s1rtc.confusion(m, sv["wet"], sv["valid"] & (dist_km >= a) & (dist_km < b)))
        ring_rows.append((a, b, f1(c), int(c[0] + c[2])))
    pd.DataFrame(ring_rows, columns=["from_km", "to_km", "f1", "sar_water_cells"]).to_csv(out / "by_distance.csv",
                                                                                          index=False)

    # ---- independent optical check (14 Feb 2020) --------------------------------------
    hls = pd.read_csv(store / "hls_scenes.csv")
    hrow = hls.iloc[[i for i, f in enumerate(hls.file) if "20200214T1623" in f][0]]
    w = s1rtc.read_grid(store / "hls" / hrow.file)[win]
    clear = np.isin(w, (0, 1, 2)) & np.isfinite(lvl_min30) & (lvl_min30 < 8)
    hwet = np.isin(w, (1, 2))
    stage_hls = float(hrow[f"stage_{p1['calibration_gauge']}_ft_at_hls"])
    m_opt = model30(dh(stage_hls, best))
    opt_rows = []
    for nm, sel in (("all land", np.ones_like(clear)), ("tree cover", lc == 10), ("open fields", open_)):
        c = s1rtc.confusion(m_opt, hwet, clear & sel)
        opt_rows.append((nm, int((clear & sel).sum()), f1(c), c[0] / max(c[0] + c[2], 1), c[1] / max(c[0] + c[1], 1)))

    # ---- daily series and depth maps ---------------------------------------------------
    daily = pd.read_csv(cfg["paths"]["testbed"] / f"gauge_{p1['calibration_gauge']}.csv", parse_dates=["date"])
    daily = daily.dropna(subset=["stage_max_ft"])
    lv = np.sort(lvl[np.isfinite(lvl) & ~channel].ravel())
    daily["rise_m"] = dh(daily.stage_max_ft, best)
    daily["flooded_km2"] = np.searchsorted(lv, daily.rise_m.to_numpy()) * FINE * FINE / 1e6
    daily[["date", "stage_max_ft", "rise_m", "flooded_km2"]].to_csv(out / "daily_flooded_area.csv", index=False)
    top = daily.sort_values("stage_max_ft", ascending=False).head(200)
    picks, seen = [], set()            # the three highest days, at most one per month
    for r in top.itertuples():
        mkey = r.date.strftime("%Y-%m")
        if mkey not in seen:
            picks.append(r)
            seen.add(mkey)
        if len(picks) == 3:
            break
    depth_paths = []
    for r in picks:
        d = r.rise_m
        wet = (lvl < d) & ~channel
        dp = prod / f"depth_3m_{r.date:%Y-%m-%d}.tif"
        s1rtc.write_grid(dp, np.where(wet, d - fa, np.nan).astype("float32"), grid,
                         tags={"DESCRIPTION": f"flood depth (m), daily max stage {r.stage_max_ft:.2f} ft"})
        depth_paths.append((r, dp))

    lines = [f"Lidar: USGS 3DEP 1 m, KY_WesternKY_A22 ({len(tiles)} tiles), averaged to {FINE:.0f} m; "
             f"area {grid[2][0] * FINE / 1000:.1f} x {grid[2][1] * FINE / 1000:.1f} km",
             f"Lidar river surface at the gauge: {z0:.2f} m NAVD88 (= {z0 / FT - alt:.1f} ft gage height on the survey day)",
             "", f"Offset calibrated on Sentinel-1 water over open fields (16 passes): {best:+.1f} m "
             f"(pooled F1 {np.nanmax(pooled_f1):.2f}; zero offset {pooled_f1[list(offsets).index(0.0)]:.2f})",
             f"Leave-one-pass-out offsets {loo.offset_m.min():+.1f} to {loo.offset_m.max():+.1f} m; held-out F1 median "
             f"{loo.f1_heldout.median():.2f}",
             "Agreement with Sentinel-1 on open fields by distance from the gauge (calibrated offset):",
             *[f"  {a:2d}-{b:2d} km  F1 {f:.2f}  ({n} Sentinel-1 water cells)" for a, b, f, n in ring_rows],
             f"  -> maps are reliable within ~{cfg['phase5']['valid_km']} km of the gauge; further away the rise "
             "differs from the gauge's", "",
             f"Independent optical check, DSWx-HLS {hrow.hls_time_utc} UTC "
             f"(Barren {stage_hls:.1f} ft), cloud-free 30 m cells:"]
    for nm, n, f, det, fa_ in opt_rows:
        lines.append(f"  {nm:12s} {n:6d} cells | F1 {f:.2f} | optical water found by the model {det:.0%} | "
                     f"model water not seen by optical {fa_:.0%}")
    lines += ["", f"Daily flooded area outside the channel, {daily.date.min():%Y-%m-%d} to {daily.date.max():%Y-%m-%d}: "
              f"{(daily.flooded_km2 > 0.5).sum()} days above 0.5 km2; maximum {daily.flooded_km2.max():.2f} km2 "
              f"on {daily.loc[daily.flooded_km2.idxmax(), 'date']:%Y-%m-%d}",
              "Depth maps (3 m) written for: " + ", ".join(f"{r.date:%Y-%m-%d} ({r.stage_max_ft:.1f} ft, "
                                                           f"{r.flooded_km2:.2f} km2)" for r, _ in depth_paths)]
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    plot(daily, depth_paths, dem, offsets, pooled_f1, best, (gr, gc), cfg["phase5"]["valid_km"],
         out / "daily_maps.png")


def plot(daily, depth_paths, dem, offsets, pooled_f1, best, gauge_rc, valid_km, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(20, 10), constrained_layout=True)
    gs = fig.add_gridspec(2, 4)
    a = fig.add_subplot(gs[0, :3])
    a.plot(daily.date, daily.flooded_km2, lw=.8)
    a.set_ylabel("flooded area outside the river (km²)")
    a.set_title("Daily flood extent, Barren River at Bowling Green (gauge + 1 m lidar model)")
    b = fig.add_subplot(gs[0, 3])
    b.plot(offsets, pooled_f1)
    b.axvline(best, ls="--", color="grey")
    b.set_xlabel("offset added to the gauge rise (m)")
    b.set_ylabel("F1 vs Sentinel-1 water on open fields")
    b.set_title(f"Calibration: best offset {best:+.1f} m")
    sl = (slice(None, None, 4), slice(None, None, 4))
    for i, (r, p) in enumerate(depth_paths):
        ax = fig.add_subplot(gs[1, i])
        ax.imshow(dem[sl], cmap="gray", vmin=np.nanpercentile(dem, 2), vmax=np.nanpercentile(dem, 98))
        im = ax.imshow(s1rtc.read_grid(p)[sl], cmap="Blues", vmin=0, vmax=6)
        ax.add_patch(plt.Circle((gauge_rc[1] / 4, gauge_rc[0] / 4), valid_km * 1000 / FINE / 4, fill=False,
                                ec="#d62728", lw=1.5, ls="--"))
        ax.plot(gauge_rc[1] / 4, gauge_rc[0] / 4, "r^", ms=8)
        ax.set_title(f"{r.date:%d %b %Y}: {r.stage_max_ft:.1f} ft, {r.flooded_km2:.1f} km²\n"
                     f"red circle: reliable zone ({valid_km} km of the gauge)")
        ax.set_axis_off()
    fig.colorbar(im, ax=fig.axes[-1], shrink=.7, label="depth (m)")
    fig.savefig(path, dpi=100)


if __name__ == "__main__":
    main()
