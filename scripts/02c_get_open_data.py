"""Step 2 (no CSDA account): download an ICEYE Open Data scene (CC BY 4.0).

ICEYE publishes sample scenes on the AWS Open Data Registry with no login.
They use the same file formats as the CSDA products, so the rest of the
pipeline works unchanged. Files go to data/raw/<scene>/ with a DATA_SOURCE
marker, so outputs carry the CC BY 4.0 notice instead of the CSDA one.

    python scripts/02c_get_open_data.py ICEYE_DJ27J0_20250813T103121Z_5743224_X13_SM
    python scripts/02c_get_open_data.py <scene> --products GRD SLC

Lake Borgne / Pearl River (MS-LA), 13 Aug 2025: ICEYE_DJ27J0_20250813T103121Z_5743224_X13_SM
"""

import argparse
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, "src")
from iceye_csda import SOURCE_OPEN_DATA  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402

BUCKET = "https://iceye-open-data-catalog.s3.amazonaws.com"
MODES = {"SM": "stripmap", "SLF": "spot-fine", "SL": "spot", "SC": "scan", "DW": "dwell"}


def scene_prefix(scene):
    """Find the bucket folder for a scene id (mode folders are tried in turn)."""
    mode = scene.rsplit("_", 1)[-1]
    folders = [MODES[mode]] if mode in MODES else []
    folders += [f for f in ("stripmap", "spot", "spot-fine", "spot-precise",
                            "spot-extended-area", "scan", "scan-wide", "dwell",
                            "dwell-fine", "dwell-precise") if f not in folders]
    for f in folders:
        r = requests.get(BUCKET, params={"list-type": "2", "prefix": f"data/{f}/{scene}/"},
                         timeout=60)
        r.raise_for_status()
        keys = re.findall(r"<Key>([^<]+)</Key>", r.text)
        if keys:
            return keys
    raise SystemExit(f"Scene {scene} not found in the ICEYE open-data bucket.")


def download(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 22):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r   {dest.name}: {done / total:5.1%}", end="", flush=True)
    print()
    tmp.rename(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", help="ICEYE open-data scene id")
    ap.add_argument("--products", nargs="+", default=["GRD"], help="GRD, SLC, QLK ...")
    ap.add_argument("--config", default="config/kentucky.yaml")
    args = ap.parse_args()
    out = load_config(args.config)["paths"]["raw"] / args.scene
    out.mkdir(parents=True, exist_ok=True)
    (out / "DATA_SOURCE").write_text(SOURCE_OPEN_DATA + "\n")

    wanted = tuple(f"_{p.upper()}." for p in args.products)
    for key in scene_prefix(args.scene):
        name = key.rsplit("/", 1)[-1]
        if not any(w in name for w in wanted) or name.endswith((".kml", ".png")):
            continue
        dest = out / name
        if dest.exists():
            print(f"   {name}: already here")
            continue
        download(f"{BUCKET}/{key}", dest)
    print(f"Saved to {out}. Next: python scripts/03_preprocess.py --input {out}/*_GRD.tif")


if __name__ == "__main__":
    main()
