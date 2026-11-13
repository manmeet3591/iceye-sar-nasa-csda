"""Testbed phase 3b: optical QA of the Sentinel-1 water maps with OPERA DSWx-HLS.

Run after t2_calibrate.py and t3_prepare_hls.py.

    python scripts/t3_optical_qa.py

DSWx-HLS WTR classes (from the files' colour tables): 0 not water, 1 open water,
2 partial surface water, 252 snow/ice, 253 cloud/cloud shadow, 255 no data.
Only cloud-free pixels (0, 1, 2) are used, and only scenes with at least
phase3.min_clear of the Barren River reach cloud-free.

Questions, near the Barren River gauge:
  1. Is the gauge-expected wet area right? (optical water vs expected area at the
     optical overpass time, using the gauge level at that time)
  2. Where radar and optical disagree, by land cover (ESA WorldCover 2021)
  3. Of the wooded pixels the gauge expects wet but radar misses, how many does
     optical see as water?

Outputs in outputs/<name>/phase3/: scenes.csv, landcover.csv, summary.txt, optical_qa.png
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from iceye_csda import gauges, s1rtc  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from t2_calibrate import LC_NAMES, reach  # noqa: E402

FT = 0.3048
CLEAR = (0, 1, 2)
WATER = (1, 2)


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2, p3 = cfg["phase1"], cfg["phase2"], cfg["phase3"]
    store = Path(p2["store"])
    out = cfg["paths"]["outputs"] / "phase3"
    out.mkdir(parents=True, exist_ok=True)
    anc = cfg["paths"]["testbed"] / "s1"
    import rasterio
    with rasterio.open(anc / "aoi.tif") as s:
        grid = (s.crs, s.transform, s.shape)
    st = {"dem": s1rtc.read_grid(anc / "dem.tif"), "hand": s1rtc.read_grid(anc / "hand.tif"),
          "jrc": s1rtc.read_grid(anc / "jrc_occurrence.tif")}
    lc = s1rtc.read_grid(anc / "worldcover_2021.tif").astype("uint8")
    cal = p1["calibration_gauge"]
    info = gauges.fetch_sites_by_id([cal])[cal]
    rch, ch = reach(cfg, st, grid, info)
    cut = float(pd.read_csv(cfg["paths"]["outputs"] / "phase2" / "summary.txt", sep="\t", header=None)
                .iloc[1, 0].split("all passes): ")[1].split(" dB")[0])
    scenes = pd.read_csv(store / "hls_scenes.csv")

    rows, pooled = [], {"lc": [], "sar": [], "hls": [], "exp": []}
    for r in scenes.itertuples():
        w = s1rtc.read_grid(store / "hls" / r.file)
        clear = np.isin(w, CLEAR)
        frac_clear = clear[rch].mean()
        row = {"pass_date": r.pass_date, "track": r.track, "hls_time_utc": r.hls_time_utc,
               "clear_in_reach": round(float(frac_clear), 3),
               "barren_ft_hls": getattr(r, f"stage_{cal}_ft_at_hls"),
               "barren_ft_sar": getattr(r, f"stage_{cal}_ft_at_sar")}
        if frac_clear < p3["min_clear"]:
            rows.append(row | {"used": False})
            continue
        stem = store / "s1" / f"{r.pass_date}_T{int(r.track):03d}"
        vv = s1rtc.read_grid(Path(f"{stem}_VV_db.tif"))
        valid = s1rtc.read_grid(Path(f"{stem}_valid.tif")) == 1
        sar = np.nan_to_num(vv, nan=99.0) < cut
        hls = np.isin(w, WATER)
        wse = (row["barren_ft_hls"] + float(info["alt_va"])) * FT
        exp = s1rtc.expected_wet(st["dem"], wse, rch, ch)
        m = rch & clear & valid & np.isfinite(st["dem"])
        f1_hls_exp = s1rtc.scores(*s1rtc.confusion(hls, exp, m))[0]
        f1_sar_hls = s1rtc.scores(*s1rtc.confusion(sar, hls, m))[0]
        fp = m & ~ch
        rows.append(row | {"used": True, "pixels": int(m.sum()), "expected_wet_px": int((exp & m).sum()),
                           "hls_water_px": int((hls & m).sum()), "sar_water_px": int((sar & m).sum()),
                           "f1_hls_vs_expected": f1_hls_exp, "f1_sar_vs_hls": f1_sar_hls})
        pooled["lc"].append(lc[fp])
        pooled["sar"].append(sar[fp])
        pooled["hls"].append(hls[fp])
        pooled["exp"].append(exp[fp])
    df = pd.DataFrame(rows)
    df.to_csv(out / "scenes.csv", index=False)
    used = df[df.used]

    L, S, H, E = (np.concatenate(pooled[k]) for k in ("lc", "sar", "hls", "exp"))
    lc_rows = []
    for k, nm in LC_NAMES.items():
        sel = L == k
        if sel.sum() < 20:
            continue
        e = sel & E
        missed = e & ~S
        lc_rows.append({"land_cover": nm, "pixels": int(sel.sum()), "expected_wet": int(e.sum()),
                        "sar_detects_expected": float(S[e].mean()) if e.any() else np.nan,
                        "hls_detects_expected": float(H[e].mean()) if e.any() else np.nan,
                        "hls_water_where_sar_missed": float(H[missed].mean()) if missed.any() else np.nan,
                        "sar_water_outside_expected": float(S[sel & ~E].mean()),
                        "hls_water_outside_expected": float(H[sel & ~E].mean())})
    lcdf = pd.DataFrame(lc_rows)
    lcdf.to_csv(out / "landcover.csv", index=False)

    lines = [f"DSWx-HLS scenes within a day of a high-water pass: {len(df)} (on {df.pass_date.nunique()} passes); "
             f"usable (>= {p3['min_clear']:.0%} of the Barren reach cloud-free): {len(used)}",
             f"Radar cut-off from phase 2: {cut:.2f} dB (VV)", ""]
    for r in df.itertuples():
        txt = (f"  {r.pass_date} T{r.track:03d} | HLS {r.hls_time_utc} | clear {r.clear_in_reach:4.0%} | "
               f"Barren {r.barren_ft_hls:.1f} ft at HLS, {r.barren_ft_sar:.1f} ft at radar")
        if r.used:
            txt += (f" | expected {r.expected_wet_px} px, optical water {r.hls_water_px}, radar water "
                    f"{r.sar_water_px} | F1 optical-vs-expected {r.f1_hls_vs_expected:.2f}, "
                    f"radar-vs-optical {r.f1_sar_vs_hls:.2f}")
        else:
            txt += " | too cloudy"
        lines.append(txt)
    lines += ["", "Pooled over usable scenes, floodplain pixels near the gauge (outside the channel):",
              "  land cover         | expected wet px | radar finds | optical finds | optical water where radar missed"]
    for r in lcdf.itertuples():
        lines.append(f"  {r.land_cover:18s} | {r.expected_wet:15d} | {r.sar_detects_expected:11.0%} | "
                     f"{r.hls_detects_expected:13.0%} | {r.hls_water_where_sar_missed:.0%}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    plot(lcdf, used, out / "optical_qa.png")


def plot(lcdf, used, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(15, 5.2), constrained_layout=True)
    d = lcdf[lcdf.expected_wet >= 20].sort_values("expected_wet")
    y = np.arange(len(d))
    ax[0].barh(y + .2, d.sar_detects_expected * 100, height=.38, label="radar (Sentinel-1, VV cut-off)")
    ax[0].barh(y - .2, d.hls_detects_expected * 100, height=.38, label="optical (DSWx-HLS, clear pixels)")
    ax[0].set_yticks(y, [f"{a} ({b} px)" for a, b in zip(d.land_cover, d.expected_wet)])
    ax[0].set_xlabel("% of gauge-expected wet pixels seen as water")
    ax[0].set_title("Who sees the expected flood, by land cover")
    ax[0].legend(fontsize=8, loc="lower right")
    x = np.arange(len(used))
    ax[1].bar(x - .2, used.f1_hls_vs_expected, width=.4, label="optical vs gauge-expected")
    ax[1].bar(x + .2, used.f1_sar_vs_hls, width=.4, label="radar vs optical")
    ax[1].set_xticks(x, [f"optical {t[:10]} {t[11:]} UTC ({b:.1f} ft)\nradar {p} T{k} ({c:.1f} ft)"
                         for p, t, b, k, c in zip(used.pass_date, used.hls_time_utc, used.barren_ft_hls,
                                                  used.track, used.barren_ft_sar)], fontsize=8)
    ax[1].set_ylabel("F1 (cloud-free pixels near the Barren River gauge)")
    ax[1].set_title("Per usable optical scene")
    ax[1].legend(fontsize=8)
    fig.savefig(path, dpi=110)


if __name__ == "__main__":
    main()
