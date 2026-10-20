"""Flood extent (open water) mapping and flood depth estimation.

Water extent:
  - tile_threshold: split-based thresholding (Martinis et al. 2009; Chini et al.
    2017). The scene is cut into tiles; only tiles that clearly contain both
    water and land (bimodal histogram) are used to pick the threshold, so a
    scene dominated by land or by open water still gets a sensible value.
  - grow_water: region growing from confident water seeds into slightly
    brighter connected pixels (rough water edges, wind ripples near shore).
  - map_water: threshold + growing + HAND / slope exclusion masks.

Depth:
  - flood_depth (FwDET; Cohen et al. 2018, 2019): elevations along the flood
    boundary approximate the water surface; each flooded pixel takes the
    water-surface elevation of its nearest boundary pixel (then smoothed).
  - flexth_depth (FLEXTH concept; Betterle & Salamon 2024, NHESS): unreliable
    boundary pixels are discarded first, the water level is interpolated from
    several nearby boundary pixels (inverse-distance weights), and the flood is
    allowed to extend into connected, lower-lying pixels the SAR map missed.
    This is our implementation of the published idea, not the authors' code.
"""

import numpy as np
from scipy import ndimage


def otsu_threshold(values, bins=256):
    """Otsu threshold of a 1-D array of finite values."""
    v = values[np.isfinite(values)]
    hist, edges = np.histogram(v, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centers)
    mu0 = m0 / np.maximum(w0, 1)
    mu1 = (m0[-1] - m0) / np.maximum(w1, 1)
    between = w0 * w1 * (mu0 - mu1) ** 2
    return float(centers[np.argmax(between)])


def water_mask(sigma0_db, threshold_db=None, min_pixels=50):
    """Open water = low backscatter. Returns (mask, threshold_used).

    Note: smooth surfaces (tarmac, radar shadow) also look dark; mask them
    with slope / HAND layers for production work. Flooded vegetation and
    urban areas can appear *bright* (double bounce) and are missed here.
    """
    t = otsu_threshold(sigma0_db) if threshold_db is None else float(threshold_db)
    mask = np.isfinite(sigma0_db) & (sigma0_db < t)
    mask = ndimage.binary_opening(mask, iterations=1)
    return _remove_small(mask, min_pixels), t


def tile_threshold(db, tile=256, min_valid=0.8, frac_range=(0.1, 0.9), min_ashman=2.0,
                   min_sep_db=3.0, min_tiles=5):
    """Scene threshold from bimodal tiles only. Returns (threshold, info).

    A tile is used when its Otsu split leaves 10-90 % of pixels on the water
    side, the two classes are well separated (Ashman's D >= 2 and >= 3 dB apart),
    and it is mostly valid data. The threshold is Otsu on the pooled pixels of
    the selected tiles. Falls back to whole-scene Otsu if too few tiles qualify.
    """
    rows, cols = db.shape
    selected, tile_t = [], []
    n_tiles = 0
    for r in range(0, rows - tile + 1, tile):
        for c in range(0, cols - tile + 1, tile):
            v = db[r:r + tile, c:c + tile].ravel()
            n_tiles += 1
            v = v[np.isfinite(v)]
            if v.size < min_valid * tile * tile:
                continue
            t = otsu_threshold(v)
            lo, hi = v[v < t], v[v >= t]
            frac = lo.size / v.size
            if not (frac_range[0] <= frac <= frac_range[1]):
                continue
            sep = hi.mean() - lo.mean()
            ashman = np.sqrt(2) * sep / np.sqrt(lo.var() + hi.var() + 1e-12)
            if ashman >= min_ashman and sep >= min_sep_db:
                selected.append(v)
                tile_t.append(t)
    info = {"tiles": n_tiles, "tiles_selected": len(selected)}
    if len(selected) < min_tiles:
        info["method"] = "otsu (whole scene; too few bimodal tiles)"
        return otsu_threshold(db), info
    info["method"] = "tiles"
    info["tile_threshold_range"] = (float(np.min(tile_t)), float(np.max(tile_t)))
    return otsu_threshold(np.concatenate(selected)), info


def grow_water(db, seeds, grow_threshold):
    """Keep pixels darker than grow_threshold that are connected to a seed."""
    candidate = (np.isfinite(db) & (db < grow_threshold)) | seeds
    labels, n = ndimage.label(candidate)
    if not n:
        return seeds.copy()
    keep = np.zeros(n + 1, bool)
    keep[np.unique(labels[seeds])] = True
    keep[0] = False
    return keep[labels]


