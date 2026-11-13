"""Testbed phase 1b: Sentinel-1 water maps, gauge-based thresholding, DSWx-S1 comparison.

Run after t1_prepare_s1.py.

    python scripts/t1_analyse_s1.py

1. Gauge calibration: at the calibration gauge (Barren River at Bowling Green)
   the expected wet area on each date = ground below the gauge water surface,
   connected to the channel, within reach_radius_m. The VV (and VH) dB threshold
   that best reproduces it over all dates is chosen (pooled F1).
2. Independent check at the validation gauge (Drakes Creek near Alvaton),
   comparing the gauge-calibrated threshold with the automatic tile threshold.
3. County water maps for every date with both thresholds, compared with OPERA
   DSWx-S1 (open water + inundated vegetation) where both are valid.
4. Flood = water now, not water on the track's dry reference date, not JRC
   permanent water.

Outputs in outputs/<name>/phase1/: calibration.csv, gauge_check.csv,
dswx_comparison.csv, calibration.png, flood_maps.png, summary.txt
"""

import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from iceye_csda import gauges, s1rtc  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.flood import map_water  # noqa: E402


def load(cfg):
    p1 = cfg["phase1"]
    d = cfg["paths"]["testbed"] / "s1"
    st = {k: s1rtc.read_grid(d / f"{k}.tif") for k in ("dem", "hand", "slope", "jrc_occurrence")}
    st["aoi"] = s1rtc.read_grid(d / "aoi.tif") == 1
    dates = []
    for track, t in p1["tracks"].items():
        for day in t["dates"]:
            stem = d / f"{day}_T{int(track):03d}"
            if not (d / f"{stem.name}_VV_db.tif").exists():
                print("missing", stem.name)
                continue
            dates.append({
                "date": day, "track": int(track), "reference": t["reference"],
                "VV": s1rtc.read_grid(d / f"{stem.name}_VV_db.tif"),
                "VH": s1rtc.read_grid(d / f"{stem.name}_VH_db.tif"),
                "valid": s1rtc.read_grid(d / f"{stem.name}_valid.tif") == 1,
                "time": datetime.fromisoformat((d / f"{stem.name}_time.txt").read_text().strip()),
                "dswx": (s1rtc.read_grid(d / f"{day}_dswx_wtr.tif")
                         if (d / f"{day}_dswx_wtr.tif").exists() else None)})
    return st, dates


def gauge_setup(cfg, grid, st, site):
    p1 = cfg["phase1"]
    info = gauges.fetch_sites_by_id([site])[site]
    row, col = s1rtc.gauge_pixel(float(info["dec_long_va"]), float(info["dec_lat_va"]), grid)
    reach = s1rtc.reach_mask(row, col, grid, p1["reach_radius_m"], st["hand"],
                             p1["reach_hand_max_m"])
    channel = np.isfinite(st["jrc_occurrence"]) & (st["jrc_occurrence"] >= p1["channel_occurrence"])
    near = s1rtc.reach_mask(row, col, grid, 90)          # always seed at the gauge itself
    return {"info": info, "rc": (row, col), "reach": reach, "channel": channel | near}


