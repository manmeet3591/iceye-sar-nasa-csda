"""Step 2: download the granules listed in the manifest into data/raw/ (git-ignored).

Requires EARTHDATA_TOKEN and an approved CSDA account.

    python scripts/02_download.py                   # everything in the manifest
    python scripts/02_download.py --products GRD    # only GRD files
    python scripts/02_download.py --limit 3 --dry-run
"""

import argparse
import csv
import sys

sys.path.insert(0, "src")
from iceye_csda.auth import earthdata_session  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402
from iceye_csda.download import download, filename_from_url  # noqa: E402


def wanted(url, row, products):
    if not products:
        return True
    text = (filename_from_url(url) + " " + row["collection"] + " " + row["granule_ur"]).upper()
    return any(p.upper() in text for p in products)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/kentucky.yaml")
    ap.add_argument("--products", nargs="*", help="e.g. GRD SLC CSI (default: config / all)")
    ap.add_argument("--limit", type=int, help="max number of granules")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    products = args.products if args.products is not None else cfg["products"]

    with open(cfg["paths"]["manifest"]) as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    session = None if args.dry_run else earthdata_session()
    n_ok = n_fail = 0
    for row in rows:
        out_dir = cfg["paths"]["raw"] / row["collection"] / row["granule_ur"]
        for url in row["urls"].split():
            if not wanted(url, row, products):
                continue
            if args.dry_run:
                print(f"[dry-run] {url} -> {out_dir}")
                continue
            try:
                path = download(url, out_dir, session=session)
                print(f"ok   {path}")
                n_ok += 1
            except Exception as e:  # keep going; report at the end
                print(f"FAIL {url}: {e}")
                n_fail += 1
    if not args.dry_run:
        print(f"\nDownloaded {n_ok} file(s), {n_fail} failure(s).")


if __name__ == "__main__":
    main()
