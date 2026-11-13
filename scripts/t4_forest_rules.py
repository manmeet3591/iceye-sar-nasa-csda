"""Testbed phase 4b: can Sentinel-1 see flood under trees? Test VV, VH, VV/VH and their change.

Run after t2_calibrate.py, t4_prepare_references.py.

    python scripts/t4_forest_rules.py

Only wooded pixels (ESA WorldCover 2021 class 10) near each gauge, outside the river
channel. Label = flooded according to the gauge-expected wet area at the flood pass.
Signals are computed from 3 x 3-averaged linear backscatter, in dB:
    VV, VH, R = VV - VH, and dVV, dVH, dR = flood pass minus a dry pass on the same
    track (t4_prepare_references.py).
For each signal: AUC (how well it separates flooded from dry trees; 0.5 = not at all),
then the best threshold at Barren River (pooled F1), a leave-one-pair-out check, and
the same rule applied at Drakes Creek, which was never used to fit.

Outputs in outputs/<name>/phase4/: auc.csv, rules.csv, summary.txt, forest_rules.png
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from iceye_csda import gauges, s1rtc  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from t2_calibrate import reach  # noqa: E402

FT = 0.3048
SIGNALS = ("VV", "VH", "R", "dVV", "dVH", "dR")


def smooth_db(path):
    db = s1rtc.read_grid(path)
    lin = np.where(np.isfinite(db), 10 ** (db / 10), np.nan)
    ok = np.isfinite(lin).astype(float)
    num = ndimage.uniform_filter(np.nan_to_num(lin), 3)
    den = ndimage.uniform_filter(ok, 3)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > .5, 10 * np.log10(num / den), np.nan)


def auc(pos, neg):
    """Probability that a flooded pixel has a higher value than a dry one (Mann-Whitney)."""
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if not len(pos) or not len(neg):
        return np.nan
    allv = np.concatenate([pos, neg])
    ranks = pd.Series(allv).rank().to_numpy()
    return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def best_rule(values, labels, higher):
    """Threshold maximising F1 for 'flooded if value > t' (or < t). Returns (t, f1)."""
    v = values[np.isfinite(values)]
    if not v.size:
        return np.nan, np.nan
    best = (np.nan, -1)
    for t in np.percentile(v, np.arange(1, 100)):
        pred = values > t if higher else values < t
        f1 = s1rtc.scores(*s1rtc.confusion(pred, labels, np.isfinite(values)))[0]
        if f1 > best[1]:
            best = (float(t), f1)
    return best


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2 = cfg["phase1"], cfg["phase2"]
    store = Path(p2["store"])
    out = cfg["paths"]["outputs"] / "phase4"
    out.mkdir(parents=True, exist_ok=True)
    anc = cfg["paths"]["testbed"] / "s1"
    import rasterio
    with rasterio.open(anc / "aoi.tif") as s:
        grid = (s.crs, s.transform, s.shape)
    st = {"dem": s1rtc.read_grid(anc / "dem.tif"), "hand": s1rtc.read_grid(anc / "hand.tif"),
          "jrc": s1rtc.read_grid(anc / "jrc_occurrence.tif")}
    trees = s1rtc.read_grid(anc / "worldcover_2021.tif") == 10
    cut = float(pd.read_csv(cfg["paths"]["outputs"] / "phase2" / "per_pass.csv").loo_db.median())
    sites = [p1["calibration_gauge"], p1["validation_gauge"]]
    info = {s: gauges.fetch_sites_by_id([s])[s] for s in sites}
    reaches = {s: reach(cfg, st, grid, info[s]) for s in sites}
    passes = pd.read_csv(store / "high_water_passes.csv").set_index("date")
    pairs = pd.read_csv(store / "reference_pairs.csv")

    data = {s: [] for s in sites}          # per site: list of (pair id, label array, feature dict)
    for k, pr in enumerate(pairs.itertuples()):
        f = store / "s1" / f"{pr.flood_date}_T{int(pr.track):03d}"
        r = store / "s1" / f"{pr.ref_date}_T{int(pr.track):03d}"
        valid = (s1rtc.read_grid(Path(f"{f}_valid.tif")) == 1) & (s1rtc.read_grid(Path(f"{r}_valid.tif")) == 1)
        vv, vh = smooth_db(Path(f"{f}_VV_db.tif")), smooth_db(Path(f"{f}_VH_db.tif"))
        rvv, rvh = smooth_db(Path(f"{r}_VV_db.tif")), smooth_db(Path(f"{r}_VH_db.tif"))
        raw_vv = s1rtc.read_grid(Path(f"{f}_VV_db.tif"))
        feats = {"VV": vv, "VH": vh, "R": vv - vh, "dVV": vv - rvv, "dVH": vh - rvh, "dR": (vv - vh) - (rvv - rvh)}
        for s in sites:
            rch, ch = reaches[s]
            stage = passes.loc[pr.flood_date, f"stage_{s}_ft"]
            wse = (stage + float(info[s]["alt_va"])) * FT
            exp = s1rtc.expected_wet(st["dem"], wse, rch, ch)
            m = rch & ~ch & trees & valid & np.isfinite(st["dem"])
            data[s].append((k, exp[m], {n: a[m] for n, a in feats.items()}, raw_vv[m]))

    def pooled(s, keep=None):
        sel = [d for d in data[s] if keep is None or keep(d[0])]
        lab = np.concatenate([d[1] for d in sel])
        fe = {n: np.concatenate([d[2][n] for d in sel]) for n in SIGNALS}
        raw = np.concatenate([d[3] for d in sel])
        return lab, fe, raw

    cal, val = sites
    lab_c, fe_c, raw_c = pooled(cal)
    lab_v, fe_v, raw_v = pooled(val)
    auc_rows = []
    for n in SIGNALS:
        a_c = auc(fe_c[n][lab_c], fe_c[n][~lab_c])
        a_v = auc(fe_v[n][lab_v], fe_v[n][~lab_v])
        auc_rows.append({"signal": n, "auc_barren": a_c, "auc_drakes": a_v,
                         "flooded_higher": a_c > .5,
                         "median_flooded_barren": float(np.nanmedian(fe_c[n][lab_c])),
                         "median_dry_barren": float(np.nanmedian(fe_c[n][~lab_c]))})
    aucdf = pd.DataFrame(auc_rows)
    aucdf["separation"] = (aucdf.auc_barren - .5).abs()
    aucdf.to_csv(out / "auc.csv", index=False)

    rule_rows = []
    base_c = s1rtc.confusion(np.nan_to_num(raw_c, nan=99) < cut, lab_c, np.ones_like(lab_c))
    base_v = s1rtc.confusion(np.nan_to_num(raw_v, nan=99) < cut, lab_v, np.ones_like(lab_v))
    rule_rows.append({"rule": f"dark: VV < {cut:.2f} dB (phase 2)", "threshold": cut,
                      "barren_f1": s1rtc.scores(*base_c)[0], "barren_detect": base_c[0] / max(lab_c.sum(), 1),
                      "barren_false_alarm": base_c[1] / max((~lab_c).sum(), 1),
                      "drakes_f1": s1rtc.scores(*base_v)[0], "drakes_detect": base_v[0] / max(lab_v.sum(), 1),
                      "drakes_false_alarm": base_v[1] / max((~lab_v).sum(), 1), "loo_f1_median": np.nan})
    for r in aucdf.sort_values("separation", ascending=False).itertuples():
        hi = bool(r.flooded_higher)
        t, f1 = best_rule(fe_c[r.signal], lab_c, hi)
        loo = []
        for k in range(len(pairs)):
            lt, lf, _ = pooled(cal, lambda i: i != k)
            tt, _ = best_rule(lf[r.signal], lt, hi)
            held = [d for d in data[cal] if d[0] == k]
            if held and held[0][1].sum() >= 20:
                v = held[0][2][r.signal]
                pred = v > tt if hi else v < tt
                loo.append(s1rtc.scores(*s1rtc.confusion(pred, held[0][1], np.isfinite(v)))[0])
        pv = fe_v[r.signal] > t if hi else fe_v[r.signal] < t
        pc = fe_c[r.signal] > t if hi else fe_c[r.signal] < t
        cc = s1rtc.confusion(pc, lab_c, np.isfinite(fe_c[r.signal]))
        cv = s1rtc.confusion(pv, lab_v, np.isfinite(fe_v[r.signal]))
        rule_rows.append({"rule": f"{r.signal} {'>' if hi else '<'} {t:.2f} dB", "threshold": t,
                          "barren_f1": f1, "barren_detect": cc[0] / max(lab_c.sum(), 1),
                          "barren_false_alarm": cc[1] / max((~lab_c).sum(), 1),
                          "drakes_f1": s1rtc.scores(*cv)[0], "drakes_detect": cv[0] / max(lab_v.sum(), 1),
                          "drakes_false_alarm": cv[1] / max((~lab_v).sum(), 1),
                          "loo_f1_median": float(np.median(loo)) if loo else np.nan})
    rules = pd.DataFrame(rule_rows)
    rules.to_csv(out / "rules.csv", index=False)

    lines = [f"Flood/dry pass pairs: {len(pairs)} (same track, dry pass within "
             f"{cfg['phase4']['max_gap_days']} days, both gauges <= {cfg['phase4']['dry_max_ft']} ft)",
             f"Wooded floodplain pixels: Barren River {lab_c.size} ({lab_c.sum()} expected flooded), "
             f"Drakes Creek {lab_v.size} ({lab_v.sum()} expected flooded)", "",
             "How well each signal separates flooded from dry trees (AUC; 0.5 = not at all, 1 = perfectly):"]
    for r in aucdf.sort_values("separation", ascending=False).itertuples():
        lines.append(f"  {r.signal:4s} Barren {r.auc_barren:.2f}  Drakes {r.auc_drakes:.2f}  "
                     f"({'higher' if r.flooded_higher else 'lower'} when flooded; median flooded "
                     f"{r.median_flooded_barren:+.1f} vs dry {r.median_dry_barren:+.1f} dB)")
    lines += ["", "Rules (fit at Barren River; Drakes Creek never used):",
              "  rule                          | Barren F1 detect false | LOO F1 | Drakes F1 detect false"]
    for r in rules.itertuples():
        lines.append(f"  {r.rule:29s} | {r.barren_f1:9.2f} {r.barren_detect:6.0%} {r.barren_false_alarm:5.0%} | "
                     f"{r.loo_f1_median:6.2f} | {r.drakes_f1:9.2f} {r.drakes_detect:6.0%} {r.drakes_false_alarm:5.0%}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    plot(fe_c, lab_c, aucdf, rules, out / "forest_rules.png")


def plot(fe, lab, aucdf, rules, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = aucdf.sort_values("separation", ascending=False).signal.tolist()[:3]
    fig, ax = plt.subplots(1, 4, figsize=(22, 5), constrained_layout=True)
    for a, n in zip(ax[:3], top):
        v = fe[n]
        bins = np.linspace(np.nanpercentile(v, 1), np.nanpercentile(v, 99), 50)
        a.hist(v[~lab & np.isfinite(v)], bins, density=True, alpha=.6, label="dry trees")
        a.hist(v[lab & np.isfinite(v)], bins, density=True, alpha=.6, label="flooded trees (gauge)")
        a.set_title(f"{n} · AUC {aucdf.set_index('signal').auc_barren[n]:.2f} (Barren River)")
        a.set_xlabel("dB")
        a.legend(fontsize=8)
    d = rules
    y = np.arange(len(d))
    ax[3].barh(y + .2, d.barren_detect * 100, height=.38, label="flooded trees found (Barren)")
    ax[3].barh(y - .2, d.drakes_detect * 100, height=.38, label="flooded trees found (Drakes, independent)")
    ax[3].set_yticks(y, d.rule, fontsize=8)
    ax[3].set_xlabel("%")
    ax[3].set_title("Detection of flooded trees by rule")
    ax[3].legend(fontsize=8)
    fig.savefig(path, dpi=105)


if __name__ == "__main__":
    main()
