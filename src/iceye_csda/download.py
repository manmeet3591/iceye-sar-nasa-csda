"""Download ICEYE assets through the CSDA download API, with resume support."""

from pathlib import Path

from .auth import API, csda_session

CHUNK = 8 * 1024 * 1024


def asset_url(collection, item_id, asset_key):
    return f"{API}/v2/download/{collection}/{item_id}/{asset_key}"


def download(collection, item_id, asset_key, out_dir, session=None, expected_size=None):
    """Download one asset to out_dir/asset_key. Skips complete files, resumes partial ones."""
    session = session or csda_session()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / asset_key
    part = dest.with_name(dest.name + ".part")

    if dest.exists() and (expected_size is None or dest.stat().st_size == expected_size):
        return dest

    headers, mode = {}, "wb"
    if part.exists():
        headers["Range"] = f"bytes={part.stat().st_size}-"
        mode = "ab"

    url = asset_url(collection, item_id, asset_key)
    with session.get(url, headers=headers, stream=True, timeout=600) as r:
        if r.status_code == 416:
            part.rename(dest)
            return dest
        if r.status_code in (401, 403):
            raise RuntimeError(f"HTTP {r.status_code}: token invalid/expired or not approved "
                               f"for {collection}. {r.text[:200]}")
        if r.status_code == 200:
            mode = "wb"  # server ignored Range
        elif r.status_code != 206:
            r.raise_for_status()
        with open(part, mode) as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)
    if expected_size is not None and part.stat().st_size != expected_size:
        raise RuntimeError(f"{asset_key}: got {part.stat().st_size} bytes, expected "
                           f"{expected_size}; rerun to resume.")
    part.rename(dest)
    return dest
