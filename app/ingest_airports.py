"""OurAirports ingestion — global airports + runways (public domain / Unlicense).

Two CSVs from the maintained GitHub mirror, loaded fresh each run.
"""
import io

import pandas as pd
import requests

from . import db

BASE = "https://davidmegginson.github.io/ourairports-data"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36"}

AIRPORT_COLS = ["ident", "type", "name", "latitude_deg", "longitude_deg", "elevation_ft",
                "continent", "iso_country", "iso_region", "municipality", "scheduled_service",
                "icao_code", "iata_code", "gps_code", "local_code", "home_link", "wikipedia_link"]
RUNWAY_COLS = ["id", "airport_ident", "length_ft", "width_ft", "surface", "lighted", "closed",
               "le_ident", "he_ident"]


def _get_csv(name: str, log) -> pd.DataFrame:
    url = f"{BASE}/{name}"
    log.info(f"GET {url}")
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), dtype=str).fillna("")


def _yn(series: pd.Series) -> pd.Series:
    """OurAirports booleans are 'yes'/'no' or '1'/'0' → 'true'/'false'/'' for COPY."""
    s = series.str.strip().str.lower()
    return s.map(lambda v: "true" if v in ("yes", "1", "true") else ("false" if v in ("no", "0", "false") else ""))


def _copy(table: str, cols: list, df: pd.DataFrame, log) -> int:
    buf = io.StringIO()
    df[cols].to_csv(buf, index=False, header=False)
    buf.seek(0)
    with db.cursor(dict_rows=False) as cur:
        cur.execute(f"TRUNCATE {table}")
        cur.copy_expert(f"COPY {table} ({','.join(cols)}) FROM STDIN WITH (FORMAT csv)", buf)
    log.info(f"loaded {table}: {len(df):,} rows")
    return len(df)


def ingest_airports(log, run_id=None) -> dict:
    ap = _get_csv("airports.csv", log)
    ap["scheduled_service"] = _yn(ap["scheduled_service"])
    ap = ap.drop_duplicates(subset=["ident"])
    n_ap = _copy("airports", AIRPORT_COLS, ap, log)

    rw = _get_csv("runways.csv", log)
    rw["lighted"] = _yn(rw["lighted"])
    rw["closed"] = _yn(rw["closed"])
    rw = rw[rw["id"].str.strip() != ""].drop_duplicates(subset=["id"])
    n_rw = _copy("runways", RUNWAY_COLS, rw, log)

    jetcap = db.query_one("SELECT count(*) c FROM airport_capability WHERE longest_runway_ft >= 4000")["c"]
    return {"airports": n_ap, "runways": n_rw, "jet_capable_4000ft": jetcap}
