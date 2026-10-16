"""CSDA download authentication.

CSDA's download API (https://csdap.earthdata.nasa.gov/api/v2/download/...)
accepts a CSDA-issued access token, not a raw Earthdata Login token. Two ways
to get one:

1. Machine-to-machine (recommended for scripts): ask the CSDA program for an
   API client ID and secret, then set CSDA_CLIENT_ID and CSDA_CLIENT_SECRET.
   They are exchanged for a short-lived token automatically.
2. Browser token: log in to https://csdap.earthdata.nasa.gov with Earthdata
   Login and set CSDA_TOKEN to the access token the site issues you.

Secrets are read from environment variables only and never written to disk.
"""

import os

import requests

API = "https://csdap.earthdata.nasa.gov/api"


def get_token():
    token = os.environ.get("CSDA_TOKEN", "").strip()
    if token:
        return token
    cid = os.environ.get("CSDA_CLIENT_ID", "").strip()
    secret = os.environ.get("CSDA_CLIENT_SECRET", "").strip()
    if cid and secret:
        r = requests.post(f"{API}/v1/auth/token", timeout=60, data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": secret,
        })
        r.raise_for_status()
        return r.json()["access_token"]
    raise RuntimeError(
        "No CSDA credentials. Set CSDA_TOKEN, or CSDA_CLIENT_ID and "
        "CSDA_CLIENT_SECRET. See docs/STUDENT_ACCESS.md."
    )


class _CSDASession(requests.Session):
    """Sends the token to CSDA only; drops it on redirect to pre-signed S3 URLs."""

    def __init__(self, token):
        super().__init__()
        self._token = token
        self.headers["Authorization"] = f"Bearer {token}"

    def rebuild_auth(self, prepared_request, response):
        host = requests.utils.urlparse(prepared_request.url).hostname or ""
        if host == "csdap.earthdata.nasa.gov":
            prepared_request.headers["Authorization"] = f"Bearer {self._token}"
        else:
            prepared_request.headers.pop("Authorization", None)


def csda_session():
    return _CSDASession(get_token())
