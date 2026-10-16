"""Step 1: find every ICEYE granule over the AOI and write a public manifest.

The manifest holds only CMR metadata (IDs, times, footprints, URLs), which is
publicly searchable, so it is safe to commit.

    python scripts/01_search.py --config config/kentucky.yaml
"""

import argparse
import csv
import sys

sys.path.insert(0, "src")
from iceye_csda import cmr  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402

FIELDS = ["collection", "granule_ur", "producer_granule_id", "time_start", "time_end",
          "granule_size_mb", "polygon", "urls"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/kentucky.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)

    collections = cmr.find_collections(**cfg["cmr"])
    if not collections:
        sys.exit("No ICEYE collections found in CMR for provider "
                 f"{cfg['cmr']['provider']}. Check your token / CSDA approval.")
    print(f"Found {len(collections)} ICEYE collection(s):")

    rows = []
    for c in collections:
        n0 = len(rows)
        for g in cmr.find_granules(c["id"], cfg["bbox"], cfg["temporal"] or None):
            rows.append({
                "collection": c.get("short_name", c["id"]),
                "granule_ur": g.get("title", ""),
                "producer_granule_id": g.get("producer_granule_id", ""),
                "time_start": g.get("time_start", ""),
                "time_end": g.get("time_end", ""),
                "granule_size_mb": g.get("granule_size", ""),
                "polygon": ";".join(sum(g.get("polygons", []), [])),
                "urls": " ".join(cmr.data_links(g)),
            })
        print(f"  {c.get('short_name', c['id'])}: {len(rows) - n0} granule(s)")

    out = cfg["paths"]["manifest"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} granule(s) written to {out}")


if __name__ == "__main__":
    main()
