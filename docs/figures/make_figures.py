"""Generate one illustrated explainer (SVG) per flood-depth paper.

    python docs/figures/make_figures.py          # writes docs/figures/papers/*.svg

Style: pastel step-by-step panels (inspired by Jay Alammar's illustrated guides).
All drawings are schematic -- no satellite imagery is used.
"""

import html
from pathlib import Path

OUT = Path(__file__).resolve().parent / "papers"
W, H = 1600, 1000
FONT = "Inter, 'DejaVu Sans', Helvetica, Arial, sans-serif"

C = dict(
    bg="#FCFAF5", ink="#2B2D42", muted="#6C7086", line="#D9D4C7",
    water="#5DA9E9", water_l="#CFE6FA", ground="#C9A47E", ground_d="#8C6A4A",
    land="#EDE3D1", edge="#E76F51", ok="#2A9D8F", warn="#E9C46A", gap="#B8B8B8",
    sea="#2E6FA8", sar="#3D3D4E", pt="#E63946", hand="#52B788",
)
FAM = {
    "A": ("Family A · Fit a water line along the river", "#F4A261", "#FDEBD8"),
    "B": ("Family B · Spread flood-edge elevation inward", "#4C9BE8", "#DCEBFB"),
    "C": ("Family C · Height above the stream (HAND)", "#52B788", "#DDF2E6"),
    "D": ("Family D · Comparisons & machine learning", "#9D7CD8", "#ECE4F8"),
    "N": ("Operational product · NASA", "#E76F51", "#FBE0D8"),
}


# ---------------------------------------------------------------- primitives
def esc(s):
    return html.escape(str(s), quote=True)


def text(x, y, s, size=18, weight=400, fill=None, anchor="start", italic=False):
    st = ' font-style="italic"' if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill or C["ink"]}" text-anchor="{anchor}"{st}>'
            f'{esc(s)}</text>')


def wrap(s, max_px, size):
    per = max(8, int(max_px / (size * 0.53)))
    words, lines, cur = s.split(), [], ""
    for w_ in words:
        if len(cur) + len(w_) + 1 > per and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = f"{cur} {w_}".strip()
    if cur:
        lines.append(cur)
    return lines


def para(x, y, s, max_px, size=17, lh=1.35, **kw):
    out = []
    for i, ln in enumerate(wrap(s, max_px, size)):
        out.append(text(x, y + i * size * lh, ln, size, **kw))
    return "".join(out)


def rect(x, y, w, h, fill, stroke="none", r=14, sw=2, dash=None, op=1):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{op}"{d}/>')


def line(x1, y1, x2, y2, stroke=None, sw=2, dash=None, marker=False):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = ' marker-end="url(#arr)"' if marker else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke or C["ink"]}" stroke-width="{sw}" stroke-linecap="round"{d}{m}/>')


def circle(x, y, r, fill, stroke="none", sw=2):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def poly(pts, fill="none", stroke=None, sw=2, closed=True, dash=None, op=1):
    p = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    tag = "polygon" if closed else "polyline"
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<{tag} points="{p}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{sw}" '
            f'stroke-linejoin="round" opacity="{op}"{d}/>')


def big_arrow(x1, x2, y, color):
    return (f'<path d="M{x1},{y-9} L{x2-14},{y-9} L{x2-14},{y-18} L{x2},{y} L{x2-14},{y+18} '
            f'L{x2-14},{y+9} L{x1},{y+9} Z" fill="{color}" opacity="0.85"/>')


# ------------------------------------------------------------- illustrations
def interp(pts, x):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0 or 1)
    return pts[-1][1]


VALLEY = [(0, .12), (.18, .45), (.32, .8), (.5, .92), (.68, .78), (.84, .42), (1, .1)]


def cross_section(x, y, w, h, ground=VALLEY, level=.48, depth_at=.5, labels=True,
                  edge_dots=True, sky=True, level_label="water surface", water=True,
                  depth_label="depth"):
    out = []
    if sky:
        out.append(rect(x, y, w, h, "#F4F8FC", r=10))
    g = [(x + a * w, y + b * h) for a, b in ground]
    out.append(poly(g + [(x + w, y + h), (x, y + h)], fill=C["ground"], stroke=C["ground_d"], sw=2))
    ly = y + level * h
    if water:
        n = 120
        xs = [x + w * i / n for i in range(n + 1)]
        segs, cur = [], []
        for xx in xs:
            gy = interp(g, xx)
            if gy > ly:
                cur.append((xx, gy))
            elif cur:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        for sgm in segs:
            out.append(poly([(sgm[0][0], ly)] + sgm + [(sgm[-1][0], ly)],
                            fill=C["water"], stroke="none", op=.85))
            out.append(line(sgm[0][0], ly, sgm[-1][0], ly, C["sea"], 2.5))
            if edge_dots:
                out.append(circle(sgm[0][0], ly, 6, C["edge"], "white", 2))
                out.append(circle(sgm[-1][0], ly, 6, C["edge"], "white", 2))
        if depth_at is not None:
            dx = x + depth_at * w
            gy = interp(g, dx)
            if gy > ly:
                out.append(line(dx, ly + 3, dx, gy - 3, "white", 3))
                out.append(circle(dx, ly + 3, 3, "white"))
                out.append(circle(dx, gy - 3, 3, "white"))
                if labels:
                    out.append(text(dx + 8, (ly + gy) / 2 + 6, depth_label, 15, 700, "white"))
        if labels and level_label:
            out.append(text(x + w * .5, ly - 9, level_label, 14, 700, C["sea"], "middle"))
    return "".join(out)


BASE_MASK = [
    "llllllllll",
    "lllwwwwlll",
    "llwwwwwwll",
    "lwwwwwwwwl",
    "lwwwwwwwwl",
    "llwwwwwwll",
    "lllwwwwlll",
    "llllllllll",
]


def edges_of(mask):
    R, Cc = len(mask), len(mask[0])
    e = set()
    for r in range(R):
        for c in range(Cc):
            if mask[r][c] != "w":
                continue
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < R and 0 <= cc < Cc and mask[rr][cc] == "l":
                    e.add((r, c))
    return e


