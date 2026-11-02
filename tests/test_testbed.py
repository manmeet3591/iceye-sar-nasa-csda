"""Tests for the testbed data calendar (no network)."""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iceye_csda import testbed as tb  # noqa: E402

D = date


def test_flood_episodes_groups_consecutive_days():
    s = pd.Series([5, 27, 30, 26.5, 10, 10, 26, 8],
                  index=[D(2025, 2, i) for i in range(1, 9)])
    ep = tb.flood_episodes(s, 26)
    assert len(ep) == 2
    assert ep.iloc[0]["start"] == D(2025, 2, 2) and ep.iloc[0]["end"] == D(2025, 2, 4)
    assert ep.iloc[0]["peak_date"] == D(2025, 2, 3) and ep.iloc[0]["peak"] == 30
    assert tb.flood_episodes(pd.Series([1.0], index=[D(2025, 1, 1)]), 26).empty


def test_cluster_dates_and_event_merge():
    cl = tb.cluster_dates(["2025-04-01", "2025-04-03", "2025-06-01"],
                          ["2025-04-01", "2025-04-04", "2025-06-01"], 3)
    assert cl == [(D(2025, 4, 1), D(2025, 4, 4), 2), (D(2025, 6, 1), D(2025, 6, 1), 1)]
    ep = pd.DataFrame([{"start": D(2025, 4, 4), "end": D(2025, 4, 6),
                        "peak_date": D(2025, 4, 5), "peak": 35.8}])
    ev = tb.flood_events({"03314500": ep}, cl, {"03314500": {"nws": "BWGK2"}})
    assert len(ev) == 2                                   # April evidence merged, June separate
    first = ev.iloc[0]
    assert first["start"] == D(2025, 4, 1) and first["end"] == D(2025, 4, 6)
    assert first["peak_date"] == D(2025, 4, 5) and "BWGK2" in first["evidence"]


def test_observations_window_peak_and_clouds():
    ev = pd.DataFrame([{"start": D(2025, 4, 4), "end": D(2025, 4, 6),
                        "peak_date": D(2025, 4, 5), "evidence": "x"}])
    acq = pd.DataFrame([
        {"sensor": "S1", "date": D(2025, 4, 5), "coverage": 0.9, "cloud_cover": np.nan},
        {"sensor": "S1", "date": D(2025, 4, 9), "coverage": 0.9, "cloud_cover": np.nan},  # late
        {"sensor": "HLS", "date": D(2025, 4, 2), "coverage": 0.9, "cloud_cover": 80.0},   # cloudy
        {"sensor": "HLS", "date": D(2025, 4, 7), "coverage": 0.9, "cloud_cover": 10.0},
        {"sensor": "NISAR", "date": D(2025, 4, 5), "coverage": 0.05, "cloud_cover": np.nan},
    ])
    o = tb.observations_for(ev, acq, 2, 0.2, max_cloud=50).iloc[0]
    assert o["S1"] == "04-05*" and o["HLS"] == "04-07" and "NISAR" not in o
    assert o["n_sensors"] == 2


def test_cmr_geometry_and_coverage():
    from shapely.geometry import box

    aoi = box(-86.6, 36.8, -86.2, 37.2)
    e = {"polygons": [["36.8 -86.6 36.8 -86.4 37.2 -86.4 37.2 -86.6 36.8 -86.6"]]}
    g = tb.cmr_geometry(e)                          # CMR polygons are "lat lon" pairs
    assert np.allclose(g.bounds, (-86.6, 36.8, -86.4, 37.2))
    assert np.isclose(tb.coverage(g, aoi), 0.5)
    assert np.isclose(tb.coverage(tb.cmr_geometry({"boxes": ["36 -87 38 -86"]}), aoi), 1.0)
    assert tb.cmr_geometry({}) is None


def test_groundsource_filter(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely
    from shapely.geometry import box

    aoi = box(-86.6, 36.8, -86.2, 37.2)
    geoms = [box(-86.5, 36.9, -86.4, 37.0),        # inside
             box(-86.3, 37.1, -86.0, 37.4),        # partly inside
             box(-80.0, 30.0, -79.0, 31.0)]        # far away
    t = pa.table({"uuid": ["a", "b", "c"], "area_km2": [1.0, 2.0, 3.0],
                  "geometry": shapely.to_wkb(np.array(geoms)),
                  "start_date": ["2025-04-03", "2025-04-04", "2025-04-03"],
                  "end_date": ["2025-04-03", "2025-04-04", "2025-04-03"]})
    path = tmp_path / "gs.parquet"
    pq.write_table(t, path, row_group_size=2)
    gs = tb.groundsource_events(path, aoi, start="2016-01-01")
    assert list(gs["uuid"]) == ["a", "b"]
    assert np.isclose(gs.iloc[0]["event_in_aoi"], 1.0) and gs.iloc[1]["event_in_aoi"] < 0.5


def test_stage_at_nearest_within_window():
    idx = pd.date_range("2025-02-17 23:00", periods=5, freq="15min", tz="UTC")
    s = pd.Series([30.0, 31.0, 32.0, 33.0, 34.0], index=idx)
    assert tb.stage_at(s, "2025-02-17T23:39:51Z") == 33.0          # nearest reading 23:45
    assert np.isnan(tb.stage_at(s, "2025-02-18T03:00:00Z"))         # nothing within 60 min
