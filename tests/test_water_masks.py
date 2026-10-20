"""Tests for split-based thresholding, masks, FLEXTH and notices (synthetic data)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iceye_csda import (CSDA_ACK, OPEN_DATA_NOTICE, SOURCE_CSDA,  # noqa: E402
                        SOURCE_OPEN_DATA, notices, scene_source)
from iceye_csda.ancillary import hand_tile_names, jrc_tile_names, slope_deg  # noqa: E402
from iceye_csda.flood import (flexth_depth, flood_depth, grow_water, map_water,  # noqa: E402
                              otsu_threshold, tile_threshold)


def _scene(rng, water_frac_cols=0.85, shape=(1024, 1024)):
    """Mostly water on the left, land on the right, like a big lake + shore."""
    db = rng.normal(-8, 1.5, shape)
    edge = int(shape[1] * water_frac_cols)
    db[:, :edge] = rng.normal(-22, 1.5, (shape[0], edge))
    return db, edge


def test_tile_threshold_ignores_class_imbalance():
    rng = np.random.default_rng(2)
    db, _ = _scene(rng)
    db[:, :870] += np.linspace(0, 6, 870)        # water gets brighter towards shore
    t, info = tile_threshold(db, tile=128, min_tiles=3)
    assert info["method"] == "tiles" and info["tiles_selected"] >= 3
    assert -17 < t < -11


def test_tile_threshold_falls_back_without_bimodal_tiles():
    rng = np.random.default_rng(3)
    db = rng.normal(-8, 1.5, (512, 512))         # land only
    t, info = tile_threshold(db, tile=128)
    assert info["method"].startswith("otsu")
    assert np.isclose(t, otsu_threshold(db))


def test_grow_water_only_keeps_connected_pixels():
    db = np.full((50, 50), -5.0)
    db[10:20, 10:20] = -20                       # confident water
    db[10:20, 20:25] = -14                       # slightly brighter, touching
    db[40:45, 40:45] = -14                       # slightly brighter, isolated
    seeds = db < -15
    g = grow_water(db, seeds, -13)
    assert g[15, 22] and not g[42, 42]


def test_map_water_applies_hand_and_slope_masks():
    rng = np.random.default_rng(4)
    db = rng.normal(-8, 1.0, (300, 300))
    db[50:150, 50:150] = rng.normal(-22, 1.0, (100, 100))   # river/lake
    db[200:260, 200:260] = rng.normal(-22, 1.0, (60, 60))   # "shadow" on a hill
    hand = np.zeros(db.shape)
    hand[200:260, 200:260] = 40
    slope = np.zeros(db.shape)
    slope[180:280, 180:280] = 20
    mask, info = map_water(db, method="otsu", hand=hand, slope=slope)
    assert mask[60:140, 60:140].mean() > 0.98
    assert not mask[200:260, 200:260].any()
    assert info["excluded_pixels"] > 3000


def _valley(water_level=2.0):
    x = np.arange(120)
    dem = np.tile(np.abs(x - 60) * 0.1, (80, 1)).astype("float32")
    return dem, dem < water_level


def test_flexth_matches_flat_water_surface():
    dem, mask = _valley()
    depth, ext, info = flexth_depth(mask, dem, extend_px=0)
    assert 1.7 < depth[40, 60] <= 2.0
    assert np.all(np.isnan(depth[~mask])) and not ext.any()


def test_flexth_ignores_outlier_edge_and_extends_missed_flood():
    dem, mask = _valley()
    truth = mask.copy()
    mask[30:40, 48:55] = False                   # SAR missed a patch inside the flood
    dem_bad = dem.copy()
    dem_bad[5, 41] = 9.0                         # a tree/building on the flood edge
    depth, ext, info = flexth_depth(mask, dem_bad, extend_px=20)
    assert ext[30:40, 48:55].all() and truth[35, 50]   # missed flood recovered
    assert abs(depth[35, 51] - (2.0 - dem[35, 51])) < 0.15   # true water level, not the hole rim
    assert info["hole_pixels"] == 70
    assert not ext[40, 10]                        # dry valley side stays dry
    assert info["edge_kept"] < info["edge_pixels"]
    assert np.nanmax(depth) < 2.5                 # outlier did not raise the water level
    fw = flood_depth(mask, dem_bad, smoothing_px=1)
    assert np.nanmax(fw) > np.nanmax(depth)       # FwDET picks the outlier up


def test_notices_follow_data_source(tmp_path):
    scene = tmp_path / "S1" / "S1_GRD.tif"
    scene.parent.mkdir()
    assert scene_source(scene) == SOURCE_CSDA
    assert CSDA_ACK in notices(SOURCE_CSDA)
    (scene.parent / "DATA_SOURCE").write_text("iceye-open-data\n")
    assert scene_source(scene) == SOURCE_OPEN_DATA
    assert notices(SOURCE_OPEN_DATA) == [OPEN_DATA_NOTICE]


def test_ancillary_tile_names():
    lake_borgne = (-89.67, 29.69, -89.19, 30.44)
    assert jrc_tile_names(lake_borgne) == ["90W_30N", "90W_40N"]
    assert hand_tile_names(lake_borgne) == [("N29", "W090"), ("N30", "W090")]
    kentucky = (-89.58, 36.49, -81.96, 39.15)
    assert jrc_tile_names(kentucky) == ["90W_40N"]


def test_slope_deg():
    dem = np.tile(np.arange(10) * 10.0, (10, 1))  # 10 m rise per 10 m pixel = 45 deg
    assert np.allclose(slope_deg(dem, 10.0), 45.0)


def test_flexth_extension_only_adds_shallow_water():
    # A small water body whose edge sits at 8 m right next to ground at 2-4 m
    # (DEM and SAR disagree) must not "flood" the low ground metres deep.
    dem = np.full((60, 60), 9.0, "float32")
    dem[:, 30:] = np.linspace(4, 2, 30)
    mask = np.zeros(dem.shape, bool)
    mask[25:35, 20:30] = True
    dem[25:35, 20:30] = 8.0
    capped, ext, _ = flexth_depth(mask, dem, extend_px=20, extend_max_depth=1.5)
    uncapped, ext_all, _ = flexth_depth(mask, dem, extend_px=20, extend_max_depth=100)
    assert ext_all[:, 30:].sum() > 50 and np.nanmax(uncapped) > 3   # the failure mode
    assert not ext[:, 30:].any()                                       # prevented by the cap
    assert np.nanmax(capped) < 1.6
