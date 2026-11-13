"""Gauge-driven flood maps from lidar: one 'flood-at' raster turns any river level into a map.

For every pixel near the river, flood_at = ground elevation minus the elevation of the
nearest river water surface in the lidar (the lidar's hydro-flattened river surface,
i.e. the water level on the survey day). If the river rises by dH metres above its
survey-day level everywhere along the reach (the water surface stays parallel to the
survey-day surface), a pixel is flooded when flood_at < dH and it is connected to the
river; depth = dH - flood_at. dH comes from the gauge:

    dH(t) = WSE_gauge(t) - river surface at the gauge on the survey day + offset

The offset is the single calibrated number (e.g. against satellite water maps).
Limits: no flow dynamics, no levee failure, tributary backwater only by connectivity,
karst sinkholes are not connected to the river and so never flood in this model.
"""

import numpy as np
from scipy import ndimage


def river_surface(dem, channel, window_px=11):
    """Water-surface elevation along the channel: local minimum of the DEM over channel
    pixels (the 30 m channel mask spills onto banks; the minimum keeps the water surface).
    Returns an array with values on channel pixels, NaN elsewhere."""
    z = np.where(channel & np.isfinite(dem), dem, np.inf)
    zmin = ndimage.minimum_filter(z, size=window_px)
    return np.where(channel & np.isfinite(zmin) & (zmin < np.inf), zmin, np.nan)


def flood_at(dem, surface, max_dist_px=None):
    """Height above the nearest river water surface (m). NaN where there is no DEM,
    no river within max_dist_px, or the nearest river surface is unknown."""
    has = np.isfinite(surface)
    dist, (iy, ix) = ndimage.distance_transform_edt(~has, return_indices=True)
    out = dem - surface[iy, ix]
    out[~np.isfinite(dem)] = np.nan
    if max_dist_px is not None:
        out[dist > max_dist_px] = np.nan
    return out.astype("float32")


def flood_map(fa, dh, channel):
    """Flooded pixels for a rise dh: flood_at < dh and connected to the channel."""
    low = np.isfinite(fa) & (fa < dh)
    lab, n = ndimage.label(low | channel)
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[channel])] = True
    keep[0] = False
    return keep[lab] & low


def depth(fa, dh, wet):
    return np.where(wet, dh - fa, np.nan).astype("float32")


def area_curve(fa, channel, levels, pixel_area_m2):
    """Flooded area (km2, outside the channel) for each rise in `levels`."""
    return np.array([(flood_map(fa, h, channel) & ~channel).sum() * pixel_area_m2 / 1e6 for h in levels])


def aggregate_fraction(mask, factor):
    """Fraction of True sub-pixels in factor x factor blocks (fine grid -> coarse grid)."""
    r, c = (mask.shape[0] // factor) * factor, (mask.shape[1] // factor) * factor
    m = mask[:r, :c].astype("float32")
    return m.reshape(r // factor, factor, c // factor, factor).mean(axis=(1, 3))


def connected_level(fa, channel):
    """Lowest river rise at which each pixel is flooded AND connected to the river.

    This is the minimax path height from the channel (morphological reconstruction by
    erosion of flood_at, seeded at the channel). With it, the map for any rise dh is
    simply `level < dh`, so thousands of daily maps need no connectivity search.
    """
    from skimage.morphology import reconstruction

    big = float(np.nanmax(fa)) + 1000 if np.isfinite(fa).any() else 1e6
    mask = np.where(np.isfinite(fa), fa, big).astype("float64")
    seed = np.where(channel, np.minimum(mask, 0.0), big)
    seed = np.maximum(seed, mask)             # reconstruction by erosion needs seed >= mask
    level = reconstruction(seed, mask, method="erosion")
    level[~np.isfinite(fa)] = np.nan
    return level.astype("float32")


NHD = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"


def nhd_river(bounds_wgs84, river_name, cache=None):
    """USGS NHD large-scale flowlines of one named river plus NHD area polygons (GeoJSON dict)."""
    import json

    import requests

    if cache is not None and cache.exists():
        return json.loads(cache.read_text())
    feats = []
    for layer, where in ((6, f"gnis_name='{river_name}'"), (9, "1=1")):
        r = requests.get(f"{NHD}/{layer}/query", timeout=120, params={
            "where": where, "geometry": ",".join(map(str, bounds_wgs84)), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "gnis_name,ftype",
            "f": "geojson"})
        r.raise_for_status()
        feats += r.json().get("features", [])
    fc = {"type": "FeatureCollection", "features": feats}
    if cache is not None:
        cache.write_text(json.dumps(fc))
    return fc


def channel_from_nhd(fc, grid, widen_px=3):
    """Rasterise NHD river lines/areas onto the grid (all touched) and widen by widen_px."""
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom

    crs, tf, shape = grid
    geoms = [(transform_geom("EPSG:4326", crs, f["geometry"]), 1) for f in fc["features"] if f.get("geometry")]
    m = rasterize(geoms, out_shape=shape, transform=tf, fill=0, dtype="uint8", all_touched=True) == 1
    return ndimage.binary_dilation(m, iterations=widen_px) if widen_px else m
