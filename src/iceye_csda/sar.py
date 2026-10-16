"""Radiometric calibration, speckle filtering and geocoding of ICEYE products.

Calibration follows ICEYE's product documentation:
    beta0  = calibration_factor * DN**2
    sigma0 = beta0 * sin(incidence_angle)
"""

import numpy as np
from scipy.ndimage import uniform_filter


def incidence_grid(shape, md):
    """Incidence angle (radians) for every pixel.

    Varies linearly across range (columns) from near to far when both are
    known; otherwise uses the scene-centre value. Assumes columns increase in
    range, which holds for ICEYE GRD in its native (not map-projected) geometry.
    """
    rows, cols = shape
    near, far = md.get("incidence_near"), md.get("incidence_far")
    if isinstance(near, float) and isinstance(far, float):
        line = np.linspace(near, far, cols, dtype="float32")
        return np.deg2rad(np.broadcast_to(line, (rows, cols)))
    center = md.get("incidence_center")
    if not isinstance(center, float):
        raise ValueError("No incidence angle in metadata; cannot compute sigma0.")
    return np.full(shape, np.deg2rad(center), dtype="float32")


def calibrate_sigma0(dn, md):
    """Convert amplitude DN to linear sigma0. Zero DN (no data) becomes NaN."""
    k = md.get("calibration_factor")
    if not isinstance(k, float):
        raise ValueError("calibration_factor missing from metadata.")
    dn = dn.astype("float32")
    sigma0 = k * dn**2 * np.sin(incidence_grid(dn.shape, md))
    sigma0[dn == 0] = np.nan
    return sigma0


def slc_to_amplitude(i, q, looks=(1, 1)):
    """Amplitude from SLC I/Q with optional (azimuth, range) multilooking.

    Multilooking averages intensity, then takes sqrt so the result can be
    calibrated like GRD DN.
    """
    intensity = i.astype("float32") ** 2 + q.astype("float32") ** 2
    la, lr = looks
    if la > 1 or lr > 1:
        r, c = (intensity.shape[0] // la) * la, (intensity.shape[1] // lr) * lr
        intensity = intensity[:r, :c].reshape(r // la, la, c // lr, lr).mean(axis=(1, 3))
    return np.sqrt(intensity)


def to_db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(x)


def lee_filter(img, size=5):
    """Classic Lee speckle filter on linear intensity. NaNs are preserved."""
    valid = np.isfinite(img)
    x = np.where(valid, img, 0.0).astype("float64")
    w = uniform_filter(valid.astype("float64"), size)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = uniform_filter(x, size) / w
        sq_mean = uniform_filter(x**2, size) / w
    var = np.maximum(sq_mean - mean**2, 0)
    noise_var = np.nanmean(var)
    denom = var + noise_var
    with np.errstate(invalid="ignore", divide="ignore"):
        weight = np.where(denom > 0, var / denom, 0.0)
    out = mean + weight * (x - mean)
    out[~valid] = np.nan
    return out.astype("float32")


def utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def geocode(src_path, array, out_path, resolution=10.0, dst_crs=None):
    """Reproject array (same shape as src_path's band 1) to a UTM GeoTIFF.

    Uses the file's geotransform if it has one, otherwise its GCPs (ICEYE GRD
    in native geometry ships with GCPs). Keeps ICEYE copyright tags.
    """
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds

    with rasterio.open(src_path) as src:
        tags = src.tags()
        if src.crs and not src.transform.is_identity:
            src_kw = dict(src_crs=src.crs, src_transform=src.transform)
            bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            calc_kw = dict(left=src.bounds.left, bottom=src.bounds.bottom,
                           right=src.bounds.right, top=src.bounds.top)
            src_crs = src.crs
        else:
            gcps, gcp_crs = src.gcps
            if not gcps:
                raise ValueError(f"{src_path} has neither a geotransform nor GCPs.")
            src_kw = dict(gcps=gcps, src_crs=gcp_crs)
            calc_kw = dict(gcps=gcps)
            src_crs = gcp_crs
            xs, ys = [g.x for g in gcps], [g.y for g in gcps]
            bounds = transform_bounds(gcp_crs, "EPSG:4326", min(xs), min(ys), max(xs), max(ys))
        height, width = src.height, src.width

    lon, lat = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    dst_crs = dst_crs or f"EPSG:{utm_epsg(lon, lat)}"
    transform, w, h = calculate_default_transform(
        src_crs, dst_crs, width, height, resolution=resolution, **calc_kw
    )
    out = np.full((h, w), np.nan, dtype="float32")
    reproject(array.astype("float32"), out, dst_transform=transform, dst_crs=dst_crs,
              src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear, **src_kw)

    profile = dict(driver="GTiff", height=h, width=w, count=1, dtype="float32",
                   crs=dst_crs, transform=transform, nodata=np.nan,
                   compress="deflate", tiled=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out, 1)
        dst.update_tags(**tags)
    return out_path
