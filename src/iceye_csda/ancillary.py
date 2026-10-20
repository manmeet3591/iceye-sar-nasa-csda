"""Free ancillary layers used to clean up the SAR water mask.

- Permanent water: JRC Global Surface Water occurrence, 1984-2021 (Pekel et al.
  2016, Nature 540:418). 30 m, % of months a pixel was water. Free to use with
  attribution (Copernicus licence).
- HAND (Height Above Nearest Drainage): ASF's GLO-30 HAND, computed from the
  Copernicus GLO-30 DEM (the HAND layer used by NASA HydroSAR). 30 m.
- Slope: computed from the USGS 3DEP DEM already used for flood depth.

All are fetched only for the scene's footprint and are not ICEYE data.
"""

import math

import numpy as np

from .dem import mosaic_urls

JRC_URL = ("https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/"
           "occurrence_{name}v1_4_2021.tif")
HAND_URL = ("https://glo-30-hand.s3.amazonaws.com/v1/2021/"
            "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_HAND.tif")

ATTRIBUTION = (
    "Permanent water: JRC Global Surface Water (Pekel et al. 2016), EC JRC/Google. "
    "HAND: ASF GLO-30 HAND, derived from Copernicus GLO-30 DEM (c) DLR e.V. 2010-2014 "
    "and (c) Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the "
    "European Union and ESA. Elevation: USGS 3DEP."
)


def jrc_tile_names(bounds_wgs84):
    """JRC tiles are 10x10 degrees, named by their north-west corner, e.g. 90W_40N."""
    w, s, e, n = bounds_wgs84
    names = []
    for west in range(math.floor(w / 10) * 10, math.ceil(e / 10) * 10, 10):
        for north in range(math.floor(s / 10) * 10 + 10, math.ceil(n / 10) * 10 + 10, 10):
            lon = f"{abs(west)}{'W' if west < 0 else 'E'}"
            lat = f"{abs(north)}{'S' if north < 0 else 'N'}"
            names.append(f"{lon}_{lat}")
    return names


def hand_tile_names(bounds_wgs84):
    """GLO-30 HAND tiles are 1x1 degree, named by their south-west corner."""
    w, s, e, n = bounds_wgs84
    out = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            out.append((f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}",
                        f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"))
    return out


def fetch_permanent_water(bounds_wgs84, out_path):
    urls = [JRC_URL.format(name=nm) for nm in jrc_tile_names(bounds_wgs84)]
    return mosaic_urls(urls, bounds_wgs84, out_path, nodata=255, label="JRC water tile")


def fetch_hand(bounds_wgs84, out_path):
    urls = [HAND_URL.format(lat=la, lon=lo) for la, lo in hand_tile_names(bounds_wgs84)]
    return mosaic_urls(urls, bounds_wgs84, out_path, label="GLO-30 HAND tile")


def slope_deg(dem, pixel_size):
    """Terrain slope in degrees from a DEM on a projected grid (pixel_size in metres)."""
    gy, gx = np.gradient(dem.astype("float64"), pixel_size)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
