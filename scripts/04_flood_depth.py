"""Step 4: flood extent + flood depth from a geocoded sigma0 scene and USGS 3DEP DEM.

Outputs in outputs/<scene>/:
  water_mask.tif   binary flood extent       (derived product)
  flood_depth.tif  depth in metres            (derived product)
  summary.txt      threshold, flooded area, depth statistics

    python scripts/04_flood_depth.py data/processed/<scene>_sigma0_db.tif
    python scripts/04_flood_depth.py <scene> --reference <pre-flood scene>  # remove permanent water
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
from iceye_csda import DERIVED_NOTICE, CSDA_ACK, dem as demlib  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.flood import flood_depth, water_mask  # noqa: E402


def write_like(ref_path, out_path, arr, dtype, nodata):
    import rasterio

    with rasterio.open(ref_path) as ref:
        profile = ref.profile.copy()
    profile.update(dtype=dtype, nodata=nodata, count=1, compress="deflate")
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)
        dst.update_tags(NOTICE=DERIVED_NOTICE, ACKNOWLEDGMENT=CSDA_ACK)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", type=Path, help="geocoded *_sigma0_db.tif")
    ap.add_argument("--reference", type=Path, help="pre-flood scene on the same grid")
    ap.add_argument("--dem", type=Path, help="existing DEM GeoTIFF (else fetch 3DEP)")
    ap.add_argument("--config", default="config/kentucky.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    fc = cfg["flood"]

    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(args.scene) as src:
        db = src.read(1)
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        pixel_area = abs(src.transform.a * src.transform.e)

    mask, thr = water_mask(db, fc["water_threshold_db"], fc["min_water_pixels"])
    if args.reference:
        from iceye_csda.dem import align_to
        ref_db = align_to(args.reference, args.scene)
        perm, _ = water_mask(ref_db, thr, fc["min_water_pixels"])
        mask &= ~perm

    dem_path = args.dem
    if dem_path is None:
        cfg["paths"]["dem"].mkdir(parents=True, exist_ok=True)
        dem_path = cfg["paths"]["dem"] / f"{args.scene.stem}_3dep.tif"
        if not dem_path.exists():
            print("Fetching USGS 3DEP DEM ...")
            demlib.fetch_3dep(bounds, resolution=10, out_path=dem_path)
    dem = demlib.align_to(dem_path, args.scene)

    depth = flood_depth(mask, dem, fc["depth_smoothing_px"], valid=np.isfinite(dem) & np.isfinite(db))

    out = cfg["paths"]["outputs"] / args.scene.stem.replace("_sigma0_db", "")
    out.mkdir(parents=True, exist_ok=True)
    write_like(args.scene, out / "water_mask.tif", mask.astype("uint8"), "uint8", 255)
    write_like(args.scene, out / "flood_depth.tif", depth, "float32", np.nan)

    d = depth[np.isfinite(depth)]
    lines = [
        f"scene: {args.scene.name}",
        f"water threshold (dB): {thr:.2f}",
        f"flooded area (km2): {mask.sum() * pixel_area / 1e6:.3f}",
        f"depth mean/median/p95/max (m): "
        + (f"{d.mean():.2f} / {np.median(d):.2f} / {np.percentile(d, 95):.2f} / {d.max():.2f}"
           if d.size else "n/a"),
        "",
        DERIVED_NOTICE,
        CSDA_ACK,
    ]
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
