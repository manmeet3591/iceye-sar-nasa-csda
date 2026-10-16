"""Earthdata Login authentication.

The token is read from the EARTHDATA_TOKEN environment variable and is never
written to disk or logged. Generate one at https://urs.earthdata.nasa.gov
(Profile -> Generate Token).
"""

import os

import requests

EDL_HOST = "urs.earthdata.nasa.gov"


class _BearerSession(requests.Session):
    """Session that keeps the Authorization header only for Earthdata hosts.

    requests drops Authorization on cross-host redirects; CSDA downloads can
    redirect between earthdata.nasa.gov hosts, so we re-add it there and
    nowhere else (e.g. not on pre-signed S3 URLs).
    """

    def __init__(self, token):
        super().__init__()
        self._token = token
        self.headers["Authorization"] = f"Bearer {token}"

    def rebuild_auth(self, prepared_request, response):
        host = requests.utils.urlparse(prepared_request.url).hostname or ""
        if host.endswith("earthdata.nasa.gov"):
            prepared_request.headers["Authorization"] = f"Bearer {self._token}"
        else:
            prepared_request.headers.pop("Authorization", None)


def get_token():
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "EARTHDATA_TOKEN is not set. Create a token at "
            "https://urs.earthdata.nasa.gov and export it as EARTHDATA_TOKEN."
        )
    return token


def earthdata_session():
    return _BearerSession(get_token())
