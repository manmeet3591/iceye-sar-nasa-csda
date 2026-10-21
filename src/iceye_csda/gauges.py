"""Validate SAR flood water levels against USGS gauges (public data, no login).

For each USGS gauge in the scene, the water-surface elevation (WSE) at the
satellite pass is compared with water levels estimated from the SAR result
near the gauge:

  edge    median ground elevation of flood/water edge pixels within the radius
          (the basic idea behind FwDET and FLEXTH: the shoreline's elevation is
          the water level)
  fwdet   median of depth + ground over FwDET flood pixels within the radius
  flexth  same for FLEXTH

All elevations are NAVD88 metres, the datum of USGS 3DEP. Gauge readings are
converted as follows:
  - elevation parameters already in NAVD88: used directly
  - gage height (00065) + gage datum (alt_va, alt_datum_cd)
  - NGVD29 values: converted with NOAA VDatum (https://vdatum.noaa.gov)
Gauges whose datum is unknown are reported but not scored.

Data: USGS Water Services (https://waterservices.usgs.gov). The legacy NWIS
services are being replaced by https://api.waterdata.usgs.gov; update the URLs
here if they stop answering.
"""

import csv
import io
from datetime import datetime, timedelta, timezone

import numpy as np
import requests

NWIS = "https://waterservices.usgs.gov/nwis"
VDATUM = "https://vdatum.noaa.gov/vdatumweb/api/convert"
FT = 0.3048

# USGS parameter codes for water level, in order of preference.
# value: (datum of the reading, True if it is gage height needing the gage datum)
PARAMS = {
    "62620": ("NAVD88", False),   # estuary/ocean water surface elevation, NAVD88
    "63160": ("NAVD88", False),   # stream water level elevation, NAVD88
    "62615": ("NAVD88", False),   # lake/reservoir water surface elevation, NAVD88
    "63158": ("NGVD29", False),   # stream water level elevation, NGVD29
    "62614": ("NGVD29", False),   # lake/reservoir water surface elevation, NGVD29
    "00065": (None, True),        # gage height above the gage datum
}


def _rdb(text):
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    if len(lines) < 2:
        return []
    return list(csv.DictReader(io.StringIO("\n".join([lines[0]] + lines[2:])), delimiter="\t"))


def fetch_sites(bbox, session=None):
    """USGS sites with instantaneous data in (west, south, east, north)."""
    s = session or requests
    w, so, e, n = bbox
    r = s.get(f"{NWIS}/site/", timeout=120, params={
        "format": "rdb", "bBox": f"{w:.5f},{so:.5f},{e:.5f},{n:.5f}",
        "siteOutput": "expanded", "siteStatus": "all", "hasDataTypeCd": "iv"})
    if r.status_code == 404:          # NWIS answers 404 when nothing matches
        return []
    r.raise_for_status()
    return _rdb(r.text)


def fetch_levels(site_nos, when, window_min=30, session=None):
    """Readings nearest to `when` (UTC) within +/- window_min, per site and parameter.

    Returns {site_no: {param: (value_ft, time_utc)}}.
    """
    s = session or requests
    out = {}
    t0 = (when - timedelta(minutes=window_min)).strftime("%Y-%m-%dT%H:%MZ")
    t1 = (when + timedelta(minutes=window_min)).strftime("%Y-%m-%dT%H:%MZ")
    for i in range(0, len(site_nos), 100):
        r = s.get(f"{NWIS}/iv/", timeout=120, params={
            "format": "json", "sites": ",".join(site_nos[i:i + 100]),
            "parameterCd": ",".join(PARAMS), "startDT": t0, "endDT": t1,
            "siteStatus": "all"})
        if r.status_code == 404:
            continue
        r.raise_for_status()
        for ts in r.json()["value"]["timeSeries"]:
            site = ts["sourceInfo"]["siteCode"][0]["value"]
            param = ts["variable"]["variableCode"][0]["value"]
            nodata = ts["variable"].get("noDataValue")
            best = None
            for block in ts["values"]:
                for v in block["value"]:
                    try:
                        val = float(v["value"])
                    except (TypeError, ValueError):
                        continue
                    if nodata is not None and val == nodata:
                        continue
                    t = datetime.fromisoformat(v["dateTime"]).astimezone(timezone.utc)
                    if best is None or abs(t - when) < abs(best[1] - when):
                        best = (val, t)
            if best:
                out.setdefault(site, {})[param] = best
    return out