def _remove_small(mask, min_pixels):
    labels, n = ndimage.label(mask)
    if not n:
        return mask
    sizes = ndimage.sum(mask, labels, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_pixels
    return keep[labels]


def map_water(sigma0_db, method="tiles", threshold_db=None, tile=256, grow_db=1.0,
              min_pixels=50, hand=None, hand_max=15.0, slope=None, slope_max=5.0):
    """Open-water mask with exclusion layers. Returns (mask, info).

    method: "tiles" (split-based), "otsu" (whole scene) or "fixed" (threshold_db).
    hand / slope: optional arrays on the same grid. Water is rejected where HAND
    > hand_max metres (too high above the drainage network to be flooded) or
    slope > slope_max degrees (dark pixels on slopes are usually radar shadow).
    """
    if threshold_db is not None or method == "fixed":
        t, info = float(threshold_db), {"method": "fixed"}
    elif method == "tiles":
        t, info = tile_threshold(sigma0_db, tile=tile)
    else:
        t, info = otsu_threshold(sigma0_db), {"method": "otsu"}
    info["threshold_db"] = t
    seeds = np.isfinite(sigma0_db) & (sigma0_db < t)
    seeds = ndimage.binary_opening(seeds, iterations=1)
    mask = grow_water(sigma0_db, seeds, t + grow_db) if grow_db else seeds
    info["grown_pixels"] = int(mask.sum() - seeds.sum())
    excluded = np.zeros(mask.shape, bool)
    if hand is not None:
        excluded |= np.isfinite(hand) & (hand > hand_max)
    if slope is not None:
        excluded |= np.isfinite(slope) & (slope > slope_max)
    info["excluded_pixels"] = int((mask & excluded).sum())
    mask = _remove_small(mask & ~excluded, min_pixels)
    return mask, info


def flood_boundary(mask, valid):
    """Water pixels touching dry land (ignoring edges against no-data)."""
    dry = valid & ~mask
    touches_dry = ndimage.binary_dilation(dry, structure=np.ones((3, 3)))
    return mask & touches_dry


def flood_depth(mask, dem, smoothing_px=15, valid=None):
    """Estimate water depth (same units as dem) for every flooded pixel.

    mask: boolean flood extent; dem: ground elevation on the same grid.
    Returns float32 array, NaN outside the flood extent.
    """
    if valid is None:
        valid = np.isfinite(dem)
    mask = mask & valid
    boundary = flood_boundary(mask, valid)
    if not boundary.any():
        return np.full(mask.shape, np.nan, "float32")

    # Water surface elevation from the nearest boundary pixel.
    _, (iy, ix) = ndimage.distance_transform_edt(~boundary, return_indices=True)
    wse = dem[iy, ix].astype("float64")

    # Smooth the surface over flooded pixels only (normalised mean filter).
    if smoothing_px and smoothing_px > 1:
        w = ndimage.uniform_filter(mask.astype("float64"), smoothing_px)
        s = ndimage.uniform_filter(np.where(mask, wse, 0.0), smoothing_px)
        with np.errstate(invalid="ignore", divide="ignore"):
            wse = np.where(w > 0, s / w, wse)

    depth = np.clip(wse - dem, 0, None).astype("float32")
    depth[~mask] = np.nan
    return depth


def _boundary_points(mask, valid, dem, slope=None, slope_max=5.0, k_local=30, max_mad=3.0):
    """Boundary pixels kept by the FLEXTH-style quality filter. Returns (rows, cols, z, info)."""
    from scipy.spatial import cKDTree

    b = flood_boundary(mask, valid) & np.isfinite(dem)
    n_all = int(b.sum())
    if slope is not None:
        b &= ~(np.isfinite(slope) & (slope > slope_max))
    r, c = np.nonzero(b)
    z = dem[r, c].astype("float64")
    n_slope = r.size
    if r.size > k_local:
        # Drop edge elevations that disagree with their neighbourhood (trees,
        # levees, buildings on the edge): |z - local median| > max_mad * MAD.
        tree = cKDTree(np.c_[r, c])
        _, idx = tree.query(np.c_[r, c], k=k_local, workers=-1)
        local = z[idx]
        med = np.median(local, axis=1)
        mad = 1.4826 * np.median(np.abs(local - med[:, None]), axis=1)
        ok = np.abs(z - med) <= max_mad * mad + 0.10
        r, c, z = r[ok], c[ok], z[ok]
    info = {"edge_pixels": n_all, "edge_after_slope": n_slope, "edge_kept": int(r.size)}
    return r, c, z, info


def _idw(tree, z, edge_body, pts, pts_body, k, power=2.0, chunk=500_000):
    """Inverse-distance water level from the k nearest edge pixels of the same water body.

    Returns (level, distance to nearest edge). Edges of other water bodies are
    ignored unless none of the k nearest belong to the pixel's own body.
    """
    k = min(k, z.size)
    level = np.empty(len(pts))
    dmin = np.empty(len(pts))
    for i in range(0, len(pts), chunk):
        d, idx = tree.query(pts[i:i + chunk], k=k, workers=-1)
        if k == 1:
            d, idx = d[:, None], idx[:, None]
        w = np.maximum(d, 0.5) ** -power
        same = edge_body[idx] == pts_body[i:i + chunk, None]
        none = ~same.any(1)
        w = np.where(same | none[:, None], w, 0.0)
        level[i:i + chunk] = (w * z[idx]).sum(1) / w.sum(1)
        dmin[i:i + chunk] = d[:, 0]
    return level, dmin


def small_holes(mask, max_px):
    """Dry patches fully enclosed by water and no larger than max_px pixels."""
    holes = ndimage.binary_fill_holes(mask) & ~mask
    if not max_px or not holes.any():
        return np.zeros(mask.shape, bool)
    labels, n = ndimage.label(holes)
    sizes = ndimage.sum(holes, labels, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes <= max_px
    return keep[labels]


def flexth_depth(mask, dem, valid=None, slope=None, edge_slope_max=5.0, edge_max_mad=3.0,
                 neighbours=8, extend_px=50, hand=None, hand_max=15.0, min_depth=0.05,
                 hole_px=500, report=None, extend_max_depth=1.5):
    """FLEXTH-style water level and depth. Returns (depth, extended, info).

    mask: water extent used to find the flood edge (include permanent water).
    hole_px: small dry patches enclosed by water (often bright flooded
    vegetation or wind-roughened water, not real islands) do not count as
    flood edge; they are re-tested against the water level like other gaps.
    report: pixels of mask that need a depth (default all of mask), e.g. flood
    water without permanent water. Extension is only grown from these.
    extend_max_depth: extension only adds pixels that would be at most this
    deep. SAR misses shallow water (vegetation, rough edges); deep open water
    shows up dark, so a deep "missed" area means the water level is wrong.
    depth: float32 metres, NaN outside report | extended.
    extended: pixels outside the SAR mask added because they are connected to
    the flood and lie below the interpolated water level (within extend_px).
    """
    from scipy.spatial import cKDTree

    if valid is None:
        valid = np.isfinite(dem)
    mask = mask & valid
    holes = small_holes(mask, hole_px) & valid
    r, c, z, info = _boundary_points(mask | holes, valid, dem, slope, edge_slope_max,
                                     max_mad=edge_max_mad)
    info["hole_pixels"] = int(holes.sum())
    empty = np.full(mask.shape, np.nan, "float32")
    if z.size == 0:
        return empty, np.zeros(mask.shape, bool), info
    # The water level is interpolated only from the edge of the same water
    # body: a pond at 4 m must not raise the level of the river next to it.
    body, _ = ndimage.label(mask | holes)
    edge_body = body[r, c]
    tree = cKDTree(np.c_[r, c])
    report = mask if report is None else report & mask

    # Candidate pixels for extension: dry, valid, near the flood, low HAND.
    extended = np.zeros(mask.shape, bool)
    if extend_px:
        dist, (ny, nx) = ndimage.distance_transform_edt(~mask, return_indices=True)
        near_report = report[ny, nx]                 # closest water pixel needs a depth
        cand = ((valid & ~mask & (dist <= extend_px)) | holes) & near_report
        if hand is not None:
            cand &= ~(np.isfinite(hand) & (hand > hand_max))
        cr, cc = np.nonzero(cand)
        if cr.size:
            near_body = body[ny[cr, cc], nx[cr, cc]]   # water body of the closest water pixel
            wse_c, _ = _idw(tree, z, edge_body, np.c_[cr, cc], near_body, 4 * neighbours)
            low = np.zeros(mask.shape, bool)
            gap = wse_c - dem[cr, cc]
            low[cr, cc] = (gap > min_depth) & (gap <= extend_max_depth)
            labels, n = ndimage.label(low | report)
            keep = np.zeros(n + 1, bool)
            keep[np.unique(labels[report])] = True
            keep[0] = False
            extended = keep[labels] & low

    wet = report | extended
    wr, wc = np.nonzero(wet)
    wet_body = body.copy()
    if extend_px:
        wet_body[extended] = body[ny, nx][extended]
    wse, dmin = _idw(tree, z, edge_body, np.c_[wr, wc], wet_body[wr, wc], 4 * neighbours)
    depth = empty
    depth[wr, wc] = np.clip(wse - dem[wr, wc], 0, None)
    info["extended_pixels"] = int(extended.sum())
    info["median_edge_distance_px"] = float(np.median(dmin)) if dmin.size else float("nan")
    return depth, extended, info
