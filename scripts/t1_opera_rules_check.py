"""Testbed check: apply OPERA DSWx-S1 rules (opera-adt/DSWX-SAR d9ae8ed defaults) to real data.

Reads the phase-1 grids for 2025-02-17 (track 121) and writes
data/testbed/warren/opera_rules_example.json: OPERA-formula slope vs standard slope
for the county, KI threshold of a 3 km tile around the Barren River gauge, fuzzy
scores for an OPERA open-water pixel, and real VV/VH at flooded-vegetation and
dark pixels.

    python scripts/t1_opera_rules_check.py data/testbed/warren/opera_rules_example.json

OPERA does not publish its local thresholds, so the radar scores here use one
tile only and are an approximation; terrain and history scores are exact.
"""
import json, sys
import numpy as np
from scipy import ndimage
sys.path.insert(0, "src")
from iceye_csda.s1rtc import read_grid, gauge_pixel
from iceye_csda import gauges
import rasterio

d = "data/testbed/warren/s1/"
day = "2025-02-17_T121"
vv, vh = read_grid(d + day + "_VV_db.tif"), read_grid(d + day + "_VH_db.tif")
hand, dem, jrc = read_grid(d + "hand.tif"), read_grid(d + "dem.tif"), read_grid(d + "jrc_occurrence.tif")
dswx = read_grid(d + "2025-02-17_dswx_wtr.tif")
with rasterio.open(d + "aoi.tif") as s:
    grid = (s.crs, s.transform, s.shape)
o = np.nan_to_num(jrc) / 100.0

# OPERA slope, exactly as written (Sobel 3x3, / (3 * 30 m))
k = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], float)
sx, sy = ndimage.convolve(dem, k), ndimage.convolve(dem, k.T)
slope_opera = np.degrees(np.arctan(np.hypot(sx / 3 / 30, sy / 3 / 30)))
slope_true = np.degrees(np.arctan(np.hypot(sx / 8 / 30, sy / 8 / 30)))

info = gauges.fetch_sites_by_id(["03314500"])["03314500"]
gr, gc = gauge_pixel(float(info["dec_long_va"]), float(info["dec_lat_va"]), grid)
T = 100   # 100 x 100 px tile (3 km), inside OPERA's 400 -> 40 px search range
r0, c0 = gr - T // 2, gc - T // 2
sl = (slice(r0, r0 + T), slice(c0, c0 + T))

def ki(db_vals, lo=-30, hi=5, nbins=1000):
    """OPERA compute_ki_threshold: J = P1 ln s1 + P2 ln s2 - P1 ln P1 - P2 ln P2 (density histogram)."""
    v = db_vals[np.isfinite(db_vals)]
    cnt, edges = np.histogram(v, bins=np.linspace(lo, hi, nbins + 1), density=True)
    b = edges[:-1]
    cs = np.cumsum(cnt); cs = np.where(cs <= 0, 1e-10, cs)
    m1, s1 = np.cumsum(cnt * b), np.cumsum(cnt * b ** 2)
    var_f = np.maximum(s1 / cs - (m1 / cs) ** 2, 1e-10)
    cb = np.maximum(cs[-1] - cs, 1e-10)
    var_b = np.maximum((s1[-1] - s1) / cb - ((m1[-1] - m1) / cb) ** 2, 1e-10)
    P = np.clip(cs / cs[-1], 1e-10, 1 - 1e-10)
    J = P * np.log(np.sqrt(var_f)) + (1 - P) * np.log(np.sqrt(var_b)) - P * np.log(P) - (1 - P) * np.log(1 - P)
    return float(b[np.argmin(J)])

def water_peak(db_vals, tau):
    v = db_vals[np.isfinite(db_vals) & (db_vals < tau)]
    cnt, edges = np.histogram(v, bins=np.arange(-35, tau + 0.5, 0.5))
    return float((edges[np.argmax(cnt)] + edges[np.argmax(cnt) + 1]) / 2)

def zmf(v, a, b):
    v = np.asarray(v, float); out = np.zeros_like(v); m = (a + b) / 2
    out[v <= a] = 1
    left = (v > a) & (v <= m); out[left] = 1 - 2 * ((v[left] - a) / (b - a)) ** 2
    right = (v > m) & (v < b); out[right] = 2 * ((v[right] - b) / (b - a)) ** 2
    return out

res = {}
for name, img, bounds in (("VV", vv, (-28, -11)), ("VH", vh, (-28, -18))):
    t = ki(img[sl])
    res[name] = {"tau_ki": t, "tau": float(np.clip(t, *bounds)), "bounded": not (bounds[0] <= t <= bounds[1])}
    res[name]["mu_w"] = water_peak(img[sl], res[name]["tau"])
    h, e = np.histogram(img[sl][np.isfinite(img[sl])], bins=np.arange(-32, 0.5, 1.0))
    res[name]["hist"] = h.tolist(); res[name]["hist_edges"] = [float(e[0]), float(e[-1])]