def ngvd29_to_navd88_m(lon, lat, z_ft, session=None):
    """Convert an NGVD29 height (US survey ft) to NAVD88 metres with NOAA VDatum."""
    s = session or requests
    r = s.get(VDATUM, timeout=60, params={
        "s_x": lon, "s_y": lat, "s_z": z_ft, "s_h_frame": "NAD27", "s_v_frame": "NGVD29",
        "t_h_frame": "NAD83_2011", "t_v_frame": "NAVD88", "s_v_unit": "us_ft",
        "t_v_unit": "m", "region": "contiguous"})
    r.raise_for_status()
    d = r.json()
    if "t_z" not in d:
        raise RuntimeError(d.get("message", "VDatum conversion failed"))
    return float(d["t_z"])


def gauge_wse_navd88(site, readings, convert=ngvd29_to_navd88_m):
    """Water-surface elevation (NAVD88 m) for one gauge. Returns (wse, param, note)."""
    lon, lat = float(site["dec_long_va"]), float(site["dec_lat_va"])
    for param, (datum, is_stage) in PARAMS.items():
        if param not in readings:
            continue
        val = readings[param][0]
        if is_stage:
            alt = (site.get("alt_va") or "").strip()
            datum = (site.get("alt_datum_cd") or "").strip()
            if not alt or datum not in ("NAVD88", "NGVD29"):
                note = f"gage height only; gage datum {'unknown' if not alt else datum}"
                return None, param, note
            val = val + float(alt)
        if datum == "NAVD88":
            return val * FT, param, "NAVD88"
        try:
            return convert(lon, lat, val), param, "NGVD29 -> NAVD88 (VDatum)"
        except Exception as exc:
            return None, param, f"NGVD29 conversion failed: {exc}"
    return None, None, "no water-level reading at the pass"


def estimates_near(row, col, radius_px, classes, dem, depths):
    """Water levels estimated from the SAR result around one pixel.

    classes: water_mask.tif classes (0 dry, 1 flood, 2 permanent, 3 FLEXTH-added, 255 nodata)
    depths: {"fwdet": array, "flexth": array}
    Returns dict of medians and counts; values are NaN when nothing is within
    the radius (water_dist_px too: no water anywhere in the radius).
    """
    from scipy import ndimage

    r0, r1 = max(row - radius_px, 0), min(row + radius_px + 1, classes.shape[0])
    c0, c1 = max(col - radius_px, 0), min(col + radius_px + 1, classes.shape[1])
    cls = classes[r0:r1, c0:c1]
    z = dem[r0:r1, c0:c1]
    yy, xx = np.mgrid[r0:r1, c0:c1]
    inside = (yy - row) ** 2 + (xx - col) ** 2 <= radius_px ** 2

    water = (cls == 1) | (cls == 2)
    dry = cls == 0
    edge = water & ndimage.binary_dilation(dry, structure=np.ones((3, 3))) & inside
    edge &= np.isfinite(z)
    out = {"edge_n": int(edge.sum()),
           "edge": float(np.median(z[edge])) if edge.any() else np.nan}
    for name, d in depths.items():
        wse = d[r0:r1, c0:c1] + z
        ok = np.isfinite(wse) & inside
        out[f"{name}_n"] = int(ok.sum())
        out[name] = float(np.median(wse[ok])) if ok.any() else np.nan
    w = np.nonzero(((cls == 1) | (cls == 2) | (cls == 3)))
    if w[0].size:
        out["water_dist_px"] = float(np.min(np.hypot(w[0] + r0 - row, w[1] + c0 - col)))
    else:
        out["water_dist_px"] = np.nan
    return out


def score(errors):
    """Bias, MAE and RMSE of an array of (estimate - gauge) errors, ignoring NaN."""
    e = np.asarray(errors, float)
    e = e[np.isfinite(e)]
    if not e.size:
        return {"n": 0, "bias": np.nan, "mae": np.nan, "rmse": np.nan}
    return {"n": int(e.size), "bias": float(e.mean()), "mae": float(np.abs(e).mean()),
            "rmse": float(np.sqrt((e ** 2).mean()))}
