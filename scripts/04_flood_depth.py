"""Step 4: flood extent + flood depth from a geocoded sigma0 scene.

Water is mapped with a split-based (tile) threshold and region growing, then
cleaned with free ancillary layers fetched for the scene footprint:
  - HAND (ASF GLO-30): water more than hand_max_m above drainage is rejected
  - slope (USGS 3DEP):  dark pixels on steep slopes (radar shadow) are rejected
  - permanent water (JRC Global Surface Water): separated from flood water
Depth is estimated two ways from the flood edge and the 3DEP DEM: FwDET and
FLEXTH-style (see src/iceye_csda/flood.py).

Outputs in outputs/<scene>/ (derived products):
  water_mask.tif          0 dry, 1 flood water (SAR), 2 permanent water,
                          3 flood added by FLEXTH extension, 255 no data
  flood_depth_fwdet.tif   depth in metres, FwDET
  flood_depth_flexth.tif  depth in metres, FLEXTH-style
  summary.txt             thresholds, areas, depth statistics, notices

    python scripts/04_flood_depth.py data/processed/<scene>_sigma0_db.tif
    python scripts/04_flood_depth.py <scene> --reference <pre-flood scene>  # remove normal water
    python scripts/04_flood_depth.py <scene> --no-ancillary                # offline: DEM only
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
from iceye_csda import SOURCE_CSDA, SOURCE_OPEN_DATA, notices  # noqa: E402
from iceye_csda import ancillary, dem as demlib  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.flood import flexth_depth, flood_depth, map_water  # noqa: E402


def write_like(ref_path, out_path, arr, dtype, nodata, lines):
    import rasterio

    with rasterio.open(ref_path) as ref:
        profile = ref.profile.copy()
    profile.update(dtype=dtype, nodata=nodata, count=1, compress="deflate")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)
        dst.update_tags(NOTICE=" ".join(lines))


def cached(path, fetch, bounds, label):
    """Fetch an ancillary layer once per scene; return its path or None on failure."""
    if path.exists():
        return path
    print(f"Fetching {label} ...")
    try:
        return fetch(bounds, out_path=path)
    except Exception as exc:
        print(f"   {label} unavailable ({exc}); continuing without it")
        return None


def stats(d):
    d = d[np.isfinite(d)]
    if not d.size:
        return "n/a"
    return (f"{d.mean():.2f} / {np.median(d):.2f} / {np.percentile(d, 95):.2f} / "
            f"{d.max():.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", type=Path, help="geocoded *_sigma0_db.tif")
    ap.add_argument("--reference", type=Path, help="pre-flood scene on the same grid")
    ap.add_argument("--dem", type=Path, help="existing DEM GeoTIFF (else fetch 3DEP)")
    ap.add_argument("--no-ancillary", action="store_true",
                    help="skip HAND and permanent-water layers (DEM still needed)")
    ap.add_argument("--source", choices=[SOURCE_CSDA, SOURCE_OPEN_DATA],
                    help="override the data source recorded in the scene")
    ap.add_argument("--config", default="config/kentucky.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    fc = cfg["flood"]

    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(args.scene) as src:
        db = src.read(1)
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        px = abs(src.transform.a)
        pixel_area = abs(src.transform.a * src.transform.e)
        source = args.source or src.tags().get("DATA_SOURCE", SOURCE_CSDA)
    lines_notice = notices(source)

    # Ancillary layers, cached per scene in data/dem/.
    anc = cfg["paths"]["dem"]
    anc.mkdir(parents=True, exist_ok=True)
    stem = args.scene.stem
    dem_path = args.dem or cached(anc / f"{stem}_3dep.tif", demlib.fetch_3dep, bounds,
                                  "USGS 3DEP DEM")
    if dem_path is None:
        raise SystemExit("A DEM is required for flood depth.")
    dem = demlib.align_to(dem_path, args.scene)
    slope = ancillary.slope_deg(dem, px)
    hand = perm = None
    if not args.no_ancillary:
        hp = cached(anc / f"{stem}_hand.tif", ancillary.fetch_hand, bounds, "GLO-30 HAND")
        hand = demlib.align_to(hp, args.scene) if hp else None
        wp = cached(anc / f"{stem}_jrc_occurrence.tif", ancillary.fetch_permanent_water,
                    bounds, "JRC permanent water")
        if wp:
            occ = demlib.align_to(wp, args.scene, resampling="nearest")
            perm = np.isfinite(occ) & (occ >= fc["permanent_water_occurrence"])

    valid = np.isfinite(db) & np.isfinite(dem)
    water, info = map_water(
        db, method=fc["threshold_method"], threshold_db=fc["water_threshold_db"],
        tile=fc["tile_size_px"], grow_db=fc["region_grow_db"],
        min_pixels=fc["min_water_pixels"], hand=hand, hand_max=fc["hand_max_m"],
        slope=slope, slope_max=fc["slope_max_deg"])
    water &= valid

    if perm is None:
        perm = np.zeros(water.shape, bool)
    if args.reference:
        ref_db = demlib.align_to(args.reference, args.scene)
        ref_water, _ = map_water(ref_db, method="fixed", threshold_db=info["threshold_db"],
                                 min_pixels=fc["min_water_pixels"])
        perm |= ref_water
    perm &= valid
    flood = water & ~perm
    all_water = water | perm      # the flood edge is where any water meets dry land

    depth_fw = flood_depth(all_water, dem, fc["depth_smoothing_px"], valid=valid)
    depth_fw[~flood] = np.nan
    fx = fc["flexth"]
    depth_fx, extended, fx_info = flexth_depth(
        all_water, dem, valid=valid, slope=slope, edge_slope_max=fx["edge_slope_max_deg"],
        edge_max_mad=fx["edge_outlier_mad"], neighbours=fx["idw_neighbours"],
        extend_px=int(round(fx["extend_dist_m"] / px)), hand=hand, hand_max=fc["hand_max_m"],
        hole_px=int(round(fx["hole_max_m2"] / pixel_area)), report=flood,
        extend_max_depth=fx["extend_max_depth_m"])
    depth_fx[~(flood | extended)] = np.nan

    classes = np.zeros(water.shape, "uint8")
    classes[flood] = 1
    classes[perm] = 2
    classes[extended] = 3
    classes[~valid] = 255

    out = cfg["paths"]["outputs"] / stem.replace("_sigma0_db", "")
    out.mkdir(parents=True, exist_ok=True)
    write_like(args.scene, out / "water_mask.tif", classes, "uint8", 255, lines_notice)
    write_like(args.scene, out / "flood_depth_fwdet.tif", depth_fw, "float32", np.nan,
               lines_notice)
    write_like(args.scene, out / "flood_depth_flexth.tif", depth_fx, "float32", np.nan,
               lines_notice)

    km2 = lambda m: f"{m.sum() * pixel_area / 1e6:.3f}"  # noqa: E731
    both = np.isfinite(depth_fw) & np.isfinite(depth_fx)
    lines = [
        f"scene: {args.scene.name}",
        f"data source: {source}",
        f"threshold method: {info['method']} "
        f"({info.get('tiles_selected', '-')} of {info.get('tiles', '-')} tiles)",
        f"water threshold (dB): {info['threshold_db']:.2f}"
        + (f"  (tile range {info['tile_threshold_range'][0]:.2f} to "
           f"{info['tile_threshold_range'][1]:.2f})" if "tile_threshold_range" in info else ""),
        f"pixels added by region growing: {info['grown_pixels']}",
        f"water pixels removed by HAND/slope masks: {info['excluded_pixels']}",
        f"HAND layer: {'yes' if hand is not None else 'no'}; "
        f"permanent water layer: {'yes' if not args.no_ancillary and perm.any() else 'no'}",
        f"SAR water (km2): {km2(water)}",
        f"permanent water (km2): {km2(perm)}",
        f"flood water outside permanent water (km2): {km2(flood)}",
        f"flood added by FLEXTH extension (km2): {km2(extended)}",
        f"FwDET  depth mean/median/p95/max (m): {stats(depth_fw)}",
        f"FLEXTH depth mean/median/p95/max (m): {stats(depth_fx)}",
        f"FLEXTH edge pixels kept: {fx_info.get('edge_kept', 0)} of "
        f"{fx_info.get('edge_pixels', 0)}",
        "FwDET vs FLEXTH mean |difference| (m): "
        + (f"{np.abs(depth_fw[both] - depth_fx[both]).mean():.2f}" if both.any() else "n/a"),
        "",
        *lines_notice,
    ]
    if not args.no_ancillary:
        lines.append(ancillary.ATTRIBUTION)
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
