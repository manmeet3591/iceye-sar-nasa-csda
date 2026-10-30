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


# =================================================== OPERA DSWx-S1, 8 steps ==
from make_figures import big_arrow, para, sar_tile  # noqa: E402

DARK = "#1F2230"


def membership(x, y, w, h, kind, label):
    """Tiny fuzzy membership curve: 'Z' (1 on the left) or 'S' (1 on the right)."""
    out = [line(x, y + h, x + w, y + h, C["muted"], 1.2), line(x, y, x, y + h, C["muted"], 1.2)]
    pts = []
    for i in range(31):
        a = i / 30
        z = 1 if a < .3 else 0 if a > .7 else .5 + .5 * math.cos(math.pi * (a - .3) / .4)
        m = z if kind == "Z" else 1 - z
        pts.append((x + a * w, y + h - m * (h - 2)))
    out.append(poly(pts, stroke=C["sea"], sw=2.2, closed=False))
    out.append(text(x - 8, y + h - 3, label, 12, 700, C["ink"], "end"))
    return "".join(out)


def d1(x, y, w, h):
    tw = (w - 16) / 2
    out = [sar_tile(x, y + 26, tw, 110, True)]
    out.append(sar_tile(x + tw + 16, y + 26, tw, 110, True))
    out.append(rect(x + tw + 16, y + 26, tw, 110, "#000000", r=6, op=.28))
    out.append(text(x + tw / 2, y + 16, "VV", 17, 800, C["ink"], "middle"))
    out.append(text(x + tw * 1.5 + 16, y + 16, "VH", 17, 800, C["ink"], "middle"))
    out.append(text(x + tw / 2, y + 156, "send V · hear V", 12, 600, C["muted"], "middle"))
    out.append(text(x + tw * 1.5 + 16, y + 156, "send V · hear H", 12, 600, C["muted"], "middle"))
    out.append(text(x + tw / 2, y + 176, "sharp water/land contrast", 11.5, 600, C["sea"], "middle"))
    out.append(text(x + tw * 1.5 + 16, y + 176, "less hurt by wind", 11.5, 600, C["sea"], "middle"))
    return "".join(out)


def d2(x, y, w, h):
    out = [sar_tile(x, y + 4, 150, 120, True)]
    for i in range(1, 5):
        out.append(line(x + i * 30, y + 4, x + i * 30, y + 124, "white", 1, "3 3"))
    for j in range(1, 4):
        out.append(line(x, y + 4 + j * 30, x + 150, y + 4 + j * 30, "white", 1, "3 3"))
    for (i, j) in ((0, 1), (2, 2), (4, 1)):
        out.append(rect(x + i * 30 + 1, y + 4 + j * 30 + 1, 28, 28, "none", C["edge"], r=2, sw=3))
    out.append(text(x + 75, y + 142, "use only tiles that cross", 11.5, 700, C["edge"], "middle"))
    out.append(text(x + 75, y + 157, "a known (JRC) shoreline", 11.5, 700, C["edge"], "middle"))
    hb = [2, 6, 9, 5, 2, 1, 2, 6, 12, 15, 10, 4]
    cols = [C["water"]] * 5 + ["#B9AFA0"] * 7
    out.append(histogram(x + 170, y + 10, w - 172, 64, hb, .42, cols))
    out.append(text(x + 170 + (w - 172) * .42, y + 92, "KI threshold", 11.5, 800, C["edge"], "middle"))
    out.append(text(x + 172, y + 112, "two clear humps?", 11.5, 700, C["ink"]))
    out.append(text(x + 172, y + 127, "Ashman D > 2", 11, 500, C["muted"]))
    out.append(text(x + 172, y + 141, "surface ratio > 0.1", 11, 500, C["muted"]))
    gx, gy, gw = x + 172, y + 160, w - 176
    for k in range(20):
        c = int(150 + 80 * k / 19)
        out.append(rect(gx + k * gw / 20, gy, gw / 20 + .5, 14, f"rgb(60,{c},{230 - k * 3})", r=0))
    out.append(text(gx + gw / 2, gy + 30, "threshold map (interpolated)", 11, 600, C["muted"], "middle"))
    return "".join(out)


def d3(x, y, w, h):
    out = []
    rows = (("Z", "dark VV"), ("Z", "dark VH"), ("Z", "flat slope"), ("Z", "low HAND"),
            ("S", "JRC: often water"))
    for i, (k, lab) in enumerate(rows):
        out.append(membership(x + 112, y + 6 + i * 36, 92, 26, k, lab))
    ax_ = x + 214
    for i in range(5):
        out.append(line(ax_, y + 19 + i * 36, ax_ + 30, y + 92, C["muted"], 1.3))
    out.append(circle(x + w - 44, y + 92, 34, C["sea"]))
    out.append(text(x + w - 44, y + 88, "0.83", 18, 800, "white", "middle"))
    out.append(text(x + w - 44, y + 106, "average", 11, 600, "white", "middle"))
    out.append(text(x + 112, y + 190, "each clue → 0 (land) … 1 (water)", 11.5, 600, C["muted"]))
    return "".join(out)


