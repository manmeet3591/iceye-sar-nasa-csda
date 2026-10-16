"""Step 1: find every ICEYE scene over the AOI and write a public manifest.

Searches the CSDA STAC catalog (public, no login needed). The manifest holds
only catalog metadata (IDs, times, footprints, geometry parameters) and no
imagery or thumbnails, so it is safe to commit.

    python scripts/01_search.py --config config/kentucky.yaml
"""

import argparse
import csv
import json
import sys
from collections import Counter

sys.path.insert(0, "src")
from iceye_csda import stac  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402

PROPS = ["datetime", "product:type", "platform", "sar:instrument_mode",
         "iceye:acquisition_mode", "sar:polarizations", "sar:orbit_state",
         "sar:observation_direction", "iceye:incidence_near", "iceye:incidence_center",
         "iceye:incidence_far", "csda:file_format"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/kentucky.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)

    items = list(stac.search(cfg["stac"]["collection"], cfg["bbox"],
                             cfg["temporal"] or None, cfg["products"] or None))
    if not items:
        sys.exit("No ICEYE scenes found for this area/time.")

    out = cfg["paths"]["manifest"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", *PROPS, "bbox", "assets", "total_size_mb"])
        for it in sorted(items, key=lambda i: i["properties"]["datetime"]):
            keys = stac.data_assets(it)
            size = sum(it["assets"][k].get("file:size", 0) for k in keys)
            p = it["properties"]
            w.writerow([it["id"],
                        *[json.dumps(p.get(k)) if isinstance(p.get(k), list) else p.get(k, "")
                          for k in PROPS],
                        " ".join(f"{v:.5f}" for v in it["bbox"]),
                        " ".join(keys), f"{size / 1e6:.1f}"])

    geo = out.with_suffix(".geojson")
    with open(geo, "w") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": it["id"], "geometry": it["geometry"],
             "properties": {k: it["properties"].get(k) for k in PROPS}} for it in items]}, f)

    types = Counter(i["properties"].get("product:type") for i in items)
    dates = Counter(i["properties"]["datetime"][:10] for i in items)
    total = sum(it["assets"][k].get("file:size", 0) for it in items for k in stac.data_assets(it))
    print(f"{len(items)} ICEYE item(s): {dict(types)}")
    print("dates:", ", ".join(f"{d} ({n})" for d, n in sorted(dates.items())))
    print(f"total download size: {total / 1e9:.1f} GB")
    print(f"manifest: {out}\nfootprints: {geo}")


if __name__ == "__main__":
    main()
