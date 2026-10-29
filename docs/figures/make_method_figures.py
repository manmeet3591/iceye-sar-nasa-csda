"""Illustrated explainers for the methods used in this repository (same style as make_figures.py).

    python docs/figures/make_method_figures.py      # writes docs/figures/methods/*.svg

All drawings are schematic -- no satellite imagery is used.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_figures as mf  # noqa: E402
from make_figures import C, axes, chip, circle, grid, histogram, interp, line, poly, rect, text  # noqa: E402

mf.OUT = Path(__file__).resolve().parent / "methods"
mf.FAM["T"] = ("Our testbed · Bowling Green / Warren County, KY", "#3A86A8", "#DCEEF5")


def gauge_icon(x, y, h=120, level=.55):
    """A staff gauge in the river: ruler with a water mark."""
    out = [rect(x, y, 26, h, "white", C["ink"], r=4, sw=2)]
    for i in range(9):
        yy = y + 8 + i * (h - 16) / 8
        out.append(line(x, yy, x + (14 if i % 2 else 22), yy, C["ink"], 1.5))
    wy = y + h * level
    out.append(rect(x - 30, wy, 86, y + h - wy + 12, C["water"], r=4, op=.8))
    out.append(line(x - 30, wy, x + 56, wy, C["sea"], 3))
    return "".join(out)


def step1(x, y, w, h):
    out = [gauge_icon(x + 22, y + 10, 140, .42)]
    out.append(text(x + 96, y + 34, "USGS gauge 03314500", 14, 800, C["ink"]))
    out.append(text(x + 96, y + 54, "Barren River, Bowling Green", 13, 500, C["muted"]))
    out.append(text(x + 96, y + 84, "stage at 23:39 UTC pass", 14, 600, C["ink"]))
    out.append(text(x + 96, y + 106, "34.67 ft", 22, 800, C["sea"]))
    out.append(text(x + 96, y + 134, "+ gauge datum 409.16 ft", 14, 600, C["ink"]))
    out.append(rect(x + 4, y + 176, w - 8, 66, "#EAF3FB", C["water"], r=12, sw=2))
    out.append(text(x + w / 2, y + 202, "water surface = 443.8 ft", 16, 800, C["sea"], "middle"))
    out.append(text(x + w / 2, y + 228, "= 135.3 m (NAVD88)", 15, 700, C["sea"], "middle"))
    return "".join(out)


GROUND2 = [(0, .14), (.12, .30), (.19, .68), (.27, .72), (.33, .36), (.42, .52), (.52, .82),
           (.62, .95), (.73, .78), (.86, .45), (1, .12)]


def step2(x, y, w, h):
    sh = 190
    out = [rect(x, y, w, sh, "#F4F8FC", r=10)]
    g = [(x + a * w, y + b * sh) for a, b in GROUND2]
    out.append(poly(g + [(x + w, y + sh), (x, y + sh)], fill=C["ground"], stroke=C["ground_d"], sw=2))
    ly = y + .56 * sh
    n = 160
    segs, cur = [], []
    for i in range(n + 1):
        xx = x + w * i / n
        gy = interp(g, xx)
        if gy > ly:
            cur.append((xx, gy))
        elif cur:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    for s in segs:
        main = s[0][0] < x + .62 * w < s[-1][0]
        pts = [(s[0][0], ly)] + s + [(s[-1][0], ly)]
        if main:
            out.append(poly(pts, fill=C["water"], stroke="none", op=.85))
            out.append(line(s[0][0], ly, s[-1][0], ly, C["sea"], 2.5))
        else:
            out.append(poly(pts, fill="none", stroke=C["sea"], sw=2, dash="5 4"))
            cx = (s[0][0] + s[-1][0]) / 2
            out.append(text(cx, y + 22, "low but cut off", 12, 700, C["muted"], "middle"))
            out.append(text(cx, y + 38, "→ stays dry", 12, 700, C["muted"], "middle"))
            out.append(line(cx, y + 44, cx, ly - 6, C["muted"], 1.5, "3 3"))
    out.append(line(x + 6, ly, x + w - 6, ly, C["sea"], 1.5, "3 4"))
    out.append(text(x + w - 8, ly - 8, "gauge water level", 13, 800, C["sea"], "end"))
    out.append(text(x + .62 * w, y + sh - 12, "channel", 12, 700, "white", "middle"))
    # plan view: reach circle
    py_ = y + sh + 14
    out.append(text(x, py_ + 16, "Only within 1.5 km of the gauge,", 13, 600, C["ink"]))
    out.append(text(x, py_ + 34, "where the water surface is ~flat.", 13, 600, C["ink"]))
    return "".join(out)


TRUTH = ["llllllllll",
         "lllwwwwlll",
         "llwwwwwwll",
         "lwwwwwwwwl",
         "llwwwwwwll",
         "llllllllll"]


def compare(thr):
    """Mask letters: t = both wet, f = radar-only (false alarm), n = missed, l = both dry."""
    rows = []
    for r, row in enumerate(TRUTH):
        s = ""
        for c, k in enumerate(row):
            wet = k == "w"
            core = 2 <= c <= 7 and 1 <= r <= 4 and not (r in (1, 4) and c in (2, 7))
            if thr == "strict":
                radar = core and not (c in (2, 7) or r == 1)
            elif thr == "best":
                radar = wet or (r, c) == (5, 1)
            else:
                radar = wet or r in (0, 5) and c % 3 == 0 or (r, c) in ((2, 0), (3, 9), (1, 8))
            s += "t" if wet and radar else "f" if radar else "n" if wet else "l"
        rows.append(s)
    return rows


def step3(x, y, w, h):
    bars = [1, 3, 6, 5, 3, 2, 3, 6, 11, 16, 18, 14, 9, 5, 2]
    cols = [C["water"]] * 6 + ["#B9AFA0"] * 9
    out = [histogram(x + 6, y + 4, w - 12, 70, bars, None, cols, "")]
    labels = [(.18, "−20 dB", "too strict"), (.42, "−14 dB", "best"), (.70, "−9 dB", "too loose")]
    for fx, lab, _ in labels:
        tx = x + 6 + fx * (w - 12)
        out.append(line(tx, y, tx, y + 78, C["edge"], 2.5, "5 4"))
        out.append(text(tx, y + 96, lab, 13, 800, C["edge"], "middle"))
    out.append(text(x + 6, y + 112, "dark = water", 12, 600, C["sea"]))
    out.append(text(x + w - 6, y + 112, "bright = land", 12, 600, C["ground_d"], "end"))
    cw = (w - 20) / 3
    pal = dict(t=C["water"], f=C["edge"], n=C["warn"], l=C["land"])
    for i, key in enumerate(("strict", "best", "loose")):
        gx = x + i * (cw + 10)
        out.append(grid(gx, y + 124, cw, 72, compare(key), colors=pal, stroke="white"))
        out.append(text(gx + cw / 2, y + 214, labels[i][2], 12, 700, C["ink"], "middle"))
    lx = x
    for lab, col in (("match", C["water"]), ("false alarm", C["edge"]), ("missed", C["warn"])):
        out.append(rect(lx, y + 228, 12, 12, col, r=2))
        out.append(text(lx + 16, y + 239, lab, 12, 600, C["muted"]))
        lx += 26 + len(lab) * 8.0
    return "".join(out)


def step4(x, y, w, h):
    ax, ay, aw, ah = x + 30, y + 8, w - 40, 150
    out = [axes(ax, ay, aw, ah, "radar threshold (dB)", "match score (F1)")]
    pts = []
    for i in range(61):
        a = i / 60
        f = .08 + .82 * math.exp(-((a - .52) / .17) ** 2)
        pts.append((ax + a * aw, ay + ah - f * (ah - 12)))
    out.append(poly(pts, stroke=C["sea"], sw=3.5, closed=False))
    bx, by = ax + .52 * aw, ay + ah - .9 * (ah - 12)
    out.append(line(bx, by + 4, bx, ay + ah, C["edge"], 2, "5 4"))
    out.append(circle(bx, by, 8, C["edge"], "white", 2))
    out.append(text(bx + 12, by + 4, "best threshold", 13, 800, C["edge"]))
    out.append(text(ax + 4, ay + ah + 40, "−28", 12, 600, C["muted"]))
    out.append(text(ax + aw, ay + ah + 40, "−8", 12, 600, C["muted"], "end"))
    out.append(rect(x + 4, y + 206, w - 8, 44, "#EAF6EF", C["ok"], r=10, sw=2))
    out.append(text(x + w / 2, y + 225, "apply county-wide, then check at", 13, 700, C["ok"], "middle"))
    out.append(text(x + w / 2, y + 243, "a 2nd gauge NOT used to calibrate", 13, 700, C["ok"], "middle"))
    return "".join(out)


def gauge_thresholding():
    return mf.page(
        "gauge_based_thresholding", "T", "Gauge-based thresholding of SAR water maps",
        "Phase 1 of the testbed · Sentinel-1 (OPERA RTC, 30 m) · USGS gauges 03314500 and 03314000",
        "\u00a0\u00a0Let a river gauge tell the radar which shade of dark means water.",
        [("Read the gauge at the moment of the satellite pass", step1,
          "Gauge height + the gauge's datum = water-surface elevation, in the same datum as the "
          "elevation map (NAVD88)."),
         ("Draw where water must be", step2,
          "Near the gauge the river is ~flat: ground below that level AND connected to the channel "
          "is expected to be wet. Isolated hollows and uplands are left out."),
         ("Try every radar threshold", step3,
          "Each threshold turns the radar image into a water map. Compare each map with the "
          "expected wet area: matches, false alarms, misses."),
         ("Keep the threshold that matches best", step4,
          "Score every threshold over all satellite dates (F1) and keep the peak. Then use it for "
          "the whole county.")],
        "Satellite image + one gauge with a known datum + a good DEM (USGS 3DEP lidar) + "
        "a map of the river channel (JRC water).",
        "A threshold tuned to this sensor, orbit and landscape, instead of a guess from the "
        "image histogram.",
        "Feb 17, 2025: 25.3 km² flooded vs OPERA's 25.9 km² (map agreement F1 0.79). "
        "High-water dates: −14.0 dB (Barren R.) and −12.5 dB (Drakes Cr.).",
        "At normal flow the channel is only 1–3 pixels wide, so only flood dates really calibrate. "
        "Today that is 2–3 passes; more events are needed. Narrow wooded creeks are hard to see at 30 m.",
        note="Expected-wet area assumes a flat water surface over ±1.5 km.")


if __name__ == "__main__":
    print(mf.OUT / f"{gauge_thresholding()}.svg")
