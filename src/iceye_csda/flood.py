"""Flood extent (open water) mapping and flood depth estimation.

Depth uses the Floodwater Depth Estimation Tool idea (FwDET; Cohen et al. 2018,
2019): elevations along the flood boundary approximate the water surface;
each flooded pixel takes the water-surface elevation of its nearest boundary
pixel (then smoothed), and depth = water surface - ground elevation.
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
    labels, n = ndimage.label(mask)
    if n:
        sizes = ndimage.sum(mask, labels, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes >= min_pixels
        mask = keep[labels]
    return mask, t


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
