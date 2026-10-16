"""Fetch USGS 3DEP elevation (public domain) and align it to a SAR grid."""

import numpy as np


def fetch_3dep(bounds_wgs84, resolution=10, out_path=None):
    """Download a 3DEP DEM covering (west, south, east, north) via py3dep."""
    import py3dep

    dem = py3dep.get_dem(tuple(bounds_wgs84), resolution=resolution, crs=4326)
    if out_path:
        dem.rio.to_raster(out_path, compress="deflate")
    return dem


def align_to(dem_path, ref_path):
    """Resample a DEM onto the grid of ref_path. Returns float32 array (metres)."""
    import rasterio
    from rasterio.warp import reproject, Resampling

    with rasterio.open(ref_path) as ref:
        out = np.full((ref.height, ref.width), np.nan, dtype="float32")
        dst_transform, dst_crs = ref.transform, ref.crs
    with rasterio.open(dem_path) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=dst_transform,
                  dst_crs=dst_crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    return out
