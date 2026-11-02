"""Testbed phase 2b: calibrate the SAR water cut-off on every high-water pass since 2016.

Run after t2_prepare_passes.py.

    python scripts/t2_calibrate.py

For each pass the gauge water level at the pass time (+ gauge datum, NAVD88) and
the DEM give the expected wet area near the gauge (see s1rtc.expected_wet). Then:
  - each pass's own best cut-off (what a perfect calibration could achieve)
  - one pooled cut-off per track and for both tracks
  - leave-one-pass-out: calibrate on all other passes, apply to the held-out one;
    the drop from its own best F1 is the honest cost of using a single cut-off
  - the same cut-off checked at the second gauge (Drakes Creek), never used to fit

  - which floodplain pixels the cut-off misses, by land cover (ESA WorldCover 2021)

Outputs in outputs/<name>/phase2/: per_pass.csv, landcover.csv, summary.txt, calibration.png
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from iceye_csda import gauges, s1rtc  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.flood import tile_threshold  # noqa: E402

FT = 0.3048
WORLDCOVER = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
              "ESA_WorldCover_10m_2021_v200_N36W087_Map.tif")
LC_NAMES = {10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built-up",
            60: "bare", 80: "water", 90: "herbaceous wetland"}


def worldcover(path, grid):
    """ESA WorldCover 2021 (10 m) on the 30 m grid by majority; cached. Tile covers 36-39 N, 87-84 W."""
    if path.exists():
        return s1rtc.read_grid(path).astype("uint8")
    import rasterio
    from rasterio.warp import Resampling, reproject
    lc = np.zeros(grid[2], "uint8")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open("/vsicurl/" + WORLDCOVER) as src:
            reproject(rasterio.band(src, 1), lc, dst_transform=grid[1], dst_crs=grid[0],
                      resampling=Resampling.mode)
    s1rtc.write_grid(path, lc, grid, nodata=0, dtype="uint8")
    return lc


def reach(cfg, st, grid, site_info):
    p1 = cfg["phase1"]
    row, col = s1rtc.gauge_pixel(float(site_info["dec_long_va"]), float(site_info["dec_lat_va"]), grid)
    r = s1rtc.reach_mask(row, col, grid, p1["reach_radius_m"], st["hand"], p1["reach_hand_max_m"])
    ch = np.isfinite(st["jrc"]) & (st["jrc"] >= p1["channel_occurrence"])
    return r, ch | s1rtc.reach_mask(row, col, grid, 90)


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2 = cfg["phase1"], cfg["phase2"]
    store = Path(p2["store"])
    out = cfg["paths"]["outputs"] / "phase2"
    out.mkdir(parents=True, exist_ok=True)
    anc = cfg["paths"]["testbed"] / "s1"
    import rasterio
    with rasterio.open(anc / "aoi.tif") as s:
        grid = (s.crs, s.transform, s.shape)
    st = {"dem": s1rtc.read_grid(anc / "dem.tif"), "hand": s1rtc.read_grid(anc / "hand.tif"),
          "jrc": s1rtc.read_grid(anc / "jrc_occurrence.tif")}
    ref_water = np.isfinite(st["jrc"]) & (st["jrc"] >= p1["channel_occurrence"])
    sites = {s: gauges.fetch_sites_by_id([s])[s] for s in (p1["calibration_gauge"], p1["validation_gauge"])}
    reaches = {s: reach(cfg, st, grid, info) for s, info in sites.items()}
    t0, t1, dt = p1["thresholds_db"]
    T = np.arange(t0, t1 + dt / 2, dt)

    passes = pd.read_csv(store / "high_water_passes.csv")
    samples = []
    for r in passes.itertuples():
        stem = store / "s1" / f"{r.date}_T{int(r.track):03d}"
        vv = s1rtc.read_grid(Path(f"{stem}_VV_db.tif"))
        valid = s1rtc.read_grid(Path(f"{stem}_valid.tif")) == 1
        dswx_p = store / "s1" / f"{r.date}_dswx_wtr.tif"
        dswx = s1rtc.read_grid(dswx_p) if dswx_p.exists() else None
        auto_t, _ = tile_threshold(np.where(valid, vv, np.nan), tile=p1["tile_px"], ref_water=ref_water)
        s = {"date": r.date, "track": int(r.track), "vv": vv, "auto_t": auto_t, "dswx": dswx}
        for site, info in sites.items():
            stage = getattr(r, f"stage_{site}_ft")
            wse = (stage + float(info["alt_va"])) * FT          # both gauges use NAVD88 datums
            rch, ch = reaches[site]
            s[site] = {"stage": stage, "truth": s1rtc.expected_wet(st["dem"], wse, rch, ch),
                       "valid": rch & valid & np.isfinite(st["dem"])}
            s[site]["expected_px"] = int((s[site]["truth"] & s[site]["valid"]).sum())
        samples.append(s)

    cal, val = p1["calibration_gauge"], p1["validation_gauge"]

    def fit(subset, site):
        return s1rtc.calibrate_threshold(
            [{"db": x["vv"], "truth": x[site]["truth"], "valid": x[site]["valid"]} for x in subset], T)

    def f1_at(x, site, thr):
        return s1rtc.scores(*s1rtc.confusion(np.nan_to_num(x["vv"], nan=99.0) < thr, x[site]["truth"],
                                             x[site]["valid"]))[0]

    pooled, _ = fit(samples, cal)
    per_track = {tr: fit([x for x in samples if x["track"] == tr], cal)[0]
                 for tr in sorted({x["track"] for x in samples})}
    rows = []
    for i, x in enumerate(samples):
        own_best, curve = fit([x], cal)
        loo_t, _ = fit([y for j, y in enumerate(samples) if j != i], cal)
        loo_track_t, _ = fit([y for j, y in enumerate(samples) if j != i and y["track"] == x["track"]] or
                             [y for j, y in enumerate(samples) if j != i], cal)
        row = {"date": x["date"], "track": x["track"],
               "barren_ft": round(x[cal]["stage"], 2), "drakes_ft": round(x[val]["stage"], 2),
               "expected_px_barren": x[cal]["expected_px"], "expected_px_drakes": x[val]["expected_px"],
               "own_best_db": own_best, "f1_own_best": f1_at(x, cal, own_best),
               "loo_db": loo_t, "f1_loo": f1_at(x, cal, loo_t),
               "loo_same_track_db": loo_track_t, "f1_loo_same_track": f1_at(x, cal, loo_track_t),
               "auto_db": x["auto_t"], "f1_auto": f1_at(x, cal, x["auto_t"]),
               "drakes_f1_pooled": f1_at(x, val, pooled), "drakes_own_best_db": fit([x], val)[0]}
        row["drakes_f1_own_best"] = f1_at(x, val, row["drakes_own_best_db"])
        if x["dswx"] is not None:
            for site, key in ((cal, "dswx_f1_barren"), (val, "dswx_f1_drakes")):
                row[key] = s1rtc.scores(*s1rtc.confusion(np.isin(x["dswx"], s1rtc.WTR_WATER),
                                                         x[site]["truth"], x[site]["valid"]))[0]
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(out / "per_pass.csv", index=False)

    # Which expected-wet floodplain pixels does the pooled cut-off miss, and where?
    lc = worldcover(anc / "worldcover_2021.tif", grid)
    rch, ch = reaches[cal]
    vals, lcs = [], []
    for x in samples:
        m = x[cal]["truth"] & x[cal]["valid"] & ~ch          # outside the permanent channel
        vals.append(x["vv"][m])
        lcs.append(lc[m])
    vw, lw = np.concatenate(vals), np.concatenate(lcs)
    lc_rows = []
    for k, nm in LC_NAMES.items():
        sel = lw == k
        if sel.sum() >= 20:
            lc_rows.append({"land_cover": nm, "pixels": int(sel.sum()), "share": sel.mean(),
                            "detected": float(np.mean(vw[sel] < pooled)), "vv_median_db": float(np.median(vw[sel]))})
    lcdf = pd.DataFrame(lc_rows)
    lcdf.to_csv(out / "landcover.csv", index=False)

    usable = df[df.expected_px_barren >= 50]
    lines = [f"High-water passes (a gauge >= {p2['min_stage_ft']} ft at the pass): {len(df)} "
             f"({', '.join(f'T{t}: {n}' for t, n in df.track.value_counts().sort_index().items())})",
             f"Pooled cut-off (Barren River, all passes): {pooled:.2f} dB;  per track: "
             + ", ".join(f"T{t} {v:.2f}" for t, v in per_track.items()) + " dB",
             f"Each pass's own best cut-off: median {df.own_best_db.median():.2f} dB, "
             f"range {df.own_best_db.min():.2f} to {df.own_best_db.max():.2f} dB",
             f"Leave-one-pass-out cut-offs: {df.loo_db.min():.2f} to {df.loo_db.max():.2f} dB", "",
             f"F1 at Barren River (passes with >= 50 expected wet pixels: {len(usable)}):",
             f"  own best (upper bound)     median {usable.f1_own_best.median():.2f}",
             f"  leave-one-pass-out         median {usable.f1_loo.median():.2f}",
             f"  leave-one-out, same track  median {usable.f1_loo_same_track.median():.2f}",
             f"  automatic tile cut-off     median {usable.f1_auto.median():.2f}", "",
             f"Drakes Creek (never used to fit): pooled Barren cut-off F1 median "
             f"{df.drakes_f1_pooled[df.expected_px_drakes >= 50].median():.2f} vs its own best "
             f"{df.drakes_f1_own_best[df.expected_px_drakes >= 50].median():.2f} "
             f"({int((df.expected_px_drakes >= 50).sum())} passes with >= 50 expected wet pixels)", ""]
    lines.append(f"Expected-wet floodplain pixels at Barren River (outside the channel, all passes): {vw.size}; "
                 f"detected at {pooled:.2f} dB: {np.mean(vw < pooled):.0%}")
    for r in lcdf.itertuples():
        lines.append(f"  {r.land_cover:18s} {r.share:5.0%} of pixels | detected {r.detected:4.0%} | VV median "
                     f"{r.vv_median_db:6.1f} dB")
    lines.append("")
    lines.append("Per pass (Barren ft | expected px | own best dB, F1 | LOO dB, F1 | auto dB, F1):")
    for r in df.itertuples():
        lines.append(f"  {r.date} T{r.track:03d} {r.barren_ft:5.1f} ft | {r.expected_px_barren:5d} | "
                     f"{r.own_best_db:6.2f} {r.f1_own_best:.2f} | {r.loo_db:6.2f} {r.f1_loo:.2f} | "
                     f"{r.auto_db:6.2f} {r.f1_auto:.2f}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    plot(df, pooled, lcdf, out / "calibration.png")


def plot(df, pooled, lcdf, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(21, 5.5), constrained_layout=True,
                           gridspec_kw={"width_ratios": [1, 1.3, .9]})
    for tr, mk in ((19, "o"), (121, "s")):
        d = df[df.track == tr]
        sz = 20 + d.expected_px_barren.clip(upper=1500) / 10
        ax[0].scatter(d.barren_ft, d.own_best_db, s=sz, marker=mk, alpha=.8, label=f"track {tr}")
    ax[0].axhline(pooled, ls="--", color="grey", label=f"pooled {pooled:.2f} dB")
    ax[0].set_xlabel("Barren River gage height at the pass (ft)")
    ax[0].set_ylabel("best cut-off for that pass (dB, VV)")
    ax[0].set_title("Each pass's own best cut-off (marker size = expected wet area)")
    ax[0].legend()
    x = np.arange(len(df))
    for k, (col, lab) in enumerate((("f1_own_best", "own best (upper bound)"),
                                    ("f1_loo", "leave-one-pass-out"), ("f1_auto", "automatic tile"))):
        ax[1].bar(x + (k - 1) * .27, df[col], width=.27, label=lab)
    ax[1].set_xticks(x, [f"{d[2:]}\nT{t}" for d, t in zip(df.date, df.track)], fontsize=7)
    ax[1].set_ylabel("F1 vs gauge-expected wet area (Barren River)")
    ax[1].set_title("How much is lost by using one cut-off for every pass")
    ax[1].legend(fontsize=8)
    d = lcdf.sort_values("share")
    ax[2].barh(d.land_cover, d.share * 100, color="#B9AFA0", label="share of expected flood")
    ax[2].barh(d.land_cover, d.share * d.detected * 100, color="#1f77b4", label="detected by Sentinel-1")
    for y_, r in enumerate(d.itertuples()):
        ax[2].text(r.share * 100 + 1, y_, f"{r.detected:.0%} detected", va="center", fontsize=9)
    ax[2].set_xlabel("% of expected-wet floodplain pixels (all passes)")
    ax[2].set_title(f"Where the {pooled:.2f} dB cut-off finds water (ESA WorldCover 2021)")
    ax[2].legend(fontsize=8, loc="lower right")
    fig.savefig(path, dpi=110)


if __name__ == "__main__":
    main()
