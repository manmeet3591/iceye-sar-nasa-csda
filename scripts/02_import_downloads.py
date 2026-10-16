"""Step 2: organize ICEYE files you downloaded by hand from the CSDA website.

No API access needed. Download the scenes listed in the manifest from the
CSDA Satellite Data Explorer (https://csdap.earthdata.nasa.gov, log in with
Earthdata) into any folder, e.g. ~/Downloads, then run:

    python scripts/02_import_downloads.py ~/Downloads
    python scripts/02_import_downloads.py ~/Downloads --copy    # keep originals

Files are matched to scenes by file name
and moved into data/raw/<scene_id>/ (git-ignored). Zip archives are unpacked.
Prints which manifest scenes are still missing.
"""

import argparse
import csv
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, "src")
from iceye_csda.config import load_config  # noqa: E402


def expand_zips(folder, scratch):
    """Unpack any .zip in folder into scratch; return list of candidate files."""
    files = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() != ".zip"]
    for z in folder.rglob("*.zip"):
        dest = scratch / z.stem
        with zipfile.ZipFile(z) as zf:
            for m in zf.infolist():
                target = (dest / m.filename).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    continue  # skip unsafe paths
                zf.extract(m, dest)
        files += [p for p in dest.rglob("*") if p.is_file()]
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path, help="folder containing downloaded files")
    ap.add_argument("--config", default="config/kentucky.yaml")
    ap.add_argument("--copy", action="store_true", help="copy instead of move")
    args = ap.parse_args()
    cfg = load_config(args.config)
    raw = cfg["paths"]["raw"]

    with open(cfg["paths"]["manifest"]) as f:
        rows = list(csv.DictReader(f))
    # asset filename -> scene id
    wanted = {a: r["item_id"] for r in rows for a in r["assets"].split()}

    scratch = raw / "_unzipped"
    found = set()
    for p in expand_zips(args.folder.expanduser(), scratch):
        item_id = wanted.get(p.name)
        if not item_id:
            continue
        dest = raw / item_id / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copy2 if args.copy else shutil.move)(p, dest)
        found.add(p.name)
        print(f"ok   {dest.relative_to(raw.parent.parent)}")
    shutil.rmtree(scratch, ignore_errors=True)

    print()
    for r in rows:
        assets = r["assets"].split()
        have = [a for a in assets if (raw / r["item_id"] / a).exists()]
        status = "complete" if len(have) == len(assets) else f"{len(have)}/{len(assets)} files"
        print(f"{r['product:type']:4} {r['item_id']}: {status}")


if __name__ == "__main__":
    main()
