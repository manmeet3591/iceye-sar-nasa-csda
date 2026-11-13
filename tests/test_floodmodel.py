"""Tests for the gauge-driven lidar flood model (synthetic terrain, no network)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from iceye_csda import floodmodel as fm  # noqa: E402


def _valley():
    # River along columns 48-51, water surface dropping 0.01 m per row downstream;
    # banks rise 0.1 m per column away from the river; an isolated hollow at rows 5-9, col 80.
    rows, cols = 100, 100
    x = np.arange(cols)
    surface_row = 100 - 0.01 * np.arange(rows)[:, None]
    dem = surface_row + np.abs(x - 49.5)[None, :] * 0.1
    dem[:, 48:52] = surface_row                     # hydro-flattened water surface
    dem[5:10, 78:83] = surface_row[5:10] - 1.0      # sinkhole-like hollow, not connected
    channel = np.zeros((rows, cols), bool)
    channel[:, 48:52] = True
    return dem.astype("float32"), channel


def test_flood_at_follows_the_sloping_river():
    dem, ch = _valley()
    surf = fm.river_surface(dem, ch, window_px=3)
    fa = fm.flood_at(dem, surf)
    # 10 columns from the river = 1.0 m above the local water surface, upstream and downstream
    assert abs(fa[0, 60] - 1.05) < .06 and abs(fa[90, 60] - 1.05) < .06


def test_flood_map_connected_and_depth():
    dem, ch = _valley()
    fa = fm.flood_at(dem, fm.river_surface(dem, ch, window_px=3))
    wet = fm.flood_map(fa, 0.5, ch)
    assert wet[50, 47] and wet[50, 53] and not wet[50, 55] and not wet[50, 60]
    assert not wet[7, 80]                            # hollow below the level but not connected
    d = fm.depth(fa, 0.5, wet)
    assert abs(d[50, 47] - (0.5 - fa[50, 47])) < 1e-6 and np.isnan(d[50, 60])


def test_area_curve_increases_and_aggregation():
    dem, ch = _valley()
    fa = fm.flood_at(dem, fm.river_surface(dem, ch, window_px=3))
    a = fm.area_curve(fa, ch, [0.0, 0.5, 1.0], 1.0)
    assert a[0] <= a[1] < a[2]
    frac = fm.aggregate_fraction(np.eye(10, dtype=bool), 5)
    assert frac.shape == (2, 2) and np.allclose(frac, [[.2, 0], [0, .2]])


def test_connected_level_equals_flood_map_for_every_rise():
    dem, ch = _valley()
    fa = fm.flood_at(dem, fm.river_surface(dem, ch, window_px=3))
    lvl = fm.connected_level(fa, ch)
    for dh in (0.2, 0.5, 1.0, 2.0):
        slow = fm.flood_map(fa, dh, ch) & ~ch
        fast = (lvl < dh) & ~ch
        assert np.array_equal(slow, fast), dh
    assert lvl[7, 80] > fa[7, 80]             # the hollow floods only once its rim is overtopped
