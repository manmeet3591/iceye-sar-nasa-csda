"""Search NASA's Common Metadata Repository (CMR) for ICEYE collections and granules.

CMR metadata is public; querying it does not require a token, but CSDA
collections can be restricted, so the token is sent when available.
"""

import os

import requests

CMR = "https://cmr.earthdata.nasa.gov/search"
PAGE_SIZE = 2000


def _session():
    s = requests.Session()
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


def find_collections(provider="CSDA", keyword="ICEYE"):
    """Return CMR collection entries for the provider matching keyword."""
    r = _session().get(
        f"{CMR}/collections.json",
        params={"provider": provider, "keyword": keyword, "page_size": PAGE_SIZE},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["feed"]["entry"]


def _bbox_param(bbox):
    return ",".join(str(v) for v in bbox)


def find_granules(collection_concept_id, bbox, temporal=None):
    """Yield every granule in the collection intersecting bbox (and time range)."""
    params = {
        "collection_concept_id": collection_concept_id,
        "bounding_box": _bbox_param(bbox),
        "page_size": PAGE_SIZE,
        "sort_key": "start_date",
    }
    if temporal:
        params["temporal"] = ",".join(temporal)
    s = _session()
    search_after = None
    while True:
        headers = {"CMR-Search-After": search_after} if search_after else {}
        r = s.get(f"{CMR}/granules.json", params=params, headers=headers, timeout=120)
        r.raise_for_status()
        entries = r.json()["feed"]["entry"]
        yield from entries
        search_after = r.headers.get("CMR-Search-After")
        if not entries or not search_after:
            break


def data_links(granule):
    """Downloadable data URLs for a granule (excludes browse/metadata links)."""
    urls = []
    for link in granule.get("links", []):
        rel = link.get("rel", "")
        href = link.get("href", "")
        if link.get("inherited"):
            continue
        if rel.endswith("/data#") and href.startswith("http"):
            urls.append(href)
    return urls