GRID4 = [[.2, .3, .4, .5, .3, .2, .1, .2],
         [.3, .6, .7, .9, .8, .4, .2, .1],
         [.4, .7, .9, .95, .9, .6, .3, .2],
         [.3, .5, .8, .9, .7, .3, .2, .65],
         [.2, .3, .4, .5, .4, .2, .3, .7],
         [.1, .2, .2, .3, .2, .1, .2, .3]]


def d4(x, y, w, h):
    R, Cn = len(GRID4), len(GRID4[0])
    cw, ch = (w - 10) / Cn, 22
    seeds = {(r, c) for r in range(R) for c in range(Cn) if GRID4[r][c] >= .8}
    grown = set(seeds)
    changed = True
    while changed:
        changed = False
        for r in range(R):
            for c in range(Cn):
                if (r, c) in grown or GRID4[r][c] < .6:
                    continue
                if any((r + dr, c + dc) in grown for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    grown.add((r, c))
                    changed = True
    out = []
    for r in range(R):
        for c in range(Cn):
            v = GRID4[r][c]
            if (r, c) in seeds:
                fill, fc = C["sea"], "white"
            elif (r, c) in grown:
                fill, fc = C["water"], "white"
            elif v >= .6:
                fill, fc = "#D7D7D7", C["ink"]
            else:
                fill, fc = C["land"], C["muted"]
            out.append(rect(x + c * cw, y + 6 + r * ch, cw - 2, ch - 2, fill, r=3))
            out.append(text(x + c * cw + cw / 2 - 1, y + 6 + r * ch + 15, f"{v:.2f}".lstrip("0"), 10.5,
                            700, fc, "middle"))
    ly = y + 152
    for lab, col, dx in (("seed ≥ 0.8", C["sea"], 0), ("grown ≥ 0.6", C["water"], 100),
                         ("≥ 0.6, not connected", "#D7D7D7", 0)):
        yy = ly if dx or lab.startswith("seed") else ly + 20
        out.append(rect(x + dx, yy - 10, 12, 12, col, r=2))
        out.append(text(x + dx + 16, yy, lab, 11.5, 600, C["muted"]))
    return "".join(out)


def field(x, y, w, h):
    out = [rect(x, y, w, h, "#D8C39A", r=6)]
    for i in range(1, 7):
        out.append(line(x + 4, y + i * h / 7, x + w - 4, y + i * h / 7, "#BFA67A", 2))
    return "".join(out)


def d5(x, y, w, h):
    out = [field(x + 4, y + 10, 130, 80)]
    out.append(line(x + 14, y + 18, x + 124, y + 82, C["pt"], 5))
    out.append(line(x + 124, y + 18, x + 14, y + 82, C["pt"], 5))
    out.append(text(x + 69, y + 110, "dry bare field: dark", 12, 700, C["ink"], "middle"))
    out.append(text(x + 69, y + 126, "but NOT water", 12, 700, C["pt"], "middle"))
    bx = x + 150
    out.append(rect(bx, y + 8, w - 150, 120, "#F4F1EA", C["line"], r=10, sw=1.5))
    out.append(text(bx + 10, y + 30, "rule out as water if:", 12, 800, C["ink"]))
    out.append(text(bx + 10, y + 52, "land cover = bare,", 12, 600, C["ink"]))
    out.append(text(bx + 10, y + 68, "grass or crops", 12, 600, C["ink"]))
    out.append(text(bx + 10, y + 90, "VV < −13.4 dB", 12, 800, C["sea"]))
    out.append(text(bx + 10, y + 106, "and VH < −22.2 dB", 12, 800, C["sea"]))
    out.append(text(x, y + 160, "JRC seasonality keeps water that", 11.5, 600, C["muted"]))
    out.append(text(x, y + 176, "is normal there (wet seasons).", 11.5, 600, C["muted"]))
    return "".join(out)


def blob(cx, cy, r, op=.9, fill=None):
    pts = [(cx + r * (1 + .18 * math.sin(3 * a)) * math.cos(a), cy + r * .7 * (1 + .15 * math.cos(2 * a))
            * math.sin(a)) for a in [i * 2 * math.pi / 40 for i in range(40)]]
    return poly(pts, fill=fill or C["water"], stroke=C["sea"], sw=2, op=op)


def d6(x, y, w, h):
    out = []
    for i, (ok, hb) in enumerate(((True, [2, 7, 5, 1, 1, 5, 9, 4]), (False, [1, 3, 7, 10, 8, 4, 2, 1]))):
        bx = x + i * (w / 2 + 4)
        out.append(blob(bx + 52, y + 46, 34, fill=C["water"] if ok else "#9CC8EE"))
        pts = [(bx + 52 + 50 * math.cos(a), y + 46 + 36 * math.sin(a))
               for a in [k * 2 * math.pi / 40 for k in range(40)]]
        out.append(poly(pts, stroke=C["edge"], sw=1.8, dash="4 4"))
        out.append(histogram(bx + 8, y + 102, w / 2 - 26, 46, hb, None,
                             [C["water"]] * 4 + ["#B9AFA0"] * 4 if ok else ["#B9AFA0"] * 8))
        out.append(text(bx + (w / 2 - 18) / 2, y + 172, "two humps → keep" if ok else "one hump → remove",
                        12, 800, C["ok"] if ok else C["pt"], "middle"))
    out.append(text(x, y + 192, "pixels along each water body's edge", 11.5, 600, C["muted"]))
    return "".join(out)


def d7(x, y, w, h):
    out = [rect(x, y + 4, w, 150, "#F4F8FC", r=8)]
    wy = y + 118
    out.append(rect(x, wy, w, 36, C["water"], r=0, op=.85))
    trunks = [x + 30 + k * 50 for k in range(4)]
    for tx in trunks:
        out.append(line(tx, wy + 30, tx, y + 70, "#6B4F2E", 6))
        out.append(circle(tx, y + 64, 15, "#74A35B"))
    out.append(text(x + 8, wy + 26, "water", 12, 700, "white"))
    # satellite top-right; pulse hits the water, bounces to a stem, returns to the satellite
    sx, sy = x + w - 26, y + 26
    out.append(mf.satellite(sx, sy, .55))
    tx = trunks[-1]
    px_, py_ = tx + 34, wy                 # water hit
    qx, qy = tx + 3, wy - 26               # stem hit
    out.append(line(sx - 6, sy + 14, px_, py_, C["edge"], 2.5))
    out.append(line(px_, py_, qx, qy, C["edge"], 2.5))
    out.append(line(qx, qy, sx - 16, sy + 12, C["edge"], 2.5, "6 4"))
    out.append(text(x + w - 8, y + 74, "double", 12, 800, C["edge"], "end"))
    out.append(text(x + w - 8, y + 89, "bounce", 12, 800, C["edge"], "end"))
    out.append(text(x, y + 176, "VV bright, VH much weaker → high VV/VH", 12, 800, C["ink"]))
    out.append(text(x, y + 193, "mapped only in wetland / vegetation classes", 11.5, 600, C["muted"]))
    return "".join(out)


def d8(x, y, w, h):
    classes = [("0", "not water", C["land"]), ("1", "open water", C["water"]),
               ("3", "inundated vegetation", "#2A9D8F"), ("250", "HAND masked", "#B8B8B8"),
               ("251", "layover / shadow", "#7F7F7F"), ("255", "no data", "#FFFFFF")]
    pat = ["0000110000", "0001111000", "0011133100", "0001111000", "4400000055", "4440000055"]
    key = {"0": C["land"], "1": C["water"], "3": "#2A9D8F", "4": "#B8B8B8", "5": "#7F7F7F"}
    cw = 13
    for r, row in enumerate(pat):
        for c, k in enumerate(row):
            out_ = rect(x + c * cw, y + 8 + r * cw, cw - 1, cw - 1, key[k], r=1)
            if r == 0 and c == 0:
                out = [out_]
            else:
                out.append(out_)
    out.append(text(x, y + 104, "MGRS tile, 30 m", 11.5, 700, C["muted"]))
    for i, (code, lab, col) in enumerate(classes):
        yy = y + 18 + i * 22
        out.append(rect(x + 146, yy - 11, 13, 13, col, C["line"], r=2, sw=1))
        out.append(text(x + 166, yy, code, 12, 800, C["ink"]))
        out.append(text(x + 196, yy, lab, 12, 500, C["ink"]))
    out.append(text(x, y + 168, "layers: WTR (classes), BWTR (water yes/no),", 11.5, 600, C["muted"]))
    out.append(text(x, y + 184, "CONF (confidence), DIAG (diagnostics)", 11.5, 600, C["muted"]))
    return "".join(out)


def dswx_s1():
    W2, H2 = 1600, 1220
    fc, fl = "#E76F51", "#FBE0D8"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W2}" height="{H2}" viewBox="0 0 {W2} {H2}">',
         rect(0, 0, W2, H2, C["bg"], r=0)]
    o.append(chip(48, 30, "Operational product · NASA/JPL OPERA", fc, size=15))
    o.append(text(48, 100, "How OPERA DSWx-S1 turns Sentinel-1 VV + VH into a water map", 38, 800))
    o.append(text(48, 134, "Dynamic Surface Water eXtent from Sentinel-1 · 30 m · open data since 2024", 19,
                  500, C["muted"]))
    o.append(rect(48, 156, W2 - 96, 66, fl, fc, r=18, sw=2))
    o.append(text(76, 197, "Big idea:", 22, 800, fc))
    o.append(text(196, 197, "No single clue is trusted: radar darkness in two polarisations is weighed against "
                  "terrain and history.", 20, 600))
    steps = [
        ("Two echoes of one pulse", d1,
         "Sentinel-1 sends a vertically polarised pulse and records two echoes: VV and VH. OPERA's RTC product "
         "corrects both for terrain on a 30 m grid; bursts are mosaicked so a scene holds enough water and land."),
        ("Threshold map from shore tiles", d2,
         "Only tiles with two clear humps that also cross a known JRC shoreline are used. Kittler–Illingworth "
         "gives each a threshold; these are interpolated into a map, for VV and for VH."),
        ("Turn every clue into a score", d3,
         "Fuzzy logic: dark VV, dark VH, flat ground, low HAND and 'often water in the past' each become a "
         "0–1 water-likeness score. Their average is the composite score."),
        ("Grow water from sure seeds", d4,
         "Pixels scoring ≥ 0.8 are sure water. Water spreads to neighbours scoring ≥ 0.6, but only when "
         "connected to a seed; isolated look-alikes stay out."),
        ("Remove dark land", d5,
         "Bare soil, sand or smooth fields can be as dark as water. If land cover allows it and both "
         "polarisations are very dark, the pixel is ruled not-water."),
        ("Check water-body edges", d6,
         "Along a real shoreline, backscatter splits into a water hump and a land hump. Objects whose edge "
         "pixels show no such split are removed as false alarms."),
        ("Find water under vegetation", d7,
         "Under plants, the pulse bounces water → stem → satellite and returns bright, mostly in VV. A high "
         "VV/VH ratio inside vegetated land-cover classes is mapped as inundated vegetation."),
        ("Mask and package", d8,
         "Pixels too high above drainage (HAND) or in radar layover/shadow are flagged. Results are cut "
         "into 30 m MGRS tiles with four layers."),
    ]
    px0, pw, gap, ph = 48, 358, 22, 418
    for i, (title, ill, cap) in enumerate(steps):
        rr, cc = divmod(i, 4)
        x, y = px0 + cc * (pw + gap), 248 + rr * (ph + 24)
        o.append(rect(x, y, pw, ph, "white", C["line"], r=18, sw=2))
        o.append(circle(x + 30, y + 32, 18, fc))
        o.append(text(x + 30, y + 39, str(i + 1), 18, 800, "white", "middle"))
        o.append(para(x + 58, y + 30, title, pw - 70, 18, 1.2, weight=800))
        o.append(f"<g>{ill(x + 20, y + 74, pw - 40, 200)}</g>")
        o.append(para(x + 20, y + 300, cap, pw - 36, 14.5, 1.36))
        if cc < 3:
            o.append(f'<path d="M{x + pw + 4},{y + ph / 2 - 10} L{x + pw + gap - 4},{y + ph / 2} '
                     f'L{x + pw + 4},{y + ph / 2 + 10} Z" fill="{fc}" opacity=".85"/>')
    o.append(text(48, H2 - 40, "Sources: OPERA DSWx-S1/NI ATBD (JPL D-108763 Rev A, May 2024); DSWx-S1 product "
                  "specification Rev A; metadata of DSWx-S1 tiles over Warren County, KY (Feb 2025).", 13, 500,
                  C["muted"]))
    o.append(text(48, H2 - 20, "Current product files name GLAD Global Land Cover 2020 (the ATBD names ESA "
                  "WorldCover) and some different fuzzy ranges (e.g. HAND 0–15 m). Schematic illustration.", 13,
                  500, C["muted"], italic=True))
    o.append("</svg>")
    mf.OUT.mkdir(parents=True, exist_ok=True)
    (mf.OUT / "opera_dswx_s1.svg").write_text("".join(o))
    return "opera_dswx_s1"


