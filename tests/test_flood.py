"""Tests on synthetic arrays (no ICEYE data needed)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iceye_csda.flood import flood_depth, otsu_threshold, water_mask  # noqa: E402
from iceye_csda.sar import calibrate_sigma0, lee_filter, slc_to_amplitude, to_db  # noqa: E402


def test_otsu_separates_bimodal():
    rng = np.random.default_rng(0)
    v = np.concatenate([rng.normal(-22, 1.5, 5000), rng.normal(-8, 1.5, 5000)])
    t = otsu_threshold(v)
    assert -18 < t < -12


def test_water_mask_finds_dark_block():
    rng = np.random.default_rng(1)
    db = rng.normal(-8, 1.0, (200, 200))
    db[50:150, 60:140] = rng.normal(-22, 1.0, (100, 80))
    mask, _ = water_mask(db, min_pixels=50)
    assert mask[60:140, 70:130].mean() > 0.98
    assert mask[:40].mean() < 0.01


def test_flood_depth_on_valley():
    # V-shaped valley along x: ground = |x - 50| * 0.1 m; water surface at 2 m
    x = np.arange(100)
    dem = np.tile(np.abs(x - 50) * 0.1, (60, 1)).astype("float32")
    mask = dem < 2.0
    depth = flood_depth(mask, dem, smoothing_px=1)
    centre = depth[30, 50]
    assert 1.6 < centre <= 2.0
    assert np.all(np.isnan(depth[~mask]))
    assert np.nanmin(depth) >= 0


def test_calibration_and_filters():
    md = {"calibration_factor": 1e-6, "incidence_center": 30.0}
    dn = np.full((10, 10), 1000, dtype="uint16")
    dn[0, 0] = 0
    s0 = calibrate_sigma0(dn, md)
    assert np.isnan(s0[0, 0])
    assert np.isclose(s0[5, 5], 1e-6 * 1000**2 * 0.5, rtol=1e-5)
    assert np.isclose(to_db(s0)[5, 5], 10 * np.log10(0.5), atol=1e-4)
    f = lee_filter(s0, 3)
    assert np.isnan(f[0, 0]) and np.isfinite(f[5, 5])


def test_slc_multilook_shape():
    i = np.ones((10, 9))
    q = np.zeros((10, 9))
    amp = slc_to_amplitude(i, q, looks=(2, 3))
    assert amp.shape == (5, 3)
    assert np.allclose(amp, 1.0)
