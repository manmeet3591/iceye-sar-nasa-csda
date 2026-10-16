"""Fail if licensed ICEYE data (or anything that looks like it) is tracked by git.

Used as a pre-commit hook and in CI. Usage:
    python tools/check_no_licensed_data.py            # check all tracked files
    python tools/check_no_licensed_data.py FILE ...   # check given files
"""

import subprocess
import sys
from pathlib import Path

BLOCKED_EXT = {".tif", ".tiff", ".h5", ".hdf5", ".nitf", ".ntf", ".zip", ".tar",
               ".gz", ".vrt", ".img", ".jp2", ".png", ".jpg", ".jpeg", ".kmz", ".kml", ".npy"}
ALLOWED_PREFIXES = ("data/manifest/",)
MAX_BYTES = 5 * 1024 * 1024
NOTEBOOK_IMAGE_MARKERS = ('"image/png"', '"image/jpeg"')


def problems(path):
    p = Path(path)
    if not p.is_file():
        return []
    rel = p.as_posix()
    out = []
    if p.suffix.lower() in BLOCKED_EXT:
        out.append("raster/archive file type")
    if "ICEYE" in p.name.upper() and p.suffix.lower() in (".xml", ".json"):
        out.append("ICEYE metadata sidecar")
    if rel.startswith("data/") and not rel.startswith(ALLOWED_PREFIXES) and rel != "data/README.md":
        out.append("file under data/")
    if p.stat().st_size > MAX_BYTES:
        out.append(f"larger than {MAX_BYTES // 1024 // 1024} MB")
    if p.suffix == ".ipynb":
        text = p.read_text(errors="ignore")
        if any(m in text for m in NOTEBOOK_IMAGE_MARKERS):
            out.append("notebook contains image outputs (clear outputs before committing)")
    return out


def main(argv):
    files = argv or subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                                   check=True).stdout.split()
    bad = {f: problems(f) for f in files}
    bad = {f: r for f, r in bad.items() if r}
    if bad:
        print("Blocked: these files may contain licensed ICEYE data (see DATA_LICENSE.md):")
        for f, reasons in bad.items():
            print(f"  {f}: {', '.join(reasons)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
