"""Step 2: download the scenes listed in the manifest into data/raw/ (git-ignored).

Requires CSDA credentials (CSDA_TOKEN, or CSDA_CLIENT_ID + CSDA_CLIENT_SECRET)
for an account approved for ICEYE data.

    python scripts/02_download.py                   # everything in the manifest
    python scripts/02_download.py --products GRD    # only GRD scenes (smaller)
    python scripts/02_download.py --limit 1 --dry-run
"""

import argparse
import csv
import sys

import requests

sys.path.insert(0, "src")
from iceye_csda.auth import csda_session  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.download import asset_url, download  # noqa: E402
from iceye_csda.stac import STAC  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/kentucky.yaml")
    ap.add_argument("--products", nargs="*", help="e.g. GRD SLC (default: config / all)")
    ap.add_argument("--limit", type=int, help="max number of scenes")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    coll = cfg["stac"]["collection"]
    products = args.products if args.products is not None else cfg["products"]

    with open(cfg["paths"]["manifest"]) as f:
        rows = [r for r in csv.DictReader(f)
                if not products or r["product:type"] in products]
    if args.limit:
        rows = rows[: args.limit]

    session = None if args.dry_run else csda_session()
    n_ok = n_fail = 0
    for row in rows:
        item_id = row["item_id"]
        out_dir = cfg["paths"]["raw"] / item_id
        item = requests.get(f"{STAC}/collections/{coll}/items/{item_id}", timeout=60).json()
        for key in row["assets"].split():
            size = item["assets"].get(key, {}).get("file:size")
            if args.dry_run:
                print(f"[dry-run] {asset_url(coll, item_id, key)}  ({(size or 0) / 1e6:.0f} MB)")
                continue
            try:
                path = download(coll, item_id, key, out_dir, session=session, expected_size=size)
                print(f"ok   {path}")
                n_ok += 1
            except Exception as e:  # keep going; report at the end
                print(f"FAIL {item_id}/{key}: {e}")
                n_fail += 1
    if not args.dry_run:
        print(f"\nDownloaded {n_ok} file(s), {n_fail} failure(s).")


if __name__ == "__main__":
    main()
