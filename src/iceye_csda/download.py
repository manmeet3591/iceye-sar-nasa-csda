"""Download granule files with resume support."""

from pathlib import Path
from urllib.parse import unquote, urlparse

from .auth import earthdata_session

CHUNK = 8 * 1024 * 1024


def filename_from_url(url):
    return unquote(Path(urlparse(url).path).name)


def download(url, out_dir, session=None, overwrite=False):
    """Download url into out_dir. Skips complete files and resumes partial ones."""
    session = session or earthdata_session()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / filename_from_url(url)
    part = dest.with_name(dest.name + ".part")

    if dest.exists() and not overwrite:
        return dest

    headers = {}
    mode = "wb"
    if part.exists():
        headers["Range"] = f"bytes={part.stat().st_size}-"
        mode = "ab"

    with session.get(url, headers=headers, stream=True, timeout=300) as r:
        if r.status_code == 416:  # already complete
            part.rename(dest)
            return dest
        if r.status_code == 200:
            mode = "wb"  # server ignored Range
        elif r.status_code != 206:
            r.raise_for_status()
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise RuntimeError(
                f"Got an HTML page instead of data for {url}. The token is probably "
                "invalid/expired or your account is not approved for this collection."
            )
        with open(part, mode) as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)
    part.rename(dest)
    return dest
