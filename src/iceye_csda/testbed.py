"""Data calendar for a flood-mapping testbed (e.g. Bowling Green / Warren County).

Answers: which floods happened, and which satellites imaged them?

  - acquisitions: commercial SAR in NASA CSDA (STAC) and open NASA products in
    CMR (Sentinel-1 RTC, NISAR GCOV, OPERA water maps), with the fraction of
    the area of interest each date covers
  - floods: USGS daily gage height vs NWS flood categories, plus Groundsource
    news-reported flood events (Google Research, CC BY 4.0)
  - matching: for each flood, the acquisitions within a few days of it

Everything here is metadata; no imagery is downloaded.
"""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
TIGER = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/"
         "MapServer/1/query")
NWIS = "https://waterservices.usgs.gov/nwis"


# ---------------------------------------------------------------- boundary --

def county_boundary(geoid, cache=None):
    """County polygon (WGS84 shapely geometry) from Census TIGERweb, cached as GeoJSON."""
    import json

    from shapely.geometry import shape

    if cache is not None and cache.exists():
        return shape(json.loads(cache.read_text()))
    r = requests.get(TIGER, timeout=120, params={
        "where": f"GEOID='{geoid}'", "outFields": "NAME,GEOID", "outSR": 4326, "f": "geojson"})
    r.raise_for_status()
    geom = r.json()["features"][0]["geometry"]
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(geom))
    return shape(geom)


def coverage(geom, aoi):
    """Fraction of the area of interest covered by geom (planar, fine at county scale)."""
    if geom is None or geom.is_empty:
        return 0.0
    return float(geom.intersection(aoi).area / aoi.area)


# ------------------------------------------------------------ acquisitions --

def cmr_geometry(entry):
    """Footprint of a CMR JSON granule entry (polygons or boxes), or None."""
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    parts = []
    for poly in entry.get("polygons", []) or []:
        v = [float(x) for x in poly[0].split()]
        parts.append(Polygon(list(zip(v[1::2], v[0::2]))))     # CMR order is lat lon
    for b in entry.get("boxes", []) or []:
        s, w, n, e = (float(x) for x in b.split())
        parts.append(box(w, s, e, n))
    parts = [p.buffer(0) for p in parts if not p.is_empty]
    return unary_union(parts) if parts else None


def cmr_granules(short_name, bbox, start, session=None):
    """All CMR granules of a collection intersecting bbox since start (paged)."""
    s = session or requests.Session()
    params = {"short_name": short_name, "bounding_box": ",".join(map(str, bbox)),
              "temporal": f"{start}T00:00:00Z,", "page_size": 2000, "sort_key": "start_date"}
    headers, out = {}, []
    while True:
        r = s.get(CMR, params=params, headers=headers, timeout=180)
        r.raise_for_status()
        entries = r.json()["feed"]["entry"]
        out += entries
        after = r.headers.get("CMR-Search-After")
        if not entries or not after or len(entries) < params["page_size"]:
            return out
        headers = {"CMR-Search-After": after}


def cmr_acquisitions(short_name, label, bbox, aoi, start):
    rows = []
    for e in cmr_granules(short_name, bbox, start):
        rows.append({"source": short_name, "sensor": label, "id": e.get("title", ""),
                     "datetime": e["time_start"], "geometry": cmr_geometry(e),
                     "cloud_cover": e.get("cloud_cover")})
    return rows


def csda_acquisitions(collection, label, bbox, aoi, start):
    from shapely.geometry import shape

    from .stac import search

    rows = []
    for it in search(collection, bbox, [f"{start}T00:00:00Z", ".."]):
        rows.append({"source": f"csda:{collection}", "sensor": label, "id": it["id"],
                     "datetime": it["properties"].get("datetime"),
                     "geometry": shape(it["geometry"]) if it.get("geometry") else None,
                     "cloud_cover": None})
    return rows