def grid(x, y, w, h, mask=BASE_MASK, show_edges=False, values=None, colors=None, stroke="white"):
    R, Cc = len(mask), len(mask[0])
    cw, ch = w / Cc, h / R
    pal = dict(l=C["land"], w=C["water_l"], n=C["gap"], o=C["sea"], s="#9CC8EE", f=C["water"])
    if colors:
        pal.update(colors)
    e = edges_of(mask) if show_edges else set()
    out = []
    for r in range(R):
        for c in range(Cc):
            k = mask[r][c]
            fill = C["edge"] if (r, c) in e else pal.get(k, C["land"])
            out.append(f'<rect x="{x+c*cw:.1f}" y="{y+r*ch:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                       f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
            if values and (r, c) in values:
                out.append(text(x + c * cw + cw / 2, y + r * ch + ch / 2 + 5, values[(r, c)], 12, 700,
                                "white" if (r, c) in e else C["ink"], "middle"))
    return "".join(out)


def histogram(x, y, w, h, bars, thr=None, colors=None, xlabel=""):
    out = [line(x, y + h, x + w, y + h, C["muted"], 2)]
    n = len(bars)
    bw = w / n
    mx = max(bars)
    for i, b in enumerate(bars):
        bh = (h - 10) * b / mx
        col = colors[i] if colors else C["water"]
        out.append(rect(x + i * bw + 2, y + h - bh, bw - 4, bh, col, r=3))
    if thr is not None:
        tx = x + thr * w
        out.append(line(tx, y - 5, tx, y + h + 5, C["edge"], 3, "6 4"))
    if xlabel:
        out.append(text(x + w / 2, y + h + 22, xlabel, 14, 500, C["muted"], "middle"))
    return "".join(out)


def axes(x, y, w, h, xl="", yl=""):
    out = [line(x, y + h, x + w, y + h, C["muted"], 2), line(x, y, x, y + h, C["muted"], 2)]
    if xl:
        out.append(text(x + w / 2, y + h + 22, xl, 14, 500, C["muted"], "middle"))
    if yl:
        out.append(f'<text x="{x-10}" y="{y+h/2}" font-family="{FONT}" font-size="14" fill="{C["muted"]}" '
                   f'text-anchor="middle" transform="rotate(-90 {x-10} {y+h/2})">{esc(yl)}</text>')
    return "".join(out)


def satellite(x, y, s=1.0, color=C["sar"]):
    return (f'<g transform="translate({x},{y}) scale({s})">'
            f'<rect x="-14" y="-10" width="28" height="20" rx="3" fill="{color}"/>'
            f'<rect x="-46" y="-6" width="28" height="12" fill="#4C9BE8" stroke="{color}"/>'
            f'<rect x="18" y="-6" width="28" height="12" fill="#4C9BE8" stroke="{color}"/>'
            f'<path d="M-6,10 L-14,26 L14,26 L6,10 Z" fill="#9AA0B5"/></g>')


def sar_tile(x, y, w, h, flood=True, label=None):
    """Schematic SAR image: grey speckle texture with a dark water body."""
    import random
    rnd = random.Random(int(x * 7 + y * 13))
    out = [rect(x, y, w, h, "#8D8F9C", r=6)]
    n = 14
    cw, ch = w / n, h / n
    for i in range(n):
        for j in range(n):
            g = rnd.randint(110, 190)
            out.append(f'<rect x="{x+i*cw:.1f}" y="{y+j*ch:.1f}" width="{cw+.5:.1f}" height="{ch+.5:.1f}" '
                       f'fill="rgb({g},{g},{g+8})"/>')
    river = [(x, y + h * .55), (x + w * .3, y + h * .45), (x + w * .6, y + h * .6), (x + w, y + h * .5)]
    width = .28 if flood else .07
    top = [(a, b - h * width) for a, b in river]
    bot = [(a, b + h * width) for a, b in river][::-1]
    out.append(poly(top + bot, fill="#1F2230", op=.92))
    out.append(rect(x, y, w, h, "none", C["ink"], r=6, sw=1.5))
    if label:
        out.append(text(x + w / 2, y + h + 20, label, 14, 600, C["muted"], "middle"))
    return "".join(out)


def scatter(x, y, w, h, pts, color, line11=True, xl="", yl=""):
    out = [axes(x, y, w, h, xl, yl)]
    if line11:
        out.append(line(x, y + h, x + w, y, C["muted"], 1.5, "5 4"))
    for a, b in pts:
        out.append(circle(x + a * w, y + h - b * h, 4.5, color, "white", 1))
    return "".join(out)


def bars(x, y, w, h, items, maxv, unit=""):
    out = [line(x, y + h, x + w, y + h, C["muted"], 2)]
    n = len(items)
    bw = w / n
    for i, (lab, v, col) in enumerate(items):
        bh = (h - 30) * v / maxv
        bx = x + i * bw + bw * .18
        out.append(rect(bx, y + h - bh, bw * .64, bh, col, r=5))
        out.append(text(bx + bw * .32, y + h - bh - 8, f"{v}{unit}", 15, 700, C["ink"], "middle"))
        out.append(text(bx + bw * .32, y + h + 20, lab, 14, 600, C["muted"], "middle"))
    return "".join(out)


def legend(x, y, items, size=13):
    out, cx = [], x
    for col, lab in items:
        out.append(rect(cx, y - 11, 14, 14, col, r=3))
        out.append(text(cx + 19, y + 1, lab, size, 500, C["muted"]))
        cx += 40 + len(lab) * size * .62
    return "".join(out)


def chip(x, y, s, fill, color="white", size=14):
    w = len(s) * size * .68 + 20
    return rect(x, y, w, size + 12, fill, r=(size + 12) / 2) + text(x + w / 2, y + size + 2, s, size, 700, color, "middle")


# ------------------------------------------------------------- page template
def page(slug, fam, title, cite, idea, steps, needs, gives, result, watch, note=None):
    fam_label, fc, fl = FAM[fam]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         '<defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
         f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C["ink"]}"/></marker></defs>',
         rect(0, 0, W, H, C["bg"], r=0)]
    # header
    o.append(chip(48, 30, fam_label, fc, size=15))
    o.append(text(48, 100, title, 40, 800))
    o.append(text(48, 134, cite, 19, 500, C["muted"]))
    # idea banner
    o.append(rect(48, 156, W - 96, 70, fl, fc, r=18, sw=2))
    o.append(text(76, 199, "Big idea:", 22, 800, fc))
    o.append(text(186, 199, idea, 22, 600))
    # step panels
    px, py, pw, ph, gap = 48, 252, 343, 500, 46
    for i, (stitle, illus, caption) in enumerate(steps):
        x = px + i * (pw + gap)
        o.append(rect(x, py, pw, ph, "white", C["line"], r=20, sw=2))
        o.append(circle(x + 34, py + 36, 20, fc))
        o.append(text(x + 34, py + 43, str(i + 1), 20, 800, "white", "middle"))
        o.append(para(x + 64, py + 33, stitle, pw - 80, 19, 1.25, weight=800))
        o.append(f'<g>{illus(x + 20, py + 95, pw - 40, 255)}</g>')
        o.append(para(x + 22, py + 382, caption, pw - 44, 16, 1.38, fill=C["ink"]))
        if i < len(steps) - 1:
            o.append(big_arrow(x + pw + 6, x + pw + gap - 4, py + ph / 2, fc))
    # footer cards
    fy, fh, fw, fg = 776, 180, 365, 16
    cards = [("NEEDS", needs, "#EEF2F7", C["muted"]), ("GIVES", gives, "#EAF6EF", C["ok"]),
             ("RESULT", result, fl, fc), ("WATCH OUT", watch, "#FDF3DC", "#B7791F")]
    for i, (lab, body, bgc, lc) in enumerate(cards):
        x = 48 + i * (fw + fg)
        o.append(rect(x, fy, fw, fh, bgc, r=16))
        o.append(text(x + 20, fy + 32, lab, 15, 800, lc))
        o.append(para(x + 20, fy + 60, body, fw - 40, 15.5, 1.38))
    if note:
        o.append(text(W - 48, H - 14, note, 13, 500, C["muted"], "end", italic=True))
    o.append(text(48, H - 14, "Schematic illustration · iceye-sar-nasa-csda teaching notes", 13, 500,
                  C["muted"]))
    o.append("</svg>")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{slug}.svg").write_text("".join(o))
    return slug


