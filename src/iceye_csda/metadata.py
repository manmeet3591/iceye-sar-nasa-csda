"""Read ICEYE product metadata (XML or JSON sidecar, or GeoTIFF tags)."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

# Keys used by the processing chain. ICEYE metadata spells these the same way in
# its XML and JSON sidecars.
KEYS = (
    "product_type",
    "product_level",
    "acquisition_start_utc",
    "calibration_factor",
    "incidence_near",
    "incidence_center",
    "incidence_far",
    "look_side",
    "orbit_direction",
    "polarization",
    "range_spacing",
    "azimuth_spacing",
)


def _from_xml(path):
    root = ET.parse(path).getroot()
    out = {}
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in KEYS and el.text and tag not in out:
            out[tag] = el.text.strip()
    return out


def _flatten(d, out):
    for k, v in d.items():
        if isinstance(v, dict):
            _flatten(v, out)
        elif k in KEYS and k not in out:
            out[k] = v
    return out


def _from_json(path):
    with open(path) as f:
        return _flatten(json.load(f), {})


def _from_tiff_tags(path):
    import rasterio

    with rasterio.open(path) as src:
        tags = src.tags()
    out = {}
    raw = tags.get("ICEYE_PROPERTIES")
    if raw:
        try:
            _flatten(json.loads(raw), out)
        except json.JSONDecodeError:
            pass
    for k in KEYS:
        if k in tags and k not in out:
            out[k] = tags[k]
    return out


def _coerce(md):
    for k in ("calibration_factor", "incidence_near", "incidence_center",
              "incidence_far", "range_spacing", "azimuth_spacing"):
        if k in md:
            try:
                md[k] = float(md[k])
            except (TypeError, ValueError):
                pass
    return md


def read_metadata(product_path):
    """Find and parse metadata for an ICEYE product file."""
    p = Path(product_path)
    md = {}
    for cand in (p.with_suffix(".xml"), p.with_suffix(".json")):
        if cand.exists():
            md.update(_from_xml(cand) if cand.suffix == ".xml" else _from_json(cand))
    if p.suffix.lower() in (".tif", ".tiff"):
        for k, v in _from_tiff_tags(p).items():
            md.setdefault(k, v)
    return _coerce(md)
