"""Fetch USGS 3DEP elevation (public domain) and align it to a SAR grid."""

import math
import os

import numpy as np

TILE_URL = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/"
            "{n}/USGS_13_{n}.tif")


def _gdal_env():
    import rasterio

    ca = os.environ.get("CURL_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if not ca and os.path.exists("/root/.ccr/ca-bundle.crt"):
        ca = "/root/.ccr/ca-bundle.crt"
    kw = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")
    if ca:
        kw.update(GDAL_CURL_CA_BUNDLE=ca, CURL_CA_BUNDLE=ca)
    return rasterio.Env(**kw)


def mosaic_urls(urls, bounds_wgs84, out_path, nodata=-999999.0, label="tile"):
    """Mosaic the parts of remote GeoTIFFs that cover (west, south, east, north).

    Streams only the needed windows over HTTP (/vsicurl). Missing tiles (e.g.
    open ocean) are skipped. Writes float32 with NaN for no-data.
    """
    import rasterio
    from rasterio.merge import merge

    w, s, e, n = bounds_wgs84
    with _gdal_env():
        srcs = []
        for url in urls:
            try:
                srcs.append(rasterio.open("/vsicurl/" + url))
            except rasterio.errors.RasterioIOError:
                print(f"   {label} {url.rsplit('/', 1)[-1]} not available - skipped")
        if not srcs:
            raise RuntimeError(f"No {label}s cover this area.")
        src_nodata = srcs[0].nodata
        mosaic, transform = merge(srcs, bounds=(w, s, e, n), nodata=nodata)
        profile = srcs[0].profile
        for src in srcs:
            src.close()
    arr = mosaic[0].astype("float32")
    arr[arr == np.float32(nodata)] = np.nan
    if src_nodata is not None and np.isfinite(src_nodata):
        arr[arr == np.float32(src_nodata)] = np.nan
    profile.update(driver="GTiff", height=arr.shape[0], width=arr.shape[1], transform=transform,
                   dtype="float32", nodata=np.nan, compress="deflate", tiled=True,
                   blockxsize=512, blockysize=512, count=1)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr, 1)
    return out_path


def fetch_3dep_tiles(bounds_wgs84, out_path):
    """Mosaic USGS 3DEP 1/3 arc-second (~10 m) tiles for (west, south, east, north).

    Streams only the needed windows from the public USGS bucket on AWS S3.
    """
    w, s, e, n = bounds_wgs84
    names = [f"n{lat:02d}w{abs(lon):03d}"
             for lat in range(math.floor(s) + 1, math.ceil(n) + 1)
             for lon in range(math.floor(w), math.ceil(e))]
    out = mosaic_urls([TILE_URL.format(n=nm) for nm in names], bounds_wgs84, out_path,
                      label="3DEP tile")
    import rasterio

    with rasterio.open(out, "r+") as dst:   # 3DEP marks no-data with large negatives
        a = dst.read(1)
        a[a <= -999998] = np.nan
        dst.write(a, 1)
    return out


def fetch_3dep(bounds_wgs84, resolution=10, out_path=None):
    """Get a 3DEP DEM for (west, south, east, north).

    Tries the 3DEP web service via py3dep first, then falls back to streaming
    the 1/3 arc-second tiles from S3 (useful where the web service is blocked).
    """
    try:
        import py3dep

        dem = py3dep.get_dem(tuple(bounds_wgs84), resolution=resolution, crs=4326)
        if out_path:
            dem.rio.to_raster(out_path, compress="deflate")
        return out_path
    except Exception as exc:  # network policy, service outage, ...
        print(f"   py3dep failed ({type(exc).__name__}); using 3DEP tiles on S3 instead")
        return fetch_3dep_tiles(bounds_wgs84, out_path)


def align_to(dem_path, ref_path, resampling="bilinear"):
    """Resample a raster (DEM, HAND, ...) onto the grid of ref_path. Returns float32."""
    import rasterio
    from rasterio.warp import reproject, Resampling

    with rasterio.open(ref_path) as ref:
        out = np.full((ref.height, ref.width), np.nan, dtype="float32")
        dst_transform, dst_crs = ref.transform, ref.crs
    with rasterio.open(dem_path) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=dst_transform,
                  dst_crs=dst_crs, dst_nodata=np.nan, resampling=Resampling[resampling])
    return out