# ------------------------------------------------------------------- papers
def river_plan(x, y, w, h, flood=True, points=False, sections=False, shifted=False):
    out = [rect(x, y, w, h, C["land"], r=10)]
    cl = [(x, y + h * .5), (x + w * .25, y + h * .38), (x + w * .5, y + h * .58),
          (x + w * .75, y + h * .42), (x + w, y + h * .52)]
    fw_ = .26 if flood else .08
    if flood:
        top = [(a, b - h * fw_) for a, b in cl]
        bot = [(a, b + h * fw_) for a, b in cl][::-1]
        out.append(poly(top + bot, fill=C["water_l"], stroke=C["water"], sw=2))
    top = [(a, b - h * .07) for a, b in cl]
    bot = [(a, b + h * .07) for a, b in cl][::-1]
    out.append(poly(top + bot, fill=C["water"]))
    if sections:
        for i in range(1, 9):
            fx = x + w * i / 9
            cy = interp(cl, fx)
            out.append(line(fx, cy - h * .34, fx, cy + h * .34, C["ink"], 1.6, "4 3"))
    if points:
        for i in range(1, 9):
            fx = x + w * i / 9
            cy = interp(cl, fx)
            off = h * fw_
            dy = (6 if (shifted and i % 3 == 0) else 0)
            out.append(circle(fx, cy - off + dy, 5.5, C["pt"], "white", 1.5))
            out.append(circle(fx, cy + off - dy, 5.5, C["pt"], "white", 1.5))
    out.append(text(x + 8, y + h - 8, "flow →", 13, 600, C["muted"]))
    return "".join(out)


def p01():
    def s1(x, y, w, h):
        return (sar_tile(x + 10, y + 5, w - 20, 110, True, "SAR image: flood is dark")
                + river_plan(x, y + 140, w, 110, True))

    def s2(x, y, w, h):
        out = river_plan(x, y + 20, w, 150, True, points=True)
        out += text(x, y + 200, "red dots = where flood edge", 14, 600, C["pt"])
        out += text(x, y + 220, "touches each bank", 14, 600, C["pt"])
        return out

    def s3(x, y, w, h):
        out = axes(x + 25, y + 10, w - 35, 190, "distance downstream", "elevation")
        import math
        for i in range(14):
            a = i / 13
            b = .82 - .55 * a + .07 * math.sin(i * 1.9)
            out += circle(x + 25 + a * (w - 35), y + 10 + (1 - b) * 190, 5, C["pt"], "white", 1)
        out += line(x + 25, y + 10 + .2 * 190, x + w - 10, y + 10 + .73 * 190, C["sea"], 3.5)
        out += text(x + w - 12, y + 40, "fitted water line", 14, 700, C["sea"], "end")
        return out

    def s4(x, y, w, h):
        return cross_section(x, y + 10, w, 210, level=.42)

    return page("01_schumann2007_refix", "A", "REFIX: regression of flood-edge heights",
                "Schumann et al. (2007) · IEEE Transactions on Geoscience and Remote Sensing 45(6)",
                "The flood edge is a contour of the water surface — read its height and fit a smooth line.",
                [("Map the flood from SAR", s1, "Calm floodwater reflects the radar away, so it shows up dark. Trace its outline."),
                 ("Read DEM height at the edge", s2, "Where the flood outline meets each riverbank, the ground height equals the water height."),
                 ("Fit a line downstream", s3, "Edge heights are noisy. A regression line through them gives a smooth water surface (piecewise if weirs or bridges interrupt it)."),
                 ("Depth = line − ground", s4, "Subtract the DEM from the fitted water surface at every flooded pixel.")],
                "SAR flood extent + high-resolution floodplain DEM.",
                "Water-surface line along the reach and a flood-depth map.",
                "≈18 cm RMSE vs surveyed high-water marks (River Alzette, Luxembourg, Jan 2003).",
                "Needs clean bank edges; hydraulic structures (weirs) break a single line — fit in pieces.")


def p02():
    def s1(x, y, w, h):
        return river_plan(x, y + 20, w, 200, True, sections=True) + text(
            x, y + 245, "dashed = cross-sections", 14, 600, C["muted"])

    def s2(x, y, w, h):
        out = cross_section(x, y + 10, w, 200, level=.45, edge_dots=False, depth_at=None, labels=False)
        sy = y + 10 + .45 * 200
        out += line(x + w * .12, sy - 30, x + w * .12, sy + 40, C["edge"], 3, "6 4")
        out += text(x + w * .12 + 6, sy - 34, "SAR edge (off)", 13, 700, C["edge"])
        gx = x + w * .245
        out += circle(gx, sy, 7, C["ok"], "white", 2)
        out += text(gx + 10, sy + 26, "terrain fit", 13, 700, C["ok"])
        out += line(x + w * .12 + 4, sy + 20, gx - 8, sy + 4, C["ink"], 2, marker=True)
        return out

    def s3(x, y, w, h):
        out = axes(x + 25, y + 10, w - 35, 190, "cross-section number", "water level")
        import math
        pts = []
        for i in range(12):
            a = i / 11
            b = .75 - .45 * a + (.18 if i == 5 else .04 * math.sin(i * 2.3))
            px_, py_ = x + 25 + a * (w - 35), y + 10 + (1 - b) * 190
            pts.append((px_, py_))
            out += circle(px_, py_, 5, C["edge"] if i == 5 else C["ok"], "white", 1)
        out += line(x + 25, y + 10 + .25 * 190, x + w - 10, y + 10 + .7 * 190, C["sea"], 3)
        out += text(pts[5][0] + 8, pts[5][1] - 8, "outlier evened out", 13, 700, C["edge"])
        return out

    def s4(x, y, w, h):
        return cross_section(x, y + 10, w, 210, level=.42)

    return page("02_zwenzner_voigt2009", "A", "Cross-sections that snap to the terrain",
                "Zwenzner & Voigt (2009) · Hydrology and Earth System Sciences 13, 567–576",
                "Re-position the SAR flood edge on many cross-sections so it agrees with lidar terrain.",
                [("Cut cross-sections", s1, "Slice across the river every few metres along the reach."),
                 ("Snap edge to terrain", s2, "On each slice, slide the SAR flood edge to the position that best fits the lidar ground — then read the water level."),
                 ("Smooth along the river", s3, "An error on one slice is evened out by its neighbours; big misclassifications must be fixed first."),
                 ("Water level → depth", s4, "Water level minus lidar ground gives the flood depth.")],
                "SAR (or aerial) flood mask + very high-resolution lidar DEM (1–2 m).",
                "Water levels along the river and flood-depth estimates.",
                "Elbe 2002 (Radarsat-1, IKONOS, 1 m lidar) and Severn 2007 (TerraSAR-X, 2 m lidar): depth maps derived.",
                "Dense vegetation, buildings at the edge, and very flat terrain make the edge unreliable.")


