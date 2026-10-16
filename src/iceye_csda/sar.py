"""Radiometric calibration, speckle filtering and geocoding of ICEYE products.

Calibration follows ICEYE's product documentation:
    beta0  = calibration_factor * DN**2
    sigma0 = beta0 * sin(incidence_angle)
"""

import numpy as np
from scipy.ndimage import uniform_filter


def _range_axis(shape, md):
    """Which array axis runs along range: 0 (rows) or 1 (columns).

    With an incidence polynomial, pick the axis whose length reproduces the
    far-range angle. Otherwise use the product orientation ("shadows-down/up"
    means range runs down the rows); default to columns.
    """
    coeffs, far = md.get("incidence_coeffs"), md.get("incidence_far")
    if coeffs and isinstance(far, float):
        errs = [abs(np.polyval(coeffs[::-1], n - 1) - far) for n in shape]
        return int(np.argmin(errs))
    orient = str(md.get("orientation", "")).lower()
    return 0 if ("down" in orient or "up" in orient) else 1


def incidence_grid(shape, md, step=1, full_shape=None):
    """Incidence angle (radians) for every pixel of an array of `shape`.

    `step` > 1 means the array is a block-average (multilook) of the full-
    resolution product with shape `full_shape`; pixel i covers full-resolution
    indices i*step ... i*step+step-1.
    """
    full_shape = full_shape or shape
    axis = _range_axis(full_shape, md)
    n = shape[axis]
    idx = np.arange(n, dtype="float64") * step + (step - 1) / 2
    coeffs = md.get("incidence_coeffs")
    near, far = md.get("incidence_near"), md.get("incidence_far")
    if coeffs:
        theta = np.polyval(coeffs[::-1], idx)
    elif isinstance(near, float) and isinstance(far, float):
        theta = near + (far - near) * idx / max(full_shape[axis] - 1, 1)
    elif isinstance(md.get("incidence_center"), float):
        theta = np.full(n, md["incidence_center"])
    else:
        raise ValueError("No incidence angle in metadata; cannot compute sigma0.")
    theta = np.deg2rad(theta).astype("float32")
    if axis == 0:
        return np.broadcast_to(theta[:, None], shape)
    return np.broadcast_to(theta[None, :], shape)


def _cal_factor(md):
    k = md.get("calibration_factor")
    if not isinstance(k, float):
        raise ValueError("calibration_factor missing from metadata.")
    return k


def calibrate_sigma0(dn, md):
    """Convert amplitude DN to linear sigma0. Zero DN (no data) becomes NaN."""
    dn = dn.astype("float32")
    sigma0 = _cal_factor(md) * dn**2 * np.sin(incidence_grid(dn.shape, md))
    sigma0[dn == 0] = np.nan
    return sigma0


def _affine_from_list(t):
    """Affine from a 6/9-element list in either rasterio or GDAL order.

    STAC says rasterio order [a, b, c, d, e, f] (origins at 2 and 5); some ICEYE
    products write GDAL order [c, a, b, f, d, e] (origins at 0 and 3). The
    origin terms are the large ones, which tells the two apart.
    """
    from affine import Affine

    t = [float(v) for v in t[:6]]
    if abs(t[0]) + abs(t[3]) > abs(t[2]) + abs(t[5]):
        return Affine.from_gdal(*t)
    return Affine(*t)


def georeference(path, md):
    """Return dict(src_crs=..., src_transform=...) or dict(src_crs=..., gcps=...).

    Looks in the GeoTIFF first, then in the metadata sidecar (proj:transform),
    as ICEYE open-data GRD COGs carry their geotransform only in the JSON.
    """
    import rasterio

    with rasterio.open(path) as src:
        if src.crs and not src.transform.is_identity:
            return dict(src_crs=src.crs, src_transform=src.transform)
        gcps, gcp_crs = src.gcps
        if gcps:
            return dict(src_crs=gcp_crs, gcps=gcps)
    t, code = md.get("proj:transform"), md.get("proj:code")
    if t and code:
        return dict(src_crs=rasterio.crs.CRS.from_string(code), src_transform=_affine_from_list(t))
    raise ValueError(f"No georeferencing found for {path} (file or metadata).")


