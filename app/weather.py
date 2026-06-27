"""Aviation weather from NOAA/NWS aviationweather.gov Data API (free, public domain).

Pulls METAR, TAF, nearby PIREPs, and SIGMET/AIRMET hazards over an airport. Results
are cached briefly (weather changes hourly, not per page-load).

Public API: report(icao, lat, lon) -> dict
"""
from __future__ import annotations

import time

import requests

BASE = "https://aviationweather.gov/api/data"
H = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36", "Accept": "application/json"}
TTL = 300  # seconds
_CACHE: dict = {}


def _api(path: str, **params):
    try:
        r = requests.get(f"{BASE}/{path}", params={**params, "format": "json"}, headers=H, timeout=15)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
    except Exception:
        pass
    return None


def _point_in_poly(lat: float, lon: float, coords: list) -> bool:
    """Ray-casting point-in-polygon. coords = [{'lat':..,'lon':..}, ...]."""
    pts = [(c["lon"], c["lat"]) for c in coords if c.get("lat") is not None and c.get("lon") is not None]
    if len(pts) < 3:
        return False
    inside, j = False, len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _hazards(lat: float, lon: float) -> list:
    out = []
    for ep in ("airsigmet", "isigmet"):
        for h in (_api(ep) or []):
            try:
                if _point_in_poly(lat, lon, h.get("coords") or []):
                    out.append({
                        "source": "SIGMET/AIRMET" if ep == "airsigmet" else "Intl SIGMET",
                        "hazard": h.get("hazard"),
                        "severity": h.get("severity"),
                        "validTimeTo": h.get("validTimeTo"),
                        "altitudeLow": h.get("altitudeLow1"),
                        "altitudeHi": h.get("altitudeHi1"),
                        "raw": h.get("rawAirSigmet") or h.get("rawSigmet"),
                    })
            except Exception:
                continue
    return out


def report(icao: str, lat: float | None, lon: float | None) -> dict:
    key = (icao, round(lat, 2) if lat else None, round(lon, 2) if lon else None)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < TTL:
        return cached[1]

    metar = _api("metar", ids=icao, hours=2)
    taf = _api("taf", ids=icao)
    pireps = _api("pirep", id=icao, distance=150) if lat else None
    out = {
        "station": icao,
        "metar": metar[0] if isinstance(metar, list) and metar else None,
        "taf": taf[0] if isinstance(taf, list) and taf else None,
        "pireps": (pireps if isinstance(pireps, list) else [])[:8],
        "hazards": _hazards(lat, lon) if (lat is not None and lon is not None) else [],
    }
    _CACHE[key] = (now, out)
    return out
