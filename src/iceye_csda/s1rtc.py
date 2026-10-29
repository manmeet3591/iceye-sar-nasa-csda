"""Sentinel-1 OPERA RTC and DSWx-S1 on a common county grid, plus gauge-based thresholding.

Inputs are open NASA products (Earthdata login token, EARTHDATA_TOKEN):
  OPERA_L2_RTC-S1_V1  radiometrically terrain-corrected gamma0 bursts, 30 m, VV + VH
  OPERA_L3_DSWX-S1_V1 OPERA water map (MGRS tiles, 30 m). WTR classes:
      0 not water, 1 open water, 3 inundated vegetation,
      250 HAND masked, 251 layover/shadow, 255 no data   (product spec Rev A)

Gauge-based thresholding (calibrate_threshold): near a USGS gauge the river's
water surface is nearly flat, so the gauge's water-surface elevation (WSE) and
the DEM give an *expected* wet area: ground below the WSE and connected to the
channel. The SAR threshold is chosen to match that area best (F1) over many
dates and water levels. A second gauge that was not used for calibration
checks the result independently.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy import ndimage

from .testbed import cmr_granules

WTR_WATER = (1, 3)              # open water, inundated vegetation
WTR_INVALID = (250, 251, 255)   # HAND masked, layover/shadow, fill


# ------------------------------------------------------------------ granules --

def day_granules(short_name, bbox, day):
    """CMR granules of a collection over bbox on one UTC day."""
    d0 = datetime.fromisoformat(str(day))
    t = f"{d0:%Y-%m-%d}T00:00:00Z,{d0 + timedelta(days=1):%Y-%m-%d}T00:00:00Z"
    import requests

    from .testbed import CMR
    r = requests.get(CMR, timeout=180, params={
        "short_name": short_name, "bounding_box": ",".join(map(str, bbox)),
        "temporal": t, "page_size": 2000})
    r.raise_for_status()
    return r.json()["feed"]["entry"]


def https_links(entry, suffixes):
    out = {}
    for link in entry.get("links", []):
        h = link.get("href", "")
        if h.startswith("https://"):
            for s in suffixes:
                if h.endswith(s):
                    out[s] = h
    return out


def track_of(title):
    m = re.search(r"_T(\d{3})-", title)
    return int(m.group(1)) if m else None


def newest_per_tile(entries):
    """DSWx-S1 tiles can be reprocessed; keep the newest version of each MGRS tile."""
    best = {}
    for e in entries:
        parts = e["title"].split("_")      # OPERA_L3_DSWx-S1_T16SEG_<acq>_<processed>_...
        tile, processed = parts[3], parts[5]
        if tile not in best or processed > best[tile][0]:
            best[tile] = (processed, e)
    return [v[1] for v in best.values()]


def download(url, dest, session):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 22):
                f.write(chunk)
    tmp.rename(dest)
    return dest


# ---------------------------------------------------------------------- grid --

def county_grid(aoi, res=30.0, crs="EPSG:32616"):
    """(crs, transform, shape) of a grid snapped to res covering the AOI."""
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    w, s, e, n = transform_bounds("EPSG:4326", crs, *aoi.bounds)
    w, s = np.floor(w / res) * res, np.floor(s / res) * res
    e, n = np.ceil(e / res) * res, np.ceil(n / res) * res
    shape = (int(round((n - s) / res)), int(round((e - w) / res)))
    return crs, from_origin(w, n, res, res), shape


def aoi_mask(aoi, grid):
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom

    crs, tf, shape = grid
    g = transform_geom("EPSG:4326", crs, aoi.__geo_interface__)
    return rasterize([(g, 1)], out_shape=shape, transform=tf, fill=0, dtype="uint8") == 1


def to_grid(path, grid, resampling="bilinear", src_nodata=None):
    """Reproject one raster onto the grid; returns float32 with NaN outside."""
    import rasterio
    from rasterio.warp import Resampling, reproject

    crs, tf, shape = grid
    out = np.full(shape, np.nan, "float32")
    with rasterio.open(path) as src:
        nod = src.nodata if src_nodata is None else src_nodata
        reproject(rasterio.band(src, 1), out, src_nodata=nod, dst_transform=tf, dst_crs=crs,
                  dst_nodata=np.nan, resampling=Resampling[resampling])
    return out


def mosaic_mean(paths, grid, resampling="bilinear"):
    """Average of overlapping rasters on the grid (NaN where none)."""
    total = np.zeros(grid[2], "float64")
    count = np.zeros(grid[2], "int16")
    for p in paths:
        a = to_grid(p, grid, resampling)
        ok = np.isfinite(a)
        total[ok] += a[ok]
        count[ok] += 1
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan).astype("float32")


def mosaic_first(paths, grid, nodata_values=(255,)):
    """Categorical mosaic (nearest); earlier paths win. NaN where no valid class."""
    out = np.full(grid[2], np.nan, "float32")
    for p in paths:
        a = to_grid(p, grid, "nearest", src_nodata=255)
        for v in nodata_values:
            a[a == v] = np.nan
        fill = np.isnan(out) & np.isfinite(a)
        out[fill] = a[fill]
    return out


def write_grid(path, arr, grid, nodata=np.nan, dtype="float32", tags=None):
    import rasterio

    crs, tf, shape = grid
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=shape[0], width=shape[1], count=1,
                       dtype=dtype, crs=crs, transform=tf, nodata=nodata,
                       compress="deflate") as dst:
        dst.write(arr.astype(dtype), 1)
        if tags:
            dst.update_tags(**tags)


def read_grid(path):
    import rasterio

    with rasterio.open(path) as s:
        return s.read(1)


def db(linear):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(linear > 0, 10 * np.log10(linear), np.nan).astype("float32")


# ----------------------------------------------------- gauge-based threshold --

def gauge_pixel(lon, lat, grid):
    from rasterio.warp import transform

    crs, tf, shape = grid
    (x,), (y,) = transform("EPSG:4326", crs, [lon], [lat])
    col, row = ~tf * (x, y)
    return int(row), int(col)


def reach_mask(row, col, grid, radius_m, hand=None, hand_max=None):
    _, tf, shape = grid
    r = radius_m / abs(tf.a)
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    m = (yy - row) ** 2 + (xx - col) ** 2 <= r ** 2
    if hand is not None and hand_max is not None:
        m &= ~(np.isfinite(hand) & (hand > hand_max))
    return m


def expected_wet(dem, wse, reach, channel):
    """Ground at or below the gauge water surface, inside the reach, connected to the channel."""
    low = reach & np.isfinite(dem) & (dem <= wse)
    seeds = low & channel
    if not seeds.any():
        return np.zeros(dem.shape, bool)
    lab, n = ndimage.label(low | (channel & reach))
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[channel & reach])] = True
    keep[0] = False
    return keep[lab] & low


def confusion(pred, truth, valid):
    p, t = pred & valid, truth & valid
    tp = int((p & t).sum())
    fp = int((p & ~t).sum())
    fn = int((~p & t).sum())
    return tp, fp, fn


def scores(tp, fp, fn):
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else np.nan
    csi = tp / (tp + fp + fn) if tp + fp + fn else np.nan
    return f1, csi


def calibrate_threshold(samples, thresholds):
    """Pick the dB threshold that best reproduces the gauge-expected wet area.

    samples: list of dicts with "db" (array), "truth" (bool array), "valid" (bool array).
    Confusion counts are pooled over all samples, so high-water dates (more pixels)
    weigh more than low-water ones. Returns (best_threshold, table of
    (threshold, f1, csi, tp, fp, fn)).
    """
    rows = []
    for t in thresholds:
        tp = fp = fn = 0
        for s in samples:
            a, b, c = confusion(np.nan_to_num(s["db"], nan=99.0) < t, s["truth"], s["valid"])
            tp, fp, fn = tp + a, fp + b, fn + c
        f1, csi = scores(tp, fp, fn)
        rows.append((float(t), f1, csi, tp, fp, fn))
    best = max(rows, key=lambda r: -1 if np.isnan(r[1]) else r[1])
    return best[0], rows


def acquisition_time(entries):
    """Mean acquisition time (UTC) of a list of CMR entries."""
    ts = [datetime.fromisoformat(e["time_start"].replace("Z", "+00:00")) for e in entries]
    t0 = min(ts)
    return t0 + sum((t - t0 for t in ts), timedelta()) / len(ts) if ts else None


def utc(dt):
    return dt.astimezone(timezone.utc)