def scale_georef(geo, factor):
    """Adjust georeferencing for an array multilooked by `factor` in both axes."""
    if factor == 1:
        return geo
    if "gcps" in geo:
        from rasterio.control import GroundControlPoint as G

        g = [G(row=p.row / factor, col=p.col / factor, x=p.x, y=p.y, z=p.z) for p in geo["gcps"]]
        return dict(src_crs=geo["src_crs"], gcps=g)
    from affine import Affine

    return dict(src_crs=geo["src_crs"], src_transform=geo["src_transform"] * Affine.scale(factor))


def read_multilooked(path, factor):
    """Read a GRD GeoTIFF, average intensity (amplitude²) in factor×factor blocks.

    Processes in row strips so a full ICEYE scene (≈800 MB) fits in memory.
    Returns (mean_DN², full_shape).
    """
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(path) as src:
        H, W = src.height, src.width
        h, w = H // factor, W // factor
        out = np.empty((h, w), dtype="float32")
        # Some products (e.g. ICEYE open-data COGs) store amplitude as
        # DN * scale + offset in the GeoTIFF band metadata.
        scale = (src.scales or (1.0,))[0] or 1.0
        offset = (src.offsets or (0.0,))[0] or 0.0
        rows_per = max(1, 4096 // factor) * factor
        for r0 in range(0, h * factor, rows_per):
            nr = min(rows_per, h * factor - r0)
            dn = src.read(1, window=Window(0, r0, w * factor, nr)).astype("float32")
            amp = np.clip(dn * scale + offset, 0, None)
            inten = amp**2
            inten[dn == 0] = np.nan
            blk = inten.reshape(nr // factor, factor, w, factor)
            with np.errstate(invalid="ignore"):
                out[r0 // factor:(r0 + nr) // factor] = np.nanmean(blk, axis=(1, 3))
        return out, (H, W)


def calibrate_intensity(mean_dn2, md, step=1, full_shape=None):
    """Linear sigma0 from (multilooked) DN² intensity."""
    theta = incidence_grid(mean_dn2.shape, md, step, full_shape)
    return (_cal_factor(md) * mean_dn2 * np.sin(theta)).astype("float32")


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


def geocode_array(array, out_path, src_crs, src_transform=None, gcps=None,
                  resolution=10.0, dst_crs=None, tags=None):
    """Reproject an array with a (possibly rotated) geotransform or GCPs to UTM."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, Resampling, transform as warp_xy

    h0, w0 = array.shape
    if gcps:
        xs, ys = [g.x for g in gcps], [g.y for g in gcps]
    else:
        corners = [src_transform * (c, r) for c, r in ((0, 0), (w0, 0), (0, h0), (w0, h0))]
        xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    lon, lat = warp_xy(src_crs, "EPSG:4326", [sum(xs) / len(xs)], [sum(ys) / len(ys)])
    dst_crs = dst_crs or f"EPSG:{utm_epsg(lon[0], lat[0])}"
    X, Y = warp_xy(src_crs, dst_crs, xs, ys)
    left, top = min(X), max(Y)
    w = int(np.ceil((max(X) - left) / resolution))
    h = int(np.ceil((top - min(Y)) / resolution))
    transform = from_origin(left, top, resolution, resolution)

    out = np.full((h, w), np.nan, dtype="float32")
    src_kw = dict(gcps=gcps) if gcps else dict(src_transform=src_transform)
    reproject(array.astype("float32"), out, src_crs=src_crs, dst_transform=transform,
              dst_crs=dst_crs, src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.bilinear, **src_kw)
    profile = dict(driver="GTiff", height=h, width=w, count=1, dtype="float32",
                   crs=dst_crs, transform=transform, nodata=np.nan,
                   compress="deflate", tiled=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out, 1)
        if tags:
            dst.update_tags(**tags)
    return out_path


def geocode(src_path, array, out_path, resolution=10.0, dst_crs=None):
    """Geocode a full-resolution array that matches src_path's band 1."""
    import rasterio

    with rasterio.open(src_path) as src:
        tags = src.tags()
        if src.crs and not src.transform.is_identity:
            kw = dict(src_crs=src.crs, src_transform=src.transform)
        else:
            gcps, gcp_crs = src.gcps
            if not gcps:
                raise ValueError(f"{src_path} has neither a geotransform nor GCPs.")
            kw = dict(src_crs=gcp_crs, gcps=gcps)
    return geocode_array(array, out_path, resolution=resolution, dst_crs=dst_crs, tags=tags, **kw)
