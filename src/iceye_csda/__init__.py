"""Tools for searching, downloading and processing ICEYE SAR data from NASA CSDA,
with a flood extent and flood depth workflow for teaching."""

__version__ = "0.1.0"

ICEYE_COPYRIGHT = "© ICEYE US, Inc., {year}. All Rights Reserved."
DERIVED_NOTICE = "Includes copyrighted material of ICEYE US, Inc. All rights reserved."
CSDA_ACK = (
    "This work used the data made available through the NASA Commercial "
    "Satellite Data Acquisition (CSDA) Program."
)
OPEN_DATA_NOTICE = (
    "Contains ICEYE Open Data (c) ICEYE, licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)."
)

# Where a scene came from decides which notice its outputs carry. A raw scene
# folder may hold a DATA_SOURCE file containing one of these; CSDA is assumed
# otherwise, because that is the stricter licence.
SOURCE_CSDA = "csda"
SOURCE_OPEN_DATA = "iceye-open-data"


def notices(source):
    """License lines for derived products from a scene of the given source."""
    if source == SOURCE_OPEN_DATA:
        return [OPEN_DATA_NOTICE]
    return [DERIVED_NOTICE, CSDA_ACK]


def scene_source(raw_path):
    """Read data/raw/<scene>/DATA_SOURCE if present; default to CSDA."""
    from pathlib import Path

    marker = Path(raw_path).parent / "DATA_SOURCE"
    if marker.exists():
        value = marker.read_text().strip()
        if value in (SOURCE_CSDA, SOURCE_OPEN_DATA):
            return value
    return SOURCE_CSDA