def wse_at(site_info, when, cache):
    """Gauge WSE (NAVD88 m) and stage (ft) at the pass; cached in a JSON file."""
    import json

    key = f"{site_info['site_no']}_{when:%Y%m%dT%H%M}"
    store = json.loads(cache.read_text()) if cache.exists() else {}
    if key not in store:
        lv = gauges.fetch_levels([site_info["site_no"]], when, window_min=60)
        wse, param, note = gauges.gauge_wse_navd88(site_info, lv.get(site_info["site_no"], {}))
        stage = lv.get(site_info["site_no"], {}).get("00065", (None,))[0]
        store[key] = [wse, stage, note]
        cache.write_text(json.dumps(store, indent=1))
    wse, stage, note = store[key]
    return wse, (np.nan if stage is None else stage), note


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, out = cfg["phase1"], cfg["paths"]["outputs"] / "phase1"
    out.mkdir(parents=True, exist_ok=True)
    import rasterio
    with rasterio.open(cfg["paths"]["testbed"] / "s1" / "aoi.tif") as s:
        grid = (s.crs, s.transform, s.shape)
    px_km2 = abs(grid[1].a * grid[1].e) / 1e6
    st, dates = load(cfg)
    print(f"{len(dates)} Sentinel-1 dates loaded")

    cal = gauge_setup(cfg, grid, st, p1["calibration_gauge"])
    val = gauge_setup(cfg, grid, st, p1["validation_gauge"])
    for g in (cal, val):
        print(f"gauge {g['info']['site_no']} {g['info']['station_nm']}: datum "
              f"{g['info']['alt_va']} ft {g['info']['alt_datum_cd']}, reach "
              f"{g['reach'].sum()} px, channel px in reach {(g['channel'] & g['reach']).sum()}")

    # 1-2. gauge samples ---------------------------------------------------------
    samples = {"cal": [], "val": []}
    for d in dates:
        for key, g in (("cal", cal), ("val", val)):
            wse, stage, note = wse_at(g["info"], d["time"],
                                      cfg["paths"]["testbed"] / "gauge_wse_cache.json")
            if wse is None:
                print(f"   {d['date']} {g['info']['site_no']}: no WSE ({note})")
                continue
            truth = s1rtc.expected_wet(st["dem"], wse, g["reach"], g["channel"])
            valid = g["reach"] & d["valid"] & np.isfinite(st["dem"])
            samples[key].append({"date": d["date"], "track": d["track"], "stage_ft": stage,
                                 "wse_m": wse, "truth": truth, "valid": valid,
                                 "VV": d["VV"], "VH": d["VH"], "expected_px": int((truth & valid).sum())})
    t0, t1, dt = p1["thresholds_db"]
    grid_t = np.arange(t0, t1 + dt / 2, dt)
    best, curves = {}, {}
    for pol in ("VV", "VH"):
        ss = [{"db": s[pol], "truth": s["truth"], "valid": s["valid"]} for s in samples["cal"]]
        best[pol], curves[pol] = s1rtc.calibrate_threshold(ss, grid_t)
        for tr in sorted({s["track"] for s in samples["cal"]}):
            sub = [{"db": s[pol], "truth": s["truth"], "valid": s["valid"]}
                   for s in samples["cal"] if s["track"] == tr]
            best[f"{pol}_T{tr}"], _ = s1rtc.calibrate_threshold(sub, grid_t)
    # High-water only: at normal levels the channel is 1-3 pixels wide at 30 m and
    # nothing is resolvable, so the all-dates fit is pulled down by false alarms.
    high = {}
    for key in ("cal", "val"):
        hs = [{"db": s["VV"], "truth": s["truth"], "valid": s["valid"]} for s in samples[key]
              if s["stage_ft"] >= p1["high_stage_ft"]]
        if hs:
            b, r = s1rtc.calibrate_threshold(hs, grid_t)
            high[key] = (b, dict((x[0], x[1]) for x in r)[b], len(hs))
    pd.DataFrame([{"pol": pol, "threshold_db": r[0], "f1": r[1], "csi": r[2], "tp": r[3],
                   "fp": r[4], "fn": r[5]} for pol in curves for r in curves[pol]]).to_csv(
        out / "calibration.csv", index=False)
    print("gauge-calibrated thresholds (dB):", {k: round(v, 2) for k, v in best.items()})

    # 3. county maps + DSWx comparison -----------------------------------------
    T = best["VV"]
    maps, comp, auto_t = {}, [], {}
    ref_water = np.isfinite(st["jrc_occurrence"]) & (st["jrc_occurrence"] >= p1["channel_occurrence"])
    for d in dates:
        common = dict(hand=st["hand"], hand_max=cfg["flood"]["hand_max_m"], slope=st["slope"],
                      slope_max=cfg["flood"]["slope_max_deg"], min_pixels=5,
                      grow_db=cfg["flood"]["region_grow_db"])
        vv = np.where(d["valid"], d["VV"], np.nan)
        w_auto, info = map_water(vv, method="tiles", tile=p1["tile_px"], ref_water=ref_water,
                                 **common)
        w_gauge, _ = map_water(vv, method="fixed", threshold_db=T, **common)
        auto_t[d["date"]] = info["threshold_db"]
        maps[d["date"]] = {"auto": w_auto, "gauge": w_gauge, "valid": d["valid"],
                           "VV": d["VV"], "dswx": d["dswx"], "track": d["track"],
                           "reference": d["reference"]}
        row = {"date": d["date"], "track": d["track"], "auto_threshold_db": info["threshold_db"],
               "auto_method": info["method"], "auto_tiles": info.get("tiles_selected"),
               "gauge_threshold_db": T}
        if d["dswx"] is not None:
            dv = np.isin(d["dswx"], (0, 1, 3)) & d["valid"] & st["aoi"]
            dw = np.isin(d["dswx"], s1rtc.WTR_WATER)
            row["dswx_water_km2"] = (dw & dv).sum() * px_km2
            for name, w in (("auto", w_auto), ("gauge", w_gauge)):
                tp, fp, fn = s1rtc.confusion(w, dw, dv)
                f1, csi = s1rtc.scores(tp, fp, fn)
                row[f"{name}_water_km2"] = (w & dv).sum() * px_km2
                row[f"{name}_vs_dswx_f1"] = f1
                row[f"{name}_vs_dswx_iou"] = csi
        comp.append(row)
    comp = pd.DataFrame(comp)

    # flood (not water on the reference date, not permanent water)
    perm = np.isfinite(st["jrc_occurrence"]) & (st["jrc_occurrence"] >= cfg["flood"]["permanent_water_occurrence"])
    for day, m in maps.items():
        ref = maps.get(m["reference"])
        for name in ("auto", "gauge"):
            refw = ref[name] if ref is not None else np.zeros_like(perm)
            m[f"{name}_flood"] = m[name] & ~refw & ~perm & st["aoi"]
            comp.loc[comp.date == day, f"{name}_flood_km2"] = m[f"{name}_flood"].sum() * px_km2
        if m["dswx"] is not None and ref is not None and ref["dswx"] is not None:
            dfl = np.isin(m["dswx"], s1rtc.WTR_WATER) & ~np.isin(ref["dswx"], s1rtc.WTR_WATER) & ~perm & st["aoi"]
            m["dswx_flood"] = dfl
            comp.loc[comp.date == day, "dswx_flood_km2"] = dfl.sum() * px_km2
    comp.to_csv(out / "dswx_comparison.csv", index=False)

    # independent gauge check ----------------------------------------------------
    rows = []
    for key, ss in samples.items():
        for s in ss:
            m = maps[s["date"]]
            r = {"gauge": "calibration" if key == "cal" else "validation", "date": s["date"],
                 "track": s["track"], "stage_ft": s["stage_ft"], "wse_m": s["wse_m"],
                 "expected_px": s["expected_px"]}
            for name in ("auto", "gauge"):
                r[f"{name}_f1"] = s1rtc.scores(*s1rtc.confusion(m[name], s["truth"], s["valid"]))[0]
            if m["dswx"] is not None:
                r["dswx_f1"] = s1rtc.scores(*s1rtc.confusion(
                    np.isin(m["dswx"], s1rtc.WTR_WATER), s["truth"], s["valid"]))[0]
            rows.append(r)
    check = pd.DataFrame(rows)
    check.to_csv(out / "gauge_check.csv", index=False)

    pooled = {}
    for gname in ("calibration", "validation"):
        for name in ("auto", "gauge", "dswx"):
            tp = fp = fn = 0
            for s in samples["cal" if gname == "calibration" else "val"]:
                m = maps[s["date"]]
                if name == "dswx":
                    if m["dswx"] is None:
                        continue
                    pred = np.isin(m["dswx"], s1rtc.WTR_WATER)
                else:
                    pred = m[name]
                a, b, c = s1rtc.confusion(pred, s["truth"], s["valid"])
                tp, fp, fn = tp + a, fp + b, fn + c
            pooled[(gname, name)] = s1rtc.scores(tp, fp, fn)[0]

    lines = [f"Sentinel-1 dates: {len(dates)} (tracks {sorted({d['track'] for d in dates})})",
             f"gauge-calibrated threshold VV {best['VV']:.2f} dB, VH {best['VH']:.2f} dB; "
             f"per track: " + ", ".join(f"{k} {v:.2f}" for k, v in best.items() if "_T" in k),
             *[f"high-water dates only (stage >= {p1['high_stage_ft']} ft) at the "
               f"{'calibration' if k == 'cal' else 'validation'} gauge: VV {v[0]:.2f} dB "
               f"(F1 {v[1]:.2f}, {v[2]} dates)" for k, v in high.items()],
             f"automatic tile thresholds VV (tiles must straddle JRC water): "
             f"{min(auto_t.values()):.2f} to {max(auto_t.values()):.2f} dB",
             "", "F1 against the gauge-expected wet area (pooled over dates):"]
    for gname in ("calibration", "validation"):
        lines.append(f"  {gname:11s} gauge: auto {pooled[(gname, 'auto')]:.2f}  "
                     f"gauge-calibrated {pooled[(gname, 'gauge')]:.2f}  "
                     f"DSWx-S1 {pooled[(gname, 'dswx')]:.2f}")
    lines += ["", "Per date (county, km2; F1 vs DSWx-S1):"]
    for r in comp.itertuples():
        lines.append(f"  {r.date} T{r.track:03d} auto {r.auto_threshold_db:6.2f} dB | water "
                     f"auto {getattr(r, 'auto_water_km2', np.nan):6.1f} gauge "
                     f"{getattr(r, 'gauge_water_km2', np.nan):6.1f} dswx "
                     f"{getattr(r, 'dswx_water_km2', np.nan):6.1f} | F1 auto "
                     f"{getattr(r, 'auto_vs_dswx_f1', np.nan):.2f} gauge "
                     f"{getattr(r, 'gauge_vs_dswx_f1', np.nan):.2f} | flood auto "
                     f"{r.auto_flood_km2:5.1f} gauge {r.gauge_flood_km2:5.1f} dswx "
                     f"{getattr(r, 'dswx_flood_km2', np.nan):5.1f}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    plot_calibration(curves, best, auto_t, check, out / "calibration.png")
    plot_maps(maps, st, cfg, out / "flood_maps.png", cal["rc"], val["rc"])


def plot_calibration(curves, best, auto_t, check, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    for pol, c in curves.items():
        t = [r[0] for r in c]
        f = [r[1] for r in c]
        ax[0].plot(t, f, label=f"{pol} (best {best[pol]:.2f} dB)")
        ax[0].axvline(best[pol], ls=":", color="grey")
    for v in auto_t.values():
        ax[0].axvline(v, color="#d62728", alpha=0.25, lw=1)
    ax[0].set_xlabel("water threshold (dB, gamma0)")
    ax[0].set_ylabel("F1 vs gauge-expected wet area (pooled)")
    ax[0].set_title("Gauge-based threshold (Barren River at Bowling Green)\n"
                    "red lines: automatic tile thresholds per date")
    ax[0].legend()
    for gname, mk in (("calibration", "o"), ("validation", "s")):
        c = check[check.gauge == gname]
        for name, col in (("auto", "#d62728"), ("gauge", "#1f77b4"), ("dswx", "#2ca02c")):
            if f"{name}_f1" in c:
                ax[1].scatter(c["stage_ft"], c[f"{name}_f1"], marker=mk, color=col, s=28,
                              alpha=0.8, label=f"{name} @ {gname}")
    ax[1].set_xlabel("gage height at the pass (ft)")
    ax[1].set_ylabel("F1 vs gauge-expected wet area")
    ax[1].set_title("Per date: circles = calibration gauge, squares = validation gauge")
    ax[1].legend(fontsize=8, ncol=2)
    fig.savefig(path, dpi=110)


def plot_maps(maps, st, cfg, path, cal_rc, val_rc):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    days = [cfg["phase1"]["tracks"][121]["reference"]] + cfg["phase1"]["flood_dates"]
    days = [d for d in days if d in maps]
    fig, axes = plt.subplots(len(days), 4, figsize=(20, 5.2 * len(days)), constrained_layout=True)
    axes = np.atleast_2d(axes)
    cm = ListedColormap(["#f2efe6", "#1f77b4", "#ff7f0e", "#2ca02c"])
    outside = ~st["aoi"]
    for i, day in enumerate(days):
        m = maps[day]
        vv = np.where(outside, np.nan, m["VV"])
        axes[i, 0].imshow(vv, cmap="gray", vmin=-25, vmax=0)
        axes[i, 0].set_title(f"{day} VV gamma0 (dB)")
        for j, (key, title) in enumerate((("gauge", "gauge-calibrated water"),
                                          ("dswx", "OPERA DSWx-S1 water"))):
            if key == "dswx":
                w = np.isin(m["dswx"], s1rtc.WTR_WATER) if m["dswx"] is not None else None
            else:
                w = m[key]
            if w is None:
                continue
            img = np.where(w, 1.0, 0.0)
            img[outside] = np.nan
            axes[i, j + 1].imshow(img, cmap=ListedColormap(["#f2efe6", "#1f77b4"]), vmin=0, vmax=1,
                                  interpolation="nearest")
            axes[i, j + 1].set_title(f"{day} {title}")
        if m["dswx"] is not None:
            a, b = m["gauge"], np.isin(m["dswx"], s1rtc.WTR_WATER)
            agree = np.zeros(a.shape)
            agree[a & b] = 1
            agree[a & ~b] = 2
            agree[~a & b] = 3
            agree[outside] = np.nan
            axes[i, 3].imshow(agree, cmap=cm, vmin=-0.5, vmax=3.5, interpolation="nearest")
            axes[i, 3].set_title(f"{day} agreement\nblue both · orange ours only · green DSWx only")
        for a_ in axes[i]:
            a_.plot(cal_rc[1], cal_rc[0], "r^", ms=7)
            a_.plot(val_rc[1], val_rc[0], "ms", ms=6)
            a_.set_axis_off()
    fig.suptitle("Warren County, Sentinel-1 (OPERA RTC, 30 m) — red ▲ Barren R. gauge (calibration), "
                 "magenta ■ Drakes Cr. gauge (validation). Data: NASA/ESA OPERA, USGS.", fontsize=12)
    fig.savefig(path, dpi=90)


if __name__ == "__main__":
    main()