def p03():
    def s1(x, y, w, h):
        return (sar_tile(x, y + 5, w * .46, 110, False, "before (normal)")
                + sar_tile(x + w * .54, y + 5, w * .46, 110, True, "during flood")
                + text(x + w / 2, y + 180, "NDFI: how much darker than normal?", 15, 700, C["ink"], "middle")
                + text(x + w / 2, y + 215, "big drop → flood pixel", 15, 700, C["sea"], "middle"))

    def s2(x, y, w, h):
        return grid(x + 10, y + 10, w - 20, 200, BASE_MASK, show_edges=True) + text(
            x + w / 2, y + 240, "red = flood boundary cells", 14, 700, C["edge"], "middle")

    def s3(x, y, w, h):
        cols = [C["gap"]] * 2 + [C["edge"]] * 6 + [C["gap"]] * 2
        return (histogram(x + 10, y + 20, w - 20, 170, [1, 2, 5, 11, 16, 14, 8, 4, 2, 1], None, cols,
                          "boundary elevation (m)")
                + line(x + 10 + .2 * (w - 20), y + 10, x + 10 + .2 * (w - 20), y + 195, C["ink"], 2, "4 3")
                + line(x + 10 + .8 * (w - 20), y + 10, x + 10 + .8 * (w - 20), y + 195, C["ink"], 2, "4 3")
                + text(x + w / 2, y + 245, "trim outliers → robust water level", 14, 700, C["ink"], "middle"))

    def s4(x, y, w, h):
        return cross_section(x, y + 10, w, 210, level=.42)

    return page("03_cian2018", "A", "Change detection + boundary statistics",
                "Cian, Marconcini, Ceccato & Giupponi (2018) · Natural Hazards and Earth System Sciences 18, 3063",
                "Find the flood by comparing with normal conditions, then take a robust statistic of edge heights.",
                [("Detect the flood", s1, "Compare the flood image with the normal backscatter (Normalized Difference Flood Index). A strong darkening = new water."),
                 ("Find the boundary", s2, "Cells where flooded meets dry land form the flood boundary."),
                 ("Statistics on edge heights", s3, "Collect lidar heights along the boundary, discard outliers, and estimate the water-surface elevation."),
                 ("Depth = level − lidar", s4, "Subtract the lidar ground from the water level.")],
                "High-resolution SAR time series (X-band COSMO-SkyMed) + lidar DEM.",
                "Flood extent and flood-depth map — inputs for damage models.",
                "Veneto (Italy) 2010 flood: fast, robust, far less input data than a hydraulic model.",
                "Semi-automatic; needs pre-flood images and a good lidar DEM. Closest analogue to ICEYE + 3DEP.")


def nearest_arrows(x, y, w, h):
    out = grid(x, y, w, h, BASE_MASK, show_edges=True)
    R, Cc = len(BASE_MASK), len(BASE_MASK[0])
    cw, ch = w / Cc, h / R
    for (r, c), (er, ec) in [((3, 4), (2, 3)), ((4, 5), (5, 6)), ((3, 6), (3, 8)), ((4, 3), (4, 1))]:
        out += line(x + c * cw + cw / 2, y + r * ch + ch / 2, x + ec * cw + cw / 2, y + er * ch + ch / 2,
                    C["ink"], 2.2, marker=True)
    return out


def p04():
    def s1(x, y, w, h):
        return (grid(x + 10, y + 10, w - 20, 190, BASE_MASK)
                + legend(x + 10, y + 235, [(C["water_l"], "flooded"), (C["land"], "dry")]))

    def s2(x, y, w, h):
        vals = {(1, 3): "104", (1, 6): "104", (3, 1): "103", (3, 8): "104", (5, 2): "104", (6, 5): "103"}
        return (grid(x + 10, y + 10, w - 20, 190, BASE_MASK, True, vals)
                + text(x + w / 2, y + 235, "edge cells keep their DEM height (m)", 14, 700, C["edge"], "middle"))

    def s3(x, y, w, h):
        return (nearest_arrows(x + 10, y + 10, w - 20, 190)
                + text(x + w / 2, y + 235, "copy height of NEAREST edge cell", 14, 700, C["ink"], "middle"))

    def s4(x, y, w, h):
        return cross_section(x, y + 10, w, 210, level=.42)

    return page("04_cohen2018_fwdet", "B", "FwDET v1: Floodwater Depth Estimation Tool",
                "Cohen et al. (2018) · Journal of the American Water Resources Association",
                "Ground height at the flood edge = water height. Copy it inward, subtract the ground.",
                [("Start with a flood map", s1, "Any flood map works: from SAR, optical, or a model."),
                 ("Find edge cells", s2, "Flooded cells next to dry land. Their DEM height is the local water-surface height."),
                 ("Spread inward", s3, "Each flooded cell takes the water height of its nearest edge cell, then the surface is smoothed."),
                 ("Depth = surface − DEM", s4, "Negative values set to zero. Done — no hydraulics needed.")],
                "Flood-extent map + DEM. Nothing else.",
                "Water-surface elevation and flood-depth rasters, fast at large scale.",
                "Simple GIS/Python tool; the authors present it as a first-order estimate.",
                "Biased where the flood map and DEM don't line up — edge errors spread to every cell.")