# ============================================ DSWx-S1, quantitative version ==
def zmf(v, a, b):
    """OPERA's Z-shaped membership (dswx_sar.common._fuzzy_value_computation.zmf)."""
    if v <= a:
        return 1.0
    if v >= b:
        return 0.0
    m = (a + b) / 2
    return 1 - 2 * ((v - a) / (b - a)) ** 2 if v <= m else 2 * ((v - b) / (b - a)) ** 2


def smf(v, a, b):
    return 1 - zmf(v, a, b)


def eq(x, y, s_, size=14.5, weight=600, fill=None):
    return text(x, y, s_, size, weight, fill or C["ink"])


def curve(x, y, w, h, f, lo, hi, a, b, val, label, unit, kind="Z"):
    """Small membership plot with the example value marked."""
    out = [line(x, y + h, x + w, y + h, C["muted"], 1.2), line(x, y, x, y + h, C["muted"], 1.2)]
    pts = []
    for i in range(61):
        v = lo + (hi - lo) * i / 60
        pts.append((x + w * i / 60, y + h - f(v, a, b) * (h - 2)))
    out.append(poly(pts, stroke=C["sea"], sw=2.2, closed=False))
    vx = x + w * (val - lo) / (hi - lo)
    mv = f(val, a, b)
    out.append(line(vx, y + h, vx, y + h - mv * (h - 2), C["edge"], 1.5, "3 3"))
    out.append(circle(vx, y + h - mv * (h - 2), 4.5, C["edge"], "white", 1.5))
    out.append(text(x, y - 6, label, 12.5, 800, C["ink"]))
    out.append(text(x + w, y - 6, f"= {mv:.2f}", 12.5, 800, C["edge"], "end"))
    out.append(text(x, y + h + 14, f"{lo:g}", 10.5, 500, C["muted"]))
    out.append(text(x + w, y + h + 14, f"{hi:g} {unit}", 10.5, 500, C["muted"], "end"))
    return "".join(out), mv