def by_date(rows, aoi):
    """One row per sensor and UTC date: number of granules and county coverage."""
    from shapely.ops import unary_union

    if not rows:
        return pd.DataFrame(columns=["sensor", "source", "date", "granules", "coverage"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["datetime"], utc=True).dt.date
    out = []
    for (sensor, source, d), g in df.groupby(["sensor", "source", "date"]):
        geoms = [x for x in g["geometry"] if x is not None]
        cov = coverage(unary_union(geoms), aoi) if geoms else np.nan
        cc = pd.to_numeric(g["cloud_cover"], errors="coerce")
        out.append({"sensor": sensor, "source": source, "date": d, "granules": len(g),
                    "coverage": cov, "cloud_cover": cc.mean() if cc.notna().any() else np.nan})
    return pd.DataFrame(out).sort_values(["date", "sensor"]).reset_index(drop=True)


# ------------------------------------------------------------------ gauges --

def _nwis_series(service, site, param, stat, start, end, s):
    params = {"format": "json", "sites": site, "parameterCd": param, "startDT": start,
              "endDT": end, "siteStatus": "all"}
    if stat:
        params["statCd"] = stat
    r = s.get(f"{NWIS}/{service}/", timeout=300, params=params)
    if r.status_code == 404:
        return pd.Series(dtype=float)
    r.raise_for_status()
    vals = {}
    for ts in r.json()["value"]["timeSeries"]:
        nodata = ts["variable"].get("noDataValue")
        for blk in ts["values"]:
            for v in blk["value"]:
                try:
                    x = float(v["value"])
                except (TypeError, ValueError):
                    continue
                if x != nodata:
                    vals[v["dateTime"]] = x
    return pd.Series(vals, dtype=float)


def gauge_daily(site, start, end=None, session=None):
    """Daily max gage height (ft, from 15-min data) and daily mean flow (cfs) from USGS.

    USGS publishes daily values for discharge but often not for gage height,
    so stage is fetched as instantaneous values one year at a time.
    """
    s = session or requests.Session()
    end = end or date.today().isoformat()
    flow = _nwis_series("dv", site, "00060", "00003", start, end, s)
    flow.index = pd.to_datetime(flow.index).date
    stage_parts = []
    y0, y1 = int(start[:4]), int(end[:4])
    for y in range(y0, y1 + 1):
        a = max(start, f"{y}-01-01")
        b = min(end, f"{y}-12-31")
        iv = _nwis_series("iv", site, "00065", None, a, b, s)
        if len(iv):
            t = pd.to_datetime(iv.index, utc=True).tz_convert("America/Chicago")
            stage_parts.append(pd.Series(iv.values, index=t))
    df = pd.DataFrame({"flow_mean_cfs": flow})
    if stage_parts:
        st = pd.concat(stage_parts)
        daily = st.groupby(st.index.date).max()
        df = df.join(pd.DataFrame({"stage_max_ft": daily}), how="outer")
    df.index.name = "date"
    return df.sort_index()


def flood_episodes(stage, threshold, min_gap_days=1):
    """Runs of days with stage >= threshold. Returns DataFrame start, end, peak_date, peak.

    stage: Series indexed by date. Runs separated by fewer than min_gap_days
    dry days are merged.
    """
    s = stage.dropna()
    above = s[s >= threshold]
    if above.empty:
        return pd.DataFrame(columns=["start", "end", "peak_date", "peak"])
    days = pd.to_datetime(pd.Series(above.index))
    breaks = days.diff().dt.days.fillna(1) > min_gap_days
    groups = breaks.cumsum().values
    out = []
    for g in np.unique(groups):
        idx = above.index[groups == g]
        seg = above.loc[idx]
        out.append({"start": idx[0], "end": idx[-1], "peak_date": seg.idxmax(),
                    "peak": float(seg.max())})
    return pd.DataFrame(out)


# ------------------------------------------------------------- Groundsource --

def groundsource_events(parquet_path, aoi, start=None):
    """Groundsource flood reports whose footprint intersects the area of interest.

    Streams the GeoParquet by row group and tests WKB footprints against aoi,
    so the 2.6 M-record file never has to fit in memory at once.
    """
    import pyarrow.parquet as pq
    import shapely

    pf = pq.ParquetFile(parquet_path)
    w, s, e, n = aoi.bounds
    hits = []
    for i in range(pf.num_row_groups):
        t = pf.read_row_group(i, columns=["uuid", "area_km2", "geometry", "start_date",
                                          "end_date"]).to_pandas()
        if start:
            t = t[t["end_date"] >= start]
        if t.empty:
            continue
        geoms = shapely.from_wkb(t["geometry"].values)
        b = shapely.bounds(geoms)
        near = (b[:, 0] <= e) & (b[:, 2] >= w) & (b[:, 1] <= n) & (b[:, 3] >= s)
        if not near.any():
            continue
        g = geoms[near]
        inter = shapely.intersects(g, aoi)
        if not inter.any():
            continue
        sub = t[near][inter].copy()
        gi = g[inter]
        sub["aoi_overlap"] = [coverage(x, aoi) for x in gi]           # fraction of county
        sub["event_in_aoi"] = [float(x.intersection(aoi).area / x.area) if x.area else 1.0
                               for x in gi]                           # fraction of the report
        sub["centroid_lon"] = shapely.get_x(shapely.centroid(gi))
        sub["centroid_lat"] = shapely.get_y(shapely.centroid(gi))
        hits.append(sub.drop(columns=["geometry"]))
    if not hits:
        return pd.DataFrame(columns=["uuid", "area_km2", "start_date", "end_date",
                                     "aoi_overlap", "event_in_aoi"])
    return pd.concat(hits).sort_values("start_date").reset_index(drop=True)


def cluster_dates(starts, ends, gap_days):
    """Merge date ranges closer than gap_days. Returns list of (start, end, count)."""
    rng = sorted(zip(pd.to_datetime(starts), pd.to_datetime(ends)))
    out = []
    for s, e in rng:
        if out and (s - out[-1][1]).days <= gap_days:
            out[-1] = [out[-1][0], max(out[-1][1], e), out[-1][2] + 1]
        else:
            out.append([s, e, 1])
    return [(a.date(), b.date(), c) for a, b, c in out]


# ----------------------------------------------------------------- matching --

def flood_events(episodes_by_gauge, gs_clusters, gauges):
    """Combine gauge episodes and Groundsource clusters into one event table."""
    ev = []
    for site, ep in episodes_by_gauge.items():
        for r in ep.itertuples():
            ev.append({"start": r.start, "end": r.end, "peak_date": r.peak_date,
                       "evidence": f"{gauges[site]['nws']} {r.peak:.1f} ft"})
    for s, e, n in gs_clusters:
        ev.append({"start": s, "end": e, "peak_date": None, "evidence": f"Groundsource x{n}"})
    if not ev:
        return pd.DataFrame(columns=["start", "end", "peak_date", "evidence"])
    ev = sorted(ev, key=lambda x: x["start"])
    merged = []
    for x in ev:                     # overlapping or touching evidence = same event
        if merged and x["start"] <= merged[-1]["end"] + timedelta(days=1):
            m = merged[-1]
            m["end"] = max(m["end"], x["end"])
            m["peak_date"] = m["peak_date"] or x["peak_date"]
            m["evidence"] += "; " + x["evidence"]
        else:
            merged.append(dict(x))
    return pd.DataFrame(merged)


def usable(acq, min_coverage, max_cloud=None):
    """Acquisitions covering >= min_coverage, dropping optical dates known to be cloudier
    than max_cloud % (radar has no cloud_cover, so it is never dropped)."""
    ok = acq["coverage"].fillna(0) >= min_coverage
    if max_cloud is not None and "cloud_cover" in acq:
        ok &= ~(acq["cloud_cover"] > max_cloud)
    return acq[ok]


def observations_for(events, acq, window_days, min_coverage, max_cloud=None):
    """For each event, usable acquisitions within [start - w, end + w]."""
    acq = usable(acq, min_coverage, max_cloud)
    rows = []
    for ev in events.itertuples():
        lo = ev.start - timedelta(days=window_days)
        hi = ev.end + timedelta(days=window_days)
        hit = acq[(acq["date"] >= lo) & (acq["date"] <= hi)]
        sensors = {}
        for a in hit.itertuples():
            tag = a.date.strftime("%m-%d")
            if ev.peak_date is not None and abs((a.date - ev.peak_date).days) <= 1:
                tag += "*"            # within a day of the gauge peak
            sensors.setdefault(a.sensor, []).append(tag)
        rows.append({"start": ev.start, "end": ev.end, "peak_date": ev.peak_date,
                     "evidence": ev.evidence, "n_sensors": len(sensors),
                     **{s: " ".join(v) for s, v in sensors.items()}})
    return pd.DataFrame(rows)


def today():
    return datetime.utcnow().date()


def gauge_iv(site, start, end=None, cache=None, session=None):
    """Full 15-minute gage height (ft, UTC index) from USGS, fetched by year and cached as CSV."""
    if cache is not None and cache.exists():
        s = pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0]
        s.index = pd.to_datetime(s.index, utc=True)
        return s
    sess = session or requests.Session()
    end = end or date.today().isoformat()
    parts = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        iv = _nwis_series("iv", site, "00065", None, max(start, f"{y}-01-01"), min(end, f"{y}-12-31"), sess)
        if len(iv):
            parts.append(pd.Series(iv.values, index=pd.to_datetime(iv.index, utc=True)))
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated()]
    s.name = "stage_ft"
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        s.to_csv(cache)
    return s


def stage_at(series, when, window_min=60):
    """Gage height nearest to `when` within +/- window_min, else NaN."""
    when = pd.Timestamp(when)
    when = when.tz_localize("UTC") if when.tzinfo is None else when.tz_convert("UTC")
    i = series.index.get_indexer([when], method="nearest")[0]
    if i < 0 or abs(series.index[i] - when) > pd.Timedelta(minutes=window_min):
        return np.nan
    return float(series.iloc[i])
