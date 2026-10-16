"""Search the CSDA STAC catalog for ICEYE scenes.

ICEYE data from NASA CSDA is catalogued at https://csdap.earthdata.nasa.gov/stac
(collection "iceye"), not in CMR. Searching is public; downloading requires
an approved CSDA account (see auth.py).
"""

import requests

STAC = "https://csdap.earthdata.nasa.gov/stac"
PAGE = 250


def search(collection, bbox, temporal=None, product_types=None):
    """Yield every STAC item in collection intersecting bbox (and time range)."""
    body = {"collections": [collection], "bbox": list(bbox), "limit": PAGE}
    if temporal:
        body["datetime"] = "/".join(temporal)
    url, method = f"{STAC}/search", "POST"
    s = requests.Session()
    while url:
        if method == "POST":
            r = s.post(url, json=body, timeout=120)
        else:
            r = s.get(url, timeout=120)
        r.raise_for_status()
        page = r.json()
        for item in page["features"]:
            if product_types and item["properties"].get("product:type") not in product_types:
                continue
            yield item
        nxt = next((l for l in page.get("links", []) if l.get("rel") == "next"), None)
        if not nxt or not page["features"]:
            break
        url = nxt["href"]
        method = nxt.get("method", "GET").upper()
        if nxt.get("body"):
            body = nxt["body"]


def data_assets(item):
    """Asset keys worth downloading (data + metadata; skips the PNG thumbnail)."""
    return [k for k, a in item["assets"].items()
            if k != "thumbnail" and "thumbnail" not in a.get("roles", [])]