def p05():
    coast = [
        "llllllllll",
        "lllwwwwwoo",
        "llwwwwwwoo",
        "lwwwwwwwoo",
        "lwwwwwwwoo",
        "llwwwwwwoo",
        "lllwwwwwoo",
        "llllllllll",
    ]

    def coastal_grid(x, y, w, h, exclude):
        R, Cc = len(coast), len(coast[0])
        cw, ch = w / Cc, h / R
        out = []
        e = edges_of(coast)
        for r in range(R):
            for c in range(Cc):
                k = coast[r][c]
                fill = {"l": C["land"], "w": C["water_l"], "o": C["sea"]}[k]
                shore = k == "w" and c + 1 < Cc and coast[r][c + 1] == "o"
                if (r, c) in e and exclude is not None:
                    fill = C["edge"]
                if shore and exclude is not None:
                    fill = C["gap"] if exclude else C["edge"]
                out.append(f'<rect x="{x+c*cw:.1f}" y="{y+r*ch:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                           f'fill="{fill}" stroke="white" stroke-width="1.5"/>')
                if shore and exclude is False:
                    out.append(text(x + c * cw + cw / 2, y + r * ch + ch / 2 + 5, "0", 12, 800, "white", "middle"))
                if shore and exclude:
                    out.append(text(x + c * cw + cw / 2, y + r * ch + ch / 2 + 5, "×", 15, 800, "white", "middle"))
        return "".join(out)

    def s1(x, y, w, h):
        return (coastal_grid(x + 10, y + 10, w - 20, 190, exclude=None)
                + legend(x + 10, y + 235, [(C["water_l"], "flood"), (C["sea"], "sea"), (C["land"], "land")]))

    def s2(x, y, w, h):
        return (coastal_grid(x + 10, y + 10, w - 20, 190, exclude=False)
                + text(x + w / 2, y + 235, "v1: shoreline edge ≈ 0 m → water too low", 14, 700, C["edge"], "middle"))

    def s3(x, y, w, h):
        return (coastal_grid(x + 10, y + 10, w - 20, 190, exclude=True)
                + text(x + w / 2, y + 235, "v2: shoreline cells are NOT edges", 14, 700, C["ok"], "middle"))

    def s4(x, y, w, h):
        g = [(0, .1), (.25, .55), (.55, .78), (.8, .85), (1, .9)]
        out = cross_section(x, y + 10, w, 210, ground=g, level=.45, depth_at=.55,
                            level_label="surge surface")
        out += text(x + w - 6, y + 235, "sea →", 14, 700, C["sea"], "end")
        out += text(x + 4, y + 235, "← inland", 14, 700, C["muted"])
        return out

    return page("05_cohen2019_fwdet_v2", "B", "FwDET v2.0: coastal floods",
                "Cohen et al. (2019) · Natural Hazards and Earth System Sciences 19, 2053",
                "Where the flood runs into the sea, the shoreline is not a real flood edge — ignore it.",
                [("A coastal flood", s1, "Storm surge or river flood that connects to the ocean has no landward edge on the sea side."),
                 ("The v1 problem", s2, "v1 treats the shoreline as an edge. Its ground height is near sea level, dragging the water surface (and depth) down."),
                 ("v2 fix", s3, "A new boundary scheme drops edge cells that touch the sea; only land-side edges set the water height."),
                 ("Correct coastal depth", s4, "Depths now stay realistic all the way to the coast.")],
                "Flood map + DEM + land/sea mask.",
                "Water depth for coastal and estuarine flooding.",
                "Better coastal depth estimates than v1 for unconfined (open-to-sea) flood domains.",
                "Use for Florida surge events (e.g., Ian); inland rivers behave like v1.")


def p06():
    import math

    def s1(x, y, w, h):
        out = axes(x + 25, y + 10, w - 35, 180, "position along flood edge", "edge height")
        pts = [(x + 25 + i / 29 * (w - 35), y + 10 + 90 + 50 * math.sin(i * 1.7) * (1 if i % 5 else 1.6))
               for i in range(30)]
        out += poly(pts, stroke=C["edge"], sw=2.5, closed=False)
        out += text(x + w / 2, y + 240, "noisy edge → stripes in depth", 14, 700, C["edge"], "middle")
        return out

    def s2(x, y, w, h):
        out = axes(x + 25, y + 10, w - 35, 180, "position along flood edge", "edge height")
        pts = [(x + 25 + i / 29 * (w - 35), y + 10 + 90 + 50 * math.sin(i * 1.7)) for i in range(30)]
        sm = [(a, y + 10 + 90 + 12 * math.sin(i * .35)) for i, (a, _) in enumerate(pts)]
        out += poly(pts, stroke=C["gap"], sw=1.5, closed=False)
        out += poly(sm, stroke=C["ok"], sw=3.5, closed=False)
        out += text(x + w / 2, y + 240, "~10 smoothing passes", 14, 700, C["ok"], "middle")
        return out

    def s3(x, y, w, h):
        g = [(0, .1), (.15, .2), (.3, .75), (.5, .9), (.7, .78), (.85, .45), (1, .4)]
        out = cross_section(x, y + 40, w, 175, ground=g, level=.5, depth_at=None, labels=False)
        out += text(x + 4, y + 22, "← steep slope: drop", 14, 700, C["edge"])
        out += text(x + w - 4, y + 22, "gentle: keep →", 14, 700, C["ok"], "end")
        out += text(x + w / 2, y + 240, "slope threshold ≈ 0.5%", 14, 700, C["ink"], "middle")
        return out

    def s4(x, y, w, h):
        return (bars(x + 10, y + 20, w - 20, 170,
                     [("coarse DEM", 9, C["edge"]), ("medium", 5, C["warn"]), ("10 m NED", 1.5, C["ok"])], 10)
                + text(x + w / 2, y + 245, "sensitivity to settings (schematic)", 14, 700, C["muted"], "middle"))

    return page("06_cohen2022_fwdet_v21", "B", "FwDET v2.1: clean the edge first",
                "Cohen et al. (2022) · Remote Sensing 14(21), 5313",
                "Most depth errors come from bad edge cells — smooth them and drop the ones on steep slopes.",
                [("The problem", s1, "Flood map and DEM never match perfectly. Bad edge heights create stripes and spikes in depth."),
                 ("Smooth edge heights", s2, "Average each edge cell with its neighbours, repeated several times."),
                 ("Filter steep edges", s3, "Edge cells on steep ground are probably misplaced; remove them."),
                 ("Test 16 DEMs", s4, "Run in Google Earth Engine with 16 DEMs. Fine DEMs barely care about the settings.")],
                "Flood map + DEM (+ Google Earth Engine implementation).",
                "Cleaner depth maps with fewer artefacts.",
                "Best: ~10 smoothing iterations + 0.5% slope threshold; 10 m NED far less sensitive than coarse DEMs.",
                "Coarse global DEMs remain sensitive — prefer USGS 3DEP lidar in the US.",
                note="Bar heights in panel 4 are illustrative, not values from the paper.")


def p07():
    gapmask = [
        "llllllllll",
        "lllwwwwlll",
        "llwwnnnwll",
        "lwwwnnnwwl",
        "lwwwwwwwwl",
        "llwwwwwnnl",
        "lllwwwwnnl",
        "llllllllll",
    ]
    filled = [r.replace("n", "f") for r in gapmask]

    def s1(x, y, w, h):
        return (grid(x + 10, y + 10, w - 20, 190, gapmask)
                + legend(x + 10, y + 235, [(C["water_l"], "flood"), (C["gap"], "no data / shadow")]))

    def s2(x, y, w, h):
        return (grid(x + 10, y + 10, w - 20, 190, filled, colors=dict(f=C["water"]))
                + text(x + w / 2, y + 235, "grow flood into gaps lower than water", 14, 700, C["sea"], "middle"))

    def s3(x, y, w, h):
        return (nearest_arrows(x + 10, y + 10, w - 20, 190)
                + text(x + w / 2, y + 235, "depth from boundary terrain elevation", 14, 700, C["ink"], "middle"))

    def s4(x, y, w, h):
        import random
        rnd = random.Random(3)
        a = [(t, min(.98, max(.02, t + rnd.gauss(.08, .17)))) for t in [rnd.random() for _ in range(26)]]
        b = [(t, min(.98, max(.02, t + rnd.gauss(0, .06)))) for t in [rnd.random() for _ in range(26)]]
        return (scatter(x + 30, y + 10, w - 45, 190, a, C["gap"], xl="reference depth", yl="estimated")
                + scatter(x + 30, y + 10, w - 45, 190, b, C["sea"], False)
                + legend(x + 30, y + 245, [(C["gap"], "FwDET"), (C["sea"], "FLEXTH")]))

    return page("07_betterle_salamon2024_flexth", "B", "FLEXTH: depth + filling the blind spots",
                "Betterle & Salamon (2024) · Natural Hazards and Earth System Sciences 24, 2817 (EC Joint Research Centre)",
                "Use terrain logic to fill flood where the satellite was blind, then estimate depth from the edges.",
                [("Flood map with holes", s1, "Satellite maps miss areas (radar shadow, layover, exclusion masks)."),
                 ("Fill the gaps", s2, "Simple morphological/terrain rules expand the flood into no-data areas that must also be under water."),
                 ("Depth from edges", s3, "Water level from terrain elevation at the flood/no-flood boundary, then depth = level − DEM."),
                 ("Compare with FwDET", s4, "Same inputs: FLEXTH shows less bias and scatter around the 1:1 line (e.g., Brazos River, Texas).")],
                "Flood map (e.g., Copernicus GFM from Sentinel-1) + DEM.",
                "Enhanced flood extent + water-depth map, unsupervised, over 100,000s of km².",
                "Open-source Python; being integrated into Copernicus Global Flood Monitoring.",
                "Comparison with FwDET is from the authors' own paper; still limited by flood-map quality.",
                note="Scatter points are illustrative.")


def hand_section(x, y, w, h, hval=.45, show_h=True, flood=True):
    g = [(0, .05), (.2, .35), (.38, .75), (.47, .95), (.53, .95), (.62, .72), (.8, .4), (1, .12)]
    out = cross_section(x, y, w, h, ground=g, level=hval, depth_at=None, labels=False,
                        edge_dots=flood, water=flood)
    sx, sy = x + w * .5, y + h * .95
    out += circle(sx, sy - 4, 6, C["sea"], "white", 2)
    if show_h:
        for fx in (.2, .75):
            gx, gy = x + fx * w, interp([(x + a * w, y + b * h) for a, b in g], x + fx * w)
            out += line(gx, gy, gx, sy, "#1B5E3B", 3, "5 3")
            out += line(gx - 8, sy, gx + 8, sy, "#1B5E3B", 3)
            out += line(gx, sy, sx, sy, "#1B5E3B", 1.5, "2 4")
            out += rect(gx - 24, (gy + sy) / 2 - 15, 48, 20, "white", r=6, op=.9)
            out += text(gx, (gy + sy) / 2, "HAND", 13, 800, "#1B5E3B", "middle")
    return out


def p08():
    def s1(x, y, w, h):
        out = rect(x + 10, y + 10, w - 20, 200, "#EFE6D6", r=10)
        for i in range(6):
            yy = y + 30 + i * 30
            pts = [(x + 15 + j * (w - 30) / 10, yy + 12 * __import__("math").sin(j * .9 + i)) for j in range(11)]
            out += poly(pts, stroke=C["ground_d"], sw=1.6, closed=False, op=.7)
        out += text(x + w / 2, y + 240, "DEM (contours)", 14, 700, C["muted"], "middle")
        return out

    def s2(x, y, w, h):
        out = rect(x + 10, y + 10, w - 20, 200, "#EFE6D6", r=10)
        out += poly([(x + 20, y + 40), (x + 90, y + 90), (x + 150, y + 120), (x + 220, y + 160), (x + w - 20, y + 190)],
                    stroke=C["sea"], sw=5, closed=False)
        out += poly([(x + 60, y + 190), (x + 150, y + 120)], stroke=C["sea"], sw=3, closed=False)
        out += poly([(x + 260, y + 30), (x + 220, y + 160)], stroke=C["sea"], sw=3, closed=False)
        out += text(x + w / 2, y + 240, "trace where water drains", 14, 700, C["sea"], "middle")
        return out

    def s3(x, y, w, h):
        return hand_section(x, y + 10, w, 210, flood=False) + text(
            x + w / 2, y + 245, "height above nearest stream", 14, 700, C["hand"], "middle")

    def s4(x, y, w, h):
        out = hand_section(x, y + 10, w, 210, hval=.55, show_h=False)
        out += text(x + w / 2, y + 30, "river stage h (from flow)", 14, 700, C["sea"], "middle")
        out += text(x + w / 2, y + 245, "flooded if HAND < h; depth = h − HAND", 14, 700, C["ink"], "middle")
        return out

    return page("08_hand_nobre2011_geoflood2018", "C", "HAND: Height Above Nearest Drainage",
                "Nobre et al. (2011) → GeoFlood: Zheng, Maidment, Tarboton, Passalacqua et al. (2018) · Water Resources Research",
                "Every cell's height above its stream tells you how much water it takes to flood it.",
                [("Start with a DEM", s1, "Only terrain is needed — no satellite image."),
                 ("Find the streams", s2, "Compute flow directions and the drainage network."),
                 ("Compute HAND", s3, "For each cell: its height above the stream cell it drains to."),
                 ("Flood to a stage", s4, "Given river stage h (e.g., National Water Model discharge → rating curve), cells with HAND < h are flooded.")],
                "DEM (+ river discharge/stage, or a SAR extent to calibrate h).",
                "Flood extent and depth everywhere along the network, very fast.",
                "Basis of GeoFlood (UT Austin) and NOAA's NWM-HAND inundation mapping.",
                "Ignores hydraulics (backwater, levees); for SAR work best as a false-alarm filter and cross-check.")


def p09():
    def s1(x, y, w, h):
        return hand_section(x, y + 10, w, 200, hval=.6) + text(
            x + w / 2, y + 240, "NWM-HAND predicted flooding", 14, 700, C["hand"], "middle")

    def s2(x, y, w, h):
        out = ""
        for i in range(4):
            out += sar_tile(x + 10 + (i % 2) * (w / 2), y + 10 + (i // 2) * 105, w / 2 - 20, 90, True)
        out += text(x + w / 2, y + 240, "28 remotely-sensed flood maps", 14, 700, C["ink"], "middle")
        return out

    def s3(x, y, w, h):
        return (bars(x + 10, y + 20, w - 20, 170,
                     [("small (<4th)", 3, C["edge"]), ("large (≥4th)", 8, C["ok"])], 10)
                + text(x + w / 2, y + 245, "how well flooding is captured (schematic)", 14, 700, C["muted"], "middle"))

    def s4(x, y, w, h):
        out = rect(x + 10, y + 20, w - 20, 190, "#F7F3EA", r=12)
        out += text(x + 30, y + 60, "Most important knob:", 16, 800)
        out += text(x + 30, y + 92, "channel roughness (Manning's n)", 15, 600, C["sea"])
        out += text(x + 30, y + 118, "in synthetic rating curves", 15, 600, C["sea"])
        out += text(x + 30, y + 160, "→ tune it to fix errors", 15, 700, C["ok"])
        return out

    return page("09_johnson2019_nwm_hand", "C", "Testing HAND inundation against satellites",
                "Johnson et al. (2019) · Natural Hazards and Earth System Sciences 19, 2405",
                "Check NOAA's HAND-based flood maps against real satellite flood maps — where does it fail?",
                [("HAND flood maps", s1, "National Water Model discharge → HAND-based inundation."),
                 ("Satellite truth", s2, "28 remotely sensed flood maps across 54 reach-level catchments."),
                 ("Small streams miss", s3, "Under-predicts flooding in 4th-order and smaller streams; fair for larger rivers."),
                 ("What to tune", s4, "Roughness in the synthetic rating curve matters most.")],
                "NWM-HAND inundation + satellite flood maps.",
                "Where HAND-based mapping can be trusted.",
                "Not accurate cell-by-cell, but useful to highlight at-risk areas on 4th-order+ streams.",
                "HAND alone is too coarse for small creeks (e.g., many Kentucky streams).",
                note="Bar heights are schematic.")


def p10():
    errmask = [
        "llllllllll",
        "lwlwwwwlll",
        "llwwwlwwll",
        "lwwwwwwwwl",
        "lwwwlwwwwl",
        "llwwwwwwlw",
        "lllwwwwlll",
        "llllllllll",
    ]
    fixed = BASE_MASK

    def s1(x, y, w, h):
        return grid(x + 10, y + 10, w - 20, 190, errmask) + text(
            x + w / 2, y + 235, "speckles, holes, false water", 14, 700, C["edge"], "middle")

    def s2(x, y, w, h):
        return grid(x + 10, y + 10, w - 20, 190, fixed) + text(
            x + w / 2, y + 235, "HAND removes high cells, fills low holes", 14, 700, C["hand"], "middle")

    def s3(x, y, w, h):
        out = grid(x + 10, y + 10, w - 20, 190, BASE_MASK, show_edges=True)
        cw, ch = (w - 20) / 10, 190 / 8
        path = [(x + 10 + 8.5 * cw, y + 10 + 3.5 * ch), (x + 10 + 7.5 * cw, y + 10 + 4.5 * ch),
                (x + 10 + 5.5 * cw, y + 10 + 4.5 * ch), (x + 10 + 4.5 * cw, y + 10 + 3.5 * ch)]
        out += poly(path, stroke=C["ink"], sw=2.5, closed=False, dash="5 3")
        out += circle(*path[-1], 5, C["ink"])
        out += text(x + w / 2, y + 235, "spread edge levels by cost-distance", 14, 700, C["ink"], "middle")
        return out

    def s4(x, y, w, h):
        return cross_section(x, y + 10, w, 210, level=.42)

    return page("10_bryant2022_ricorde", "C", "RICorDE: correct the map, then estimate depth",
                "Bryant, McGrath & Boudreault (2022) · Natural Hazards and Earth System Sciences 22, 1437",
                "Fix the satellite flood map with HAND first; then extrapolate edge water levels with cost-distance.",
                [("Imperfect flood map", s1, "RADARSAT flood maps contain misclassified cells."),
                 ("HAND correction", s2, "A HAND sub-model removes implausibly high water and fills low dry gaps."),
                 ("Cost-distance spread", s3, "Edge water levels are pushed inward along terrain-aware paths, not just to the nearest cell."),
                 ("Gridded depth", s4, "Depth = water level − DEM on a regular grid.")],
                "Satellite flood map + DEM (+ HAND derived from it).",
                "Corrected extent and gridded depth.",
                "Outperformed existing tools against hydraulic-model depths for two Canadian floods. Open source (NRCan GitHub).",
                "Built for accuracy, not speed; tested on Canadian data.")


def p11():
    def s1(x, y, w, h):
        return (cross_section(x, y + 10, w, 200, level=.45, labels=False)
                + text(x + w / 2, y + 240, "hydraulic-model depths = reference", 14, 700, C["muted"], "middle"))

    def s2(x, y, w, h):
        out = ""
        for i, (lab, col) in enumerate([("HAND", C["hand"]), ("TVD", C["warn"]), ("FwDET", C["water"])]):
            out += rect(x + 30, y + 20 + i * 70, w - 60, 52, col, r=12, op=.9)
            out += text(x + w / 2, y + 54 + i * 70, lab, 20, 800, "white", "middle")
        return out

    def s3(x, y, w, h):
        return (bars(x + 10, y + 20, w - 20, 170,
                     [("FwDET", .78, C["water"]), ("TVD", 1.39, C["warn"]), ("HAND", 1.75, C["hand"])], 2, " m")
                + text(x + w / 2, y + 245, "RMSE (lower is better)", 14, 700, C["muted"], "middle"))

    def s4(x, y, w, h):
        out = rect(x + 10, y + 10, w - 20, 210, "#F7F3EA", r=12)
        tips = [("FwDET most accurate", C["ok"]), ("& most robust to DEM", C["ok"]),
                ("FwDET under-estimates deep", C["edge"]), ("HAND/TVD over-estimate", C["edge"]),
                ("wide rivers hardest", C["muted"])]
        for i, (t, col) in enumerate(tips):
            out += text(x + 28, y + 45 + i * 38, "• " + t, 15, 700, col)
        return out

    return page("11_teng2022_comparison", "D", "Head-to-head: HAND vs TVD vs FwDET",
                "Teng et al. (2022) · Water Resources Research 58 (CSIRO, Australia)",
                "Run three depth methods on the same floods and score them against hydraulic models.",
                [("Reference depths", s1, "Hydraulic-model depths for many floods in semi-arid Australia."),
                 ("Three methods", s2, "HAND (terrain only), TVD and FwDET (both edge-based)."),
                 ("Score them", s3, "On validation sites FwDET had the lowest error."),
                 ("Lessons", s4, "Edge-based methods beat HAND alone; every method struggles in wide rivers.")],
                "Flood extents + DEMs + hydraulic-model reference depths.",
                "Independent ranking of depth methods.",
                "RMSE ≈ 0.78 m (FwDET), 1.39 m (TVD), 1.75 m (HAND); all improve slightly for bigger floods.",
                "RMSE values from the lead author's presentation slides — verify in the paper before citing.")


def p12():
    def s1(x, y, w, h):
        return (sar_tile(x + 20, y + 10, w - 40, 120, True)
                + chip(x + 20, y + 150, "Lee", C["water"]) + chip(x + 82, y + 150, "Frost", C["water"])
                + chip(x + 162, y + 150, "Gamma-MAP", C["water"])
                + text(x + w / 2, y + 225, "which speckle filter?", 14, 700, C["ink"], "middle"))

    def s2(x, y, w, h):
        return (chip(x + 10, y + 20, "global threshold", C["gap"]) + chip(x + 10, y + 60, "local threshold", C["ok"])
                + chip(x + 10, y + 100, "change detection", C["ok"]) + chip(x + 10, y + 140, "supervised (trained)", C["sea"])
                + text(x + w / 2, y + 225, "which flood-mapping method?", 14, 700, C["ink"], "middle"))

    def s3(x, y, w, h):
        return (chip(x + 10, y + 40, "edge-based depth", C["water"]) + chip(x + 10, y + 80, "other depth methods", C["gap"])
                + text(x + 10, y + 150, "+ every hyperparameter", 15, 700, C["muted"])
                + text(x + w / 2, y + 225, "which depth method & settings?", 14, 700, C["ink"], "middle"))

    def s4(x, y, w, h):
        out = ""
        vals = [("filter", 5), ("mapping", 7), ("depth", 4)]
        acc = 0
        for i, (lab, v) in enumerate(vals):
            out += rect(x + 30, y + 200 - (acc + v) * 12, 70, v * 12, [C["water"], C["warn"], C["hand"]][i], r=4)
            out += text(x + 110, y + 200 - (acc + v / 2) * 12 + 5, lab, 14, 700, C["ink"])
            acc += v
        out += text(x + w / 2, y + 235, "uncertainty adds up step by step", 14, 700, C["muted"], "middle")
        return out

    return page("12_travert2025_benchmark", "D", "Every choice matters: an end-to-end benchmark",
                "Travert, Goeury, Boyaval, Bacchi & Zaoui (2025/2026) · arXiv 2510.11305 → NHESS 26, 2387",
                "Test each step of the SAR→depth chain against hydraulic models and field data to see what really matters.",
                [("Speckle filter", s1, "The choice of filter alone changes the mapped flood area by several km²."),
                 ("Flood mapping", s2, "Supervised methods were best, but tuned local thresholding or change detection came close."),
                 ("Depth estimation", s3, "Depth methods and their hyperparameters are varied too."),
                 ("Track uncertainty", s4, "Uncertainty from each step is quantified to find robust operational settings.")],
                "Sentinel-1 for two Garonne River floods (France, 2019 & 2021) + hydrodynamic simulations + in-situ data.",
                "Which settings are robust, and how uncertain the final depth is.",
                "Extent errors are as important as the depth method. Code public on GitHub (sar-flood-evaluation-framework).",
                "Results are for one river system; re-tune for ICEYE X-band and US terrain.",
                note="Uncertainty bar sizes are illustrative.")


def p13():
    def s1(x, y, w, h):
        return (cross_section(x, y + 10, w, 200, level=.45, labels=False)
                + text(x + w / 2, y + 240, "HEC-RAS 2D gives training depths", 14, 700, C["muted"], "middle"))

    def s2(x, y, w, h):
        out = ""
        for i, (lab, col) in enumerate([("Sentinel-1 backscatter", C["sar"]), ("surface model (DSM)", C["ground_d"]),
                                        ("land use", C["hand"])]):
            out += rect(x + 20, y + 20 + i * 66, w - 40, 50, col, r=10, op=.9)
            out += text(x + w / 2, y + 51 + i * 66, lab, 16, 700, "white", "middle")
        return out

    def s3(x, y, w, h):
        out = ""
        for i, lab in enumerate(["GBR", "RF", "XGB", "LR", "MLP", "KNN", "SVR"]):
            out += chip(x + 15 + (i % 3) * 100, y + 30 + (i // 3) * 50, lab, C["sea"])
        out += text(x + w / 2, y + 225, "7 regression models compared", 14, 700, C["ink"], "middle")
        return out

    def s4(x, y, w, h):
        import random
        rnd = random.Random(5)
        pts = [(t, min(.98, max(.02, t + rnd.gauss(0, .07)))) for t in [rnd.random() * .6 for _ in range(30)]]
        return scatter(x + 30, y + 10, w - 45, 190, pts, C["sea"], xl="HEC-RAS depth", yl="predicted")

    return page("13_elkhrachy2022_ml", "D", "Machine learning regression of depth",
                "Elkhrachy (2022) · Remote Sensing 14(3), 440",
                "Teach a model the link between SAR, terrain, land use and depth using hydraulic-model depths.",
                [("Get training depths", s1, "Simulate a real event (New Cairo, 2018) with HEC-RAS 2D."),
                 ("Collect features", s2, "Per pixel: Sentinel-1 backscatter, surface height, land use."),
                 ("Train regressors", s3, "Gradient boosting, random forest, XGBoost, linear, MLP, k-NN and SVR."),
                 ("Predict depth", s4, "Compare predictions with the held-out simulated depths.")],
                "Sentinel-1 + DSM + land use + a calibrated hydraulic model for training.",
                "Pixel-wise depth prediction.",
                "RMSE 0.18–0.22 m for depths < 1 m (96% of test data).",
                "One event, one city; needs a hydraulic model per site — does not transfer easily.",
                note="Scatter points are illustrative.")


def p14():
    def s1(x, y, w, h):
        return satellite(x + w / 2, y + 40, 1.3) + sar_tile(x + 30, y + 90, w - 60, 120, True) + text(
            x + w / 2, y + 240, "Sentinel-1 (free, every 6–12 days)", 14, 700, C["ink"], "middle")

    def s2(x, y, w, h):
        return grid(x + 10, y + 10, w - 20, 190, BASE_MASK, colors=dict(w=C["water"])) + text(
            x + w / 2, y + 235, "HYDRO30: water extent, 30 m", 14, 700, C["sea"], "middle")

    def s3(x, y, w, h):
        return hand_section(x, y + 10, w, 210, flood=False) + text(
            x + w / 2, y + 245, "HAND from the same DEM", 14, 700, C["hand"], "middle")

    def s4(x, y, w, h):
        return hand_section(x, y + 10, w, 210, hval=.55, show_h=False) + text(
            x + w / 2, y + 245, "FD30: water height fit to extent → depth", 14, 700, C["ink"], "middle")

    return page("14_hydrosar_meyer2024", "N", "HydroSAR: NASA SERVIR flood extent & depth",
                "Meyer et al. (2024) · Remote Sensing 16(17), 3244 · Alaska Satellite Facility / UAF, NASA SERVIR",
                "Automatically turn every Sentinel-1 image into a water map, then use HAND to convert it to depth.",
                [("Sentinel-1 image", s1, "Terrain-corrected Sentinel-1 backscatter (RTC)."),
                 ("Water extent", s2, "HYDRO30: surface-water map for each acquisition."),
                 ("HAND", s3, "Height above nearest drainage, ideally from the same DEM used for terrain correction."),
                 ("Flood depth", s4, "FD30: the water height that matches the mapped extent, minus HAND = depth.")],
                "Sentinel-1 RTC + DEM/HAND.",
                "Operational 30 m water extent (HYDRO30) and flood depth (FD30).",
                "Authors report >90% extent accuracy and <1 m depth error (Hindu Kush Himalaya / South Asia).",
                "Accuracy figures are the authors' own; HAND quality limits depth. Code: 'hydrosar' Python package.")


ALL = [p01, p02, p03, p04, p05, p06, p07, p08, p09, p10, p11, p12, p13, p14]

if __name__ == "__main__":
    for f in ALL:
        print(OUT / f"{f()}.svg")
