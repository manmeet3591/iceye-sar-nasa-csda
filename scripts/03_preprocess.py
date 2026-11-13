"""Step 3: calibrate, speckle-filter and geocode ICEYE GRD (and SLC) scenes.

Outputs data/processed/<scene>_sigma0_db.tif (UTM, 10 m). These are
value-added products: they stay local and must not be published.

    python scripts/03_preprocess.py
    python scripts/03_preprocess.py --input data/raw/some/scene_GRD.tif
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")
from iceye_csda import sar, scene_source  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.metadata import read_metadata  # noqa: E402


def process_grd(path, out_dir, cfg):
    import rasterio

    md = read_metadata(path)
    res = cfg["flood"]["target_resolution_m"]
    out = out_dir / f"{path.stem}_sigma0_db.tif"
    with rasterio.open(path) as src:
        tags = src.tags()
    tags["DATA_SOURCE"] = scene_source(path)
    geo = sar.georeference(path, md)

    # Multilook to ~target resolution in strips (memory-safe), then calibrate.
    spacing = max(md.get("range_spacing") or 1.0, md.get("azimuth_spacing") or 1.0)
    factor = max(1, int(round(res / spacing)))
    dn2, full_shape = sar.read_multilooked(path, factor)
    sigma0 = sar.calibrate_intensity(dn2, md, factor, full_shape)
    sigma0 = sar.lee_filter(sigma0, cfg["flood"]["speckle_window"])
    sar.geocode_array(sar.to_db(sigma0), out, resolution=res, tags=tags,
                      **sar.scale_georef(geo, factor))
    print(f"   multilook {factor}x{factor}, calibration factor {md['calibration_factor']:.3e}")
    return out


def process_slc(path, out_dir, cfg):
    """SLC (HDF5): multilook to roughly square pixels, then calibrate.

    SLC is in slant-range geometry without GCPs in GeoTIFF form, so this writes
    an un-geocoded sigma0 array (.npy) for teaching amplitude/phase concepts.
    Use GRD for the flood-depth workflow.
    """
    import h5py

    with h5py.File(path, "r") as h5:
        i, q = h5["s_i"][:], h5["s_q"][:]
        md = {k: (float(h5[k][()]) if np.ndim(h5[k][()]) == 0 and
                  np.issubdtype(np.asarray(h5[k][()]).dtype, np.number) else None)
              for k in ("calibration_factor", "incidence_near", "incidence_center",
                        "incidence_far", "range_spacing", "azimuth_spacing") if k in h5}
    rs, az = md.get("range_spacing") or 1.0, md.get("azimuth_spacing") or 1.0
    looks = (max(1, round(rs / az)), 1) if rs > az else (1, max(1, round(az / rs)))
    amp = sar.slc_to_amplitude(i, q, looks)
    sigma0 = sar.lee_filter(sar.calibrate_sigma0(amp, md), cfg["flood"]["speckle_window"])
    out = out_dir / f"{path.stem}_sigma0_db_slant.npy"
    np.save(out, sar.to_db(sigma0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/kentucky.yaml")
    ap.add_argument("--input", nargs="*", type=Path)
    args = ap.parse_args()
    cfg = load_config(args.config)
    out_dir = cfg["paths"]["processed"]
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = cfg["paths"]["raw"]
    files = args.input or sorted(
        [p for p in raw.rglob("*") if p.suffix.lower() in (".tif", ".tiff", ".h5")]
    )
    for p in files:
        name = p.name.upper()
        try:
            if p.suffix.lower() in (".tif", ".tiff") and "GRD" in name:
                print("GRD ->", process_grd(p, out_dir, cfg))
            elif p.suffix.lower() == ".h5" and "SLC" in name:
                print("SLC ->", process_slc(p, out_dir, cfg))
            else:
                print("skip", p.name)
        except Exception as e:
            print(f"FAIL {p}: {e}")


if __name__ == "__main__":
    main()