def qpanel(o, x, y, w, h, letter, title, fc):
    o.append(rect(x, y, w, h, "white", C["line"], r=18, sw=2))
    o.append(circle(x + 30, y + 32, 18, fc))
    o.append(text(x + 30, y + 39, letter, 17, 800, "white", "middle"))
    o.append(text(x + 58, y + 40, title, 20, 800))


# Real values from scripts/t1_opera_rules_check.py on Warren County, Sentinel-1 track 121,
# 2025-02-17 (OPERA RTC-S1 + DSWx-S1, USGS 3DEP, ASF HAND, JRC). Nothing below is invented.
REAL = dict(
    tile_hist_vv=[0, 0, 1, 2, 6, 8, 9, 18, 42, 54, 78, 99, 57, 82, 72, 81, 116, 217, 357, 589, 853, 1120,
                  1311, 1232, 985, 799, 558, 355, 249, 174, 125, 89],    # 1 dB bins, -32 ... 0 dB
    tau_vv=-18.31, mu_vv=-20.75, tau_vh=-27.13, mu_vh=-27.75,          # OPERA KI formula, this tile only
    px_vv=-18.65, px_vh=-22.87, px_hand=0.08, px_slope_opera=6.01, px_slope_std=2.26, px_o=0.0,
    px_dist_km=0.24,                                                    # OPERA WTR = 1 (open water)
    slope_med_opera=7.8, slope_med_std=2.9, slope_gt5_opera=67, slope_gt5_std=30,
    veg_n=2930, veg_r_p10=5.7, veg_r_p50=8.8, veg_r_p90=12.4, veg_vh_p50=-18.1,
    dark_vv=-12.41, dark_vh=-26.47,                                     # OPERA WTR = 0
)