zvv = zmf(vv, res["VV"]["mu_w"], res["VV"]["tau"])
zvh = zmf(vh, res["VH"]["mu_w"], res["VH"]["tau"])
# polarisation swaps that need no land cover
swap1 = (o > 0.1) & (o < 0.9) & (vh < -18)
zvh = np.where(swap1, zvv, zvh)
swap2 = (vh < -24) & (o >= 0.9)
zvv = np.where(swap2, zvh, zvv)
zh = zmf(np.nan_to_num(hand), 0, 15)
zs = zmf(slope_opera, 0.5, 15)
so = 1 - zmf(o, 0.8, 0.95)
F = 0.5 * (zvv + zvh) / 2 + 0.5 * (zh + zs + so) / 3

# example pixel: inside the tile, DSWx open water, not permanent water (o < 0.1), low HAND
t_ = np.zeros(vv.shape, bool); t_[sl] = True
cand = t_ & (dswx == 1) & (o < 0.1) & np.isfinite(vv)
rr, cc = np.nonzero(cand)
i = np.argmin(np.hypot(rr - gr, cc - gc))
pr, pc = int(rr[i]), int(cc[i])
ex = {k_: float(v_[pr, pc]) for k_, v_ in dict(vv=vv, vh=vh, hand=hand, slope=slope_opera,
      slope_true=slope_true, o=o, zvv=zvv, zvh=zvh, zh=zh, zs=zs, so=so, F=F).items()}
ex["dswx"] = int(dswx[pr, pc]); ex["rc"] = [pr, pc]

# 6 x 8 patch of real F across a flood edge near the example pixel
best = None
for dr in range(-12, 7):
    for dc in range(-12, 5):
        P_ = F[pr + dr:pr + dr + 6, pc + dc:pc + dc + 8]
        if P_.shape != (6, 8) or not np.isfinite(P_).all():
            continue
        n_seed, n_low = (P_ > .81).sum(), (P_ <= .51).sum()
        mid = ((P_ > .51) & (P_ <= .81)).sum()
        score = min(n_seed, 12) + min(mid, 10) * 1.5 + min(n_low, 14)
        if best is None or score > best[0]:
            best = (score, dr, dc)
_, dr, dc = best
patch = F[pr + dr:pr + dr + 6, pc + dc:pc + dc + 8]

# vegetation examples: real pixels
ratio = vv - vh  # dB
veg = (dswx == 3)
vr, vc = np.nonzero(veg & t_) if (veg & t_).any() else np.nonzero(veg)
j = int(np.argmin(np.hypot(vr - gr, vc - gc)))
veg_px = [int(vr[j]), int(vc[j])]
dry = read_grid(d + "2025-01-24_T121_VV_db.tif"), read_grid(d + "2025-01-24_T121_VH_db.tif")
dark = np.isfinite(vh) & (vh <= -26) & (ratio > 8)
dr_, dc_ = np.nonzero(dark)
k2 = int(np.argmin(np.hypot(dr_ - gr, dc_ - gc))) if dr_.size else None
out = {"tile": {"r0": r0, "c0": c0, "size_px": T, "gauge_rc": [gr, gc]}, "thresholds": res,
       "example": ex, "patch": patch.round(2).tolist(),
       "veg_flood": {"vv": float(vv[tuple(veg_px)]), "vh": float(vh[tuple(veg_px)]), "dswx": 3},
       "veg_same_px_dry_0124": {"vv": float(dry[0][tuple(veg_px)]), "vh": float(dry[1][tuple(veg_px)])},
       "dark_px": None if k2 is None else {"vv": float(vv[dr_[k2], dc_[k2]]), "vh": float(vh[dr_[k2], dc_[k2]]),
                                            "dswx": int(dswx[dr_[k2], dc_[k2]])},
       "slope_county": {"median_opera": float(np.nanmedian(slope_opera)), "median_true": float(np.nanmedian(slope_true)),
                        "frac_opera_gt5": float(np.nanmean(slope_opera > 5)), "frac_true_gt5": float(np.nanmean(slope_true > 5))},
       "F_vs_dswx": {"F_mean_dswx_water": float(np.nanmean(F[t_ & (dswx == 1)])),
                     "F_mean_dswx_notwater": float(np.nanmean(F[t_ & (dswx == 0)]))}}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps({k_: out[k_] for k_ in ("thresholds",)}, default=str)[:0])
for k_ in ("VV", "VH"):
    r_ = res[k_]; print(k_, "KI", round(r_["tau_ki"], 2), "-> tau", r_["tau"], "bounded" if r_["bounded"] else "", "mu_w", r_["mu_w"])
print("example", {k_: (round(v_, 2) if isinstance(v_, float) else v_) for k_, v_ in ex.items()})
print("patch\n", patch.round(2))
print("veg flood", out["veg_flood"], "same px dry", out["veg_same_px_dry_0124"], "dark", out["dark_px"])
print("slope", out["slope_county"]); print("F vs dswx", out["F_vs_dswx"])
