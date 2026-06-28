# clar.api — Clario API proxy helper
# Usage: from clar.api import clar_api
import json, os, urllib.request, ssl, certifi

API = os.environ.get("CLAR_API_URL", "https://hub.clario.chat")
JWT = os.environ.get("CLAR_JWT", "")


def clar_api(endpoint, params=None, provider="fmp"):
    """Call the Clario data proxy API.

    Args:
        endpoint: FMP endpoint path, e.g. "/quote/AAPL"
        params: Optional dict of query parameters
        provider: API provider ("fmp" or "polygon")

    Returns:
        Parsed JSON response from the provider
    """
    body = {"provider": provider, "endpoint": endpoint}
    if params:
        body["params"] = params
    req = urllib.request.Request(
        f"{API}/api/data",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {JWT}",
            "Content-Type": "application/json",
            "User-Agent": "Clario/1.0",
        },
    )
    ctx = ssl.create_default_context(cafile=certifi.where())
    return json.loads(urllib.request.urlopen(req, context=ctx).read())