def dswx_s1_quant():
    R = REAL
    W2, H2 = 1600, 1990
    fc, fl = "#E76F51", "#FBE0D8"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W2}" height="{H2}" viewBox="0 0 {W2} {H2}">',
         rect(0, 0, W2, H2, C["bg"], r=0)]
    o.append(chip(48, 30, "Operational product · NASA/JPL OPERA · exact rules", fc, size=15))
    o.append(text(48, 98, "OPERA DSWx-S1: the exact rules, checked on Warren County data", 36, 800))
    o.append(text(48, 130, "Rules and numbers from the open-source code (opera-adt/DSWX-SAR, commit d9ae8ed, Mar 2026). "
                  "Examples: Sentinel-1, 17 Feb 2025, Bowling Green.", 17, 500, C["muted"]))
    PW, GX = 744, 16
    X1, X2 = 48, 48 + PW + GX
    Y1, H1 = 156, 560
    Y2, Hc = Y1 + H1 + 18, 600
    Y3, H3 = Y2 + Hc + 18, 560

    # ---------------------------------------------------------------- A
    x, y = X1, Y1
    qpanel(o, x, y, PW, H1, "A", "Inputs, and how slope is computed", fc)
    yy = y + 80
    for t_ in ["• γ⁰ VV and γ⁰ VH: OPERA RTC-S1, 30 m; Bregman total-variation filter (λ = 20), then dB",
               "• o = JRC occurrence / 100   (0 = never water … 1 = always water)",
               "• h = HAND from ASF GLO-30 (m);  land cover: GLAD 2020 (or ESA WorldCover)",
               "• slope θ from the 30 m DEM with a 3 × 3 Sobel filter (Sₓ shown, S_y = transpose):"]:
        o.append(eq(x + 26, yy, t_, 14, 500))
        yy += 26
    kk = [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]
    for r_ in range(3):
        for c_ in range(3):
            o.append(rect(x + 40 + c_ * 34, yy + 4 + r_ * 34, 32, 32, "#EAF3FB", C["water"], r=4, sw=1.5))
            o.append(text(x + 56 + c_ * 34, yy + 26 + r_ * 34, str(kk[r_][c_]), 15, 800, C["sea"], "middle"))
    o.append(eq(x + 172, yy + 36, "θ = arctan √[ (Sₓ / (3 · 30 m))² + (S_y / (3 · 30 m))² ]", 16, 800, C["sea"]))
    o.append(eq(x + 172, yy + 64, "then scored with Z(θ; 0.5°, 15°): flat ground looks water-like", 14, 600))
    o.append(eq(x + 172, yy + 90, "(a 3 × 3 Sobel sums to 8 · Δz, so the usual divisor is 8 · 30 m)", 13, 500,
                C["muted"]))
    by = yy + 132
    o.append(rect(x + 26, by, PW - 52, 210, "#FDF3DC", "#B7791F", r=12, sw=1.5))
    o.append(text(x + 44, by + 26, "Checked on Warren County's real 30 m DEM (USGS 3DEP):", 14, 800, "#8A5A00"))
    bars_ = [("median slope", R["slope_med_std"], R["slope_med_opera"], "°", 10),
             ("area steeper than 5°", R["slope_gt5_std"], R["slope_gt5_opera"], " %", 100)]
    for i_, (lab, v_std, v_op, unit, vmax) in enumerate(bars_):
        bx0, byy = x + 44, by + 56 + i_ * 66
        o.append(text(bx0, byy, lab, 13, 700, C["ink"]))
        for j_, (v_, col, nm) in enumerate(((v_std, C["ok"], "standard (÷ 8·30 m)"), (v_op, "#B7791F",
                                                                                     "OPERA as written"))):
            ww = 330 * v_ / vmax
            o.append(rect(bx0 + 175, byy - 14 + j_ * 22, ww, 17, col, r=3))
            o.append(text(bx0 + 181 + ww, byy - 1 + j_ * 22, f"{v_:g}{unit}  {nm}", 12.5, 700, col))
    o.append(text(x + 44, by + 192, "Synthetic check: a 5.7° plane comes out as 14.9°. Worth confirming with the "
                  "OPERA team.", 12.5, 600, "#8A5A00"))

    # ---------------------------------------------------------------- B
    x, y = X2, Y1
    qpanel(o, x, y, PW, H1, "B", "Thresholds: tiles → Kittler–Illingworth → map", fc)
    hx, hy, hw, hh = x + 40, y + 96, 420, 100
    hb = [v_ ** .5 for v_ in R["tile_hist_vv"]]          # square-root scale so the water hump shows
    cols = [C["water"] if (-32 + i_) < R["tau_vv"] else "#B9AFA0" for i_ in range(len(hb))]
    o.append(histogram(hx, hy, hw, hh, hb, None, cols))
    for v_, lab, col, dy, anchor in ((R["mu_vv"], f"μ_w = {R['mu_vv']:.1f}", C["sea"], -22, "end"),
                                     (R["tau_vv"], f"τ = {R['tau_vv']:.1f} dB", C["edge"], -6, "start")):
        fx = (v_ + 32) / 32
        o.append(line(hx + fx * hw, hy - 2, hx + fx * hw, hy + hh + 4, col, 2.5, "5 4"))
        o.append(text(hx + fx * hw + (4 if anchor == "start" else -4), hy + dy, lab, 12.5, 800, col, anchor))
    o.append(text(hx, hy + hh + 20, "−32", 11, 500, C["muted"]))
    o.append(text(hx + hw, hy + hh + 20, "0 dB", 11, 500, C["muted"], "end"))
    o.append(text(hx + hw / 2, hy + hh + 20, "pixel count, √ scale", 11, 500, C["muted"], "middle"))
    o.append(para(x + 480, y + 96, f"Real tile: VV backscatter in the 3 × 3 km around the Barren River gauge, "
                  f"17 Feb 2025. OPERA's KI formula gives τ = {R['tau_vv']:.1f} dB, water peak "
                  f"{R['mu_vv']:.1f} dB (VH: τ {R['tau_vh']:.1f}, peak {R['mu_vh']:.1f} dB).",
                  230, 12.5, 1.38, weight=600))
    yy = y + 252
    o.append(text(x + 26, yy - 12, "Tiles searched 400 → 200 → … → 40 px (step ½ window) until > 20 pass.", 13.5, 600))
    o.append(text(x + 26, yy + 8, "A tile is used only if ALL of:", 13.5, 800))
    yy += 8
    for t_ in ["1. it straddles JRC water: 0 < water fraction < 1 in the normal, flood (+16 px) or",
               "    drought (−10 px) version of the JRC mask, and ≥ ⅓ of its pixels are valid;",
               "2. maxₜ P₁P₂(μ₁ − μ₂)² / σ² > 0.7   (dB histogram −30 … 5 dB, 100 bins);",
               "3. two fitted Gaussians: 2 of {Ashman D > 1.5, bimodality > 0.7, Sarle > 5/9}",
               "    (or D > 3), and surface ratio min(A₁, A₂) / max(A₁, A₂) > 0.1."]:
        yy += 23
        o.append(eq(x + 30, yy, t_, 13.5, 500))
    yy += 36
    o.append(eq(x + 26, yy, "τ = argminₜ [ P₁ ln σ₁ + P₂ ln σ₂ − P₁ ln P₁ − P₂ ln P₂ ]", 16, 800, C["sea"]))
    for t_ in ["bounds τ_VV ∈ [−28, −11] dB, τ_VH ∈ [−28, −18] dB; above the bound → 3-Gaussian fit",
               "(each mode ≥ 8 % of the largest), keep the lower valley; humps that barely overlap →",
               "τ placed between their 99th / 1st percentiles. Tile τ and μ_w are averaged and interpolated",
               "(gdal_grid) into maps τ(x), μ_w(x) for VV and for VH. OPERA does not publish these maps."]:
        yy += 24
        o.append(eq(x + 26, yy, t_, 13.5, 500))

    # ---------------------------------------------------------------- C
    x, y = X1, Y2
    wfull = 2 * PW + GX
    qpanel(o, x, y, wfull, Hc, "C", "Fuzzy logic: five scores → one number F per pixel", fc)
    o.append(eq(x + 26, y + 80, "Z(v; a, b) = 1 if v ≤ a;  1 − 2((v−a)/(b−a))² if v ≤ (a+b)/2;  "
                "2((v−b)/(b−a))² if v < b;  0 if v ≥ b.        S = 1 − Z", 15, 700))
    specs = [("radar VV: Z(σ; μ_w, τ)", zmf, -26, -10, R["mu_vv"], R["tau_vv"], R["px_vv"], "dB"),
             ("radar VH: Z(σ; μ_w, τ)", zmf, -32, -16, R["mu_vh"], R["tau_vh"], R["px_vh"], "dB"),
             ("HAND: Z(h; 0, 15 m)", zmf, 0, 20, 0, 15, R["px_hand"], "m"),
             ("slope: Z(θ; 0.5°, 15°)", zmf, 0, 20, .5, 15, R["px_slope_opera"], "°"),
             ("history: S(o; 0.80, 0.95)", smf, 0, 1, .8, .95, R["px_o"], "")]
    vals = []
    for i_, (lab, f, lo, hi, a_, b_, v_, unit) in enumerate(specs):
        g, mv = curve(x + 40 + i_ * 302, y + 136, 240, 70, f, lo, hi, a_, b_, v_, lab, unit)
        o.append(g)
        vals.append(mv)
    anc = .5 * (vals[2] + vals[3] + vals[4]) / 3
    rad = .5 * (vals[0] + vals[1]) / 2
    o.append(rect(x + 26, y + 252, wfull - 52, 62, fl, fc, r=14, sw=2))
    o.append(eq(x + 46, y + 291, "F  =  ½ · mean(Z_VV, Z_VH)   +   ½ · (Z_HAND + Z_slope + S_history) / 3", 22, 800,
                fc))
    yy = y + 346
    o.append(eq(x + 26, yy, f"Real pixel {R['px_dist_km']:.2f} km from the Barren River gauge, mapped OPEN WATER by "
                f"OPERA on 17 Feb 2025 (red dots):", 14, 700))
    yy += 22
    o.append(eq(x + 26, yy, f"VV {R['px_vv']:.1f} dB, VH {R['px_vh']:.1f} dB, HAND {R['px_hand']:.2f} m, slope "
                f"{R['px_slope_opera']:.1f}° (OPERA formula; {R['px_slope_std']:.1f}° standard), JRC occurrence "
                f"{R['px_o']:.0%}", 14, 600))
    yy += 30
    o.append(eq(x + 26, yy, f"Terrain + history half (exact):  ½ · ({vals[2]:.2f} + {vals[3]:.2f} + {vals[4]:.2f}) / 3 = "
                f"{anc:.3f}", 16, 800, C["sea"]))
    yy += 28
    o.append(eq(x + 26, yy, f"Radar half with THIS tile's τ, μ_w:  ½ · ({vals[0]:.2f} + {vals[1]:.2f}) / 2 = {rad:.3f}"
                f"   →   F = {anc + rad:.2f}  (below 0.51 → not water here)", 16, 800, C["edge"]))
    yy += 26
    o.append(eq(x + 26, yy, "OPERA still mapped it as water, so its interpolated local τ at this pixel must be higher "
                "than this single tile's: the threshold map, not one tile, decides.", 13.5, 600, C["muted"]))
    yy += 38
    o.append(eq(x + 26, yy, "Polarisation swaps before averaging (where one polarisation is known to mislead):", 14.5,
                800))
    for i_, t_ in enumerate([
            "• VH score ← VV score where water comes and goes (0.1 < o < 0.9) and VH < −18 dB, or on flat dry-looking land",
            "   (bare / shrubs / grassland / herbaceous wetland, θ < 5°, VH < −18 dB): VH cannot tell smooth dry land from water there;",
            "• VV score ← VH score where water is permanent (o ≥ 0.9) and VH < −24 dB: wind roughens open water in VV, not in VH;",
            "• HAND > 200 m → F = 0. Radar and terrain/history each carry exactly half of F."]):
        o.append(eq(x + 30, yy + 24 + 22 * i_, t_, 13.5, 500))

    # ---------------------------------------------------------------- D
    x, y = X1, Y3
    qpanel(o, x, y, PW, H3, "D", "Sure seeds and region growing", fc)
    o.append(eq(x + 26, y + 84, "seed:  F > 0.81", 20, 800, C["sea"]))
    o.append(eq(x + 250, y + 84, "grow:  add 4-neighbours with F > 0.51,", 16, 800, C["water"]))
    o.append(eq(x + 250, y + 106, "repeat until no pixel is added (no limit)", 16, 800, C["water"]))
    ax_, ay_, aw_, ah_ = x + 90, y + 140, 400, 200
    o.append(axes(ax_, ay_, aw_, ah_, "", "radar score needed"))
    o.append(text(ax_ + aw_ / 2, ay_ + ah_ + 34, "JRC history o (0 = never water, 1 = always)", 13, 500, C["muted"],
                  "middle"))

    def need(oo, thr, zs_=1.0):
        an = .5 * (1.0 + zs_ + smf(oo, .8, .95)) / 3
        return (thr - an) / .5

    for thr, col, lab in ((.81, C["sea"], "to be a seed"), (.51, C["water"], "to be grown in")):
        pts = [(ax_ + aw_ * k_ / 100, ay_ + ah_ - min(need(k_ / 100, thr), 1.1) / 1.1 * ah_) for k_ in range(101)]
        o.append(poly(pts, stroke=col, sw=3, closed=False))
        o.append(text(ax_ + 8, pts[0][1] + 20, f"{lab}: {need(0, thr):.2f} at o = 0", 12.5, 800, col))
    y1 = ay_ + ah_ - 1 / 1.1 * ah_
    o.append(line(ax_, y1, ax_ + aw_, y1, C["pt"], 1.5, "4 4"))
    o.append(text(ax_ + aw_ - 4, y1 - 6, "max possible = 1", 12, 700, C["pt"], "end"))
    for k_, lab in ((0, "0"), (.5, "0.5"), (1, "1")):
        o.append(text(ax_ + aw_ * k_, ay_ + ah_ + 16, lab, 11, 500, C["muted"], "middle"))
    o.append(text(ax_ + aw_ + 12, ay_ + 20, "flat (θ ≤ 0.5°),", 12, 600, C["muted"]))
    o.append(text(ax_ + aw_ + 12, ay_ + 36, "HAND = 0", 12, 600, C["muted"]))
    yy = ay_ + ah_ + 64
    for t_ in [f"• Terrain + history can give at most 0.50 < 0.51: no pixel becomes water without radar evidence.",
               f"• Ground that was never water (o = 0) can be a seed only if the mean radar score > {need(0, .81):.2f};",
               "   so new flood mostly enters by growing outward from seeds in or near the river.",
               f"• The real pixel in C: terrain + history = {anc:.3f}, so a seed would need a radar score of "
               f"{(.81 - anc) / .5:.2f} (impossible);",
               f"   it can only be grown in, with a mean radar score > {(.51 - anc) / .5:.2f}."]:
        o.append(eq(x + 30, yy, t_, 13.5, 500))
        yy += 23

    # ---------------------------------------------------------------- E
    x, y = X2, Y3
    qpanel(o, x, y, PW, H3, "E", "Dark land, edge check, water under vegetation", fc)
    yy = y + 80
    o.append(eq(x + 26, yy, "Dark land → not water if ALL:", 15, 800, C["pt"]))
    for t_ in ["land cover ∈ {bare/sparse vegetation, urban, moss & lichen} (+ grassland, shrubs),",
               "o < 0.05, VV < −14.6 dB and VH < −22.8 dB; except within 3 px of JRC occurrence ≥ 0.10."]:
        yy += 23
        o.append(eq(x + 30, yy, t_, 13.5, 500))
    yy += 36
    o.append(eq(x + 26, yy, "Edge check, per water object ≥ 40 px:", 15, 800, C["ok"]))
    yy += 23
    o.append(eq(x + 30, yy, "the object and its surroundings must pass the same two-Gaussian test as the tiles.", 13.5,
                500))
    yy += 40
    o.append(eq(x + 26, yy, "Water under vegetation:", 15, 800, "#2A9D8F"))
    yy += 30
    o.append(eq(x + 30, yy, "r = 10 log₁₀( Lee₃ₓ₃[ γ⁰_VV / γ⁰_VH ] )", 17, 800, "#2A9D8F"))
    yy += 26
    o.append(eq(x + 30, yy, "flooded vegetation if r > 8 dB and VH > −26 dB and land cover ∈ GLAD classes", 13.5,
                600))
    yy += 20
    o.append(eq(x + 30, yy, "19–24, 112–124, 125–148, 200–207 (with WorldCover: herbaceous wetland).", 13.5, 600))
    yy += 16
    cards = [("OPERA 'flooded vegetation', 17 Feb", f"{R['veg_n']:,} pixels: our VV − VH",
              f"median {R['veg_r_p50']} dB (10–90 %: {R['veg_r_p10']}–{R['veg_r_p90']})",
              f"median VH {R['veg_vh_p50']} dB · fits r > 8 dB", "#E3F4F1", "#2A9D8F"),
             ("dark pixel, 17 Feb (OPERA: not water)", f"VV {R['dark_vv']:.1f} · VH {R['dark_vh']:.1f} dB",
              f"r = {R['dark_vv'] - R['dark_vh']:.1f} dB, but VH ≤ −26 dB", "→ not flooded vegetation ✓",
              "#F4F8FC", C["ink"])]
    for i_, (t1, t2, t3, t4, bg, col) in enumerate(cards):
        cx = x + 26 + i_ * 352
        o.append(rect(cx, yy, 340, 118, bg, C["line"], r=10, sw=1.5))
        o.append(text(cx + 14, yy + 24, t1, 13, 800, col))
        for j_, tt in enumerate((t2, t3, t4)):
            o.append(text(cx + 14, yy + 50 + j_ * 22, tt, 12.5, 600, C["ink"]))
    yy += 140
    o.append(para(x + 26, yy, "Caution from the same data: the flooded-vegetation pixel nearest the gauge carries "
                  "that label on the dry reference date (24 Jan 2025) too, so the ratio rule can flag vegetation "
                  "that is not flooded.", PW - 110, 13, 1.38, fill="#8A5A00", weight=600))

    o.append(text(48, H2 - 38, "Numbers are DSWX-SAR defaults; the Warren County DSWx-S1 tiles list the same fuzzy "
                  "ranges in their metadata. Several defaults differ from the 2024 ATBD (seeds 0.81 vs 0.8, growth "
                  "0.51 vs 0.6,", 13, 500, C["muted"]))
    o.append(text(48, H2 - 18, "dark land −14.6 / −22.8 vs −13.4 / −22.2 dB). Examples computed by "
                  "scripts/t1_opera_rules_check.py from open data; OPERA's own τ maps and F are not published.", 13,
                  500, C["muted"], italic=True))
    o.append("</svg>")
    (mf.OUT / "opera_dswx_s1_exact.svg").write_text("".join(o))
    return "opera_dswx_s1_exact"


if __name__ == "__main__":
    print(mf.OUT / f"{gauge_thresholding()}.svg")
    print(mf.OUT / f"{dswx_s1()}.svg")
    print(mf.OUT / f"{dswx_s1_quant()}.svg")
