"""Tests for Sentinel-1 gridding helpers and gauge-based thresholding (no network)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iceye_csda import s1rtc  # noqa: E402


def test_titles_and_newest_tile():
    assert s1rtc.track_of("OPERA_L2_RTC-S1_T121-257968-IW1_20250217T233930Z_x") == 121
    a = {"title": "OPERA_L3_DSWx-S1_T16SEG_20250217T234000Z_20250221T055027Z_S1A_30_v1.0"}
    b = {"title": "OPERA_L3_DSWx-S1_T16SEG_20250217T234005Z_20260404T031028Z_S1A_30_v1.0"}
    c = {"title": "OPERA_L3_DSWx-S1_T16SEF_20250217T234005Z_20260404T031028Z_S1A_30_v1.0"}
    got = {e["title"] for e in s1rtc.newest_per_tile([a, b, c])}
    assert got == {b["title"], c["title"]}


def test_county_grid_snaps_to_resolution():
    from shapely.geometry import box

    crs, tf, shape = s1rtc.county_grid(box(-86.674, 36.776, -86.114, 37.191), 30.0)
    assert tf.a == 30 and tf.e == -30 and tf.c % 30 == 0 and tf.f % 30 == 0
    assert 1400 < shape[0] < 1700 and 1600 < shape[1] < 1800


def _valley_scene(wse, rng):
    """River valley: ground rises 0.1 m per pixel away from a channel at column 50."""
    x = np.arange(100)
    dem = np.tile(100 + np.abs(x - 50) * 0.1, (80, 1)).astype("float32")
    wet = dem <= wse
    db = np.where(wet, rng.normal(-21, 1.5, dem.shape), rng.normal(-9, 2.0, dem.shape))
    return dem, db.astype("float32")


def test_expected_wet_is_connected_to_channel():
    dem = np.full((40, 40), 105.0)
    dem[:, 18:22] = 100.0           # channel
    dem[5:10, 30:35] = 100.0        # isolated low pond, not connected
    channel = np.zeros(dem.shape, bool)
    channel[:, 19:21] = True
    reach = np.ones(dem.shape, bool)
    wet = s1rtc.expected_wet(dem, 101.0, reach, channel)
    assert wet[:, 18:22].all() and not wet[5:10, 30:35].any()


def test_calibration_recovers_threshold_between_classes():
    rng = np.random.default_rng(0)
    samples = []
    for wse in (100.5, 101.5, 103.0):            # three water levels
        dem, db = _valley_scene(wse, rng)
        channel = np.zeros(dem.shape, bool)
        channel[:, 50] = True
        reach = np.ones(dem.shape, bool)
        truth = s1rtc.expected_wet(dem, wse, reach, channel)
        samples.append({"db": db, "truth": truth, "valid": reach})
    best, rows = s1rtc.calibrate_threshold(samples, np.arange(-26, -6, 0.5))
    assert -17.5 <= best <= -13.0                   # between -21 and -9 dB populations
    f1 = dict((r[0], r[1]) for r in rows)
    assert f1[best] > 0.95 and f1[-25.0] < f1[best] and f1[-7.0] < f1[best]


def test_scores():
    assert s1rtc.scores(8, 1, 1) == (0.8888888888888888, 0.8)
    assert np.isnan(s1rtc.scores(0, 0, 0)[0])
