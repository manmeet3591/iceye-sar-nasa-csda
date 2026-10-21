"""Tests for gauge validation helpers (no network)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iceye_csda.gauges import FT, _rdb, estimates_near, gauge_wse_navd88, score  # noqa: E402

T = datetime(2022, 10, 7, 3, 14, tzinfo=timezone.utc)
SITE = {"site_no": "1", "dec_long_va": "-81.3", "dec_lat_va": "28.8"}


def test_navd88_elevation_used_directly():
    wse, param, note = gauge_wse_navd88(SITE, {"62620": (2.0, T), "00065": (9.0, T)})
    assert param == "62620" and np.isclose(wse, 2.0 * FT) and note == "NAVD88"


def test_gage_height_plus_navd88_datum():
    site = dict(SITE, alt_va="1.5", alt_datum_cd="NAVD88")
    wse, param, _ = gauge_wse_navd88(site, {"00065": (8.8, T)})
    assert param == "00065" and np.isclose(wse, 10.3 * FT)


def test_ngvd29_is_converted():
    site = dict(SITE, alt_va="0.0", alt_datum_cd="NGVD29")
    calls = []

    def fake(lon, lat, z_ft):
        calls.append(z_ft)
        return z_ft * FT - 0.311

    wse, _, note = gauge_wse_navd88(site, {"00065": (8.8, T)}, convert=fake)
    assert calls == [8.8] and np.isclose(wse, 8.8 * FT - 0.311) and "VDatum" in note


def test_unknown_datum_is_not_scored():
    wse, _, note = gauge_wse_navd88(dict(SITE, alt_va=""), {"00065": (8.8, T)})
    assert wse is None and "unknown" in note
    wse, _, note = gauge_wse_navd88(SITE, {})
    assert wse is None and "no water-level" in note


def test_estimates_near_gauge():
    # River (class 2) along rows 40-59, flood (1) rows 60-69, dry above/below.
    classes = np.zeros((100, 100), "uint8")
    classes[40:60] = 2
    classes[60:70] = 1
    dem = np.full((100, 100), 3.0, "float32")
    dem[40:70] = 1.0
    dem[39] = 2.0
    dem[70] = 2.2
    fw = np.full(classes.shape, np.nan, "float32")
    fw[60:70] = 1.0                               # water surface 2.0 m
    est = estimates_near(50, 50, 30, classes, dem, {"fwdet": fw, "flexth": fw})
    assert est["edge_n"] > 0 and np.isclose(est["edge"], 1.0)   # edge water pixels are at 1 m
    assert np.isclose(est["fwdet"], 2.0) and est["water_dist_px"] == 0
    far = estimates_near(5, 5, 3, classes, dem, {"fwdet": fw})
    assert np.isnan(far["edge"]) and np.isnan(far["fwdet"]) and np.isnan(far["water_dist_px"])


def test_score_and_rdb():
    s = score([0.1, -0.3, np.nan])
    assert s["n"] == 2 and np.isclose(s["bias"], -0.1) and np.isclose(s["mae"], 0.2)
    text = "# comment\nsite_no\tstation_nm\n5s\t15s\n0123\tRiver\n"
    assert _rdb(text) == [{"site_no": "0123", "station_nm": "River"}]
