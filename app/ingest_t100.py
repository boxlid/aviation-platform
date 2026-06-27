"""BTS T-100 Domestic Segment ingestion via headless-browser automation.

BTS killed programmatic download of this table (it's now an ASP.NET WebForms SPA),
so we drive the real form with Playwright and capture the file. Each run pulls the
most recent N months and upserts them into t100_segment.
"""
import io
import os
import zipfile
from datetime import date

import pandas as pd

from . import db
from .config import RAW_DIR

FORM = "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=GEE&QO_fu146_anzr="
OUT = os.path.join(RAW_DIR, "t100")
MONTHS = ["", "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

# CSV column -> our table column
COLMAP = {
    "UNIQUE_CARRIER": "unique_carrier", "AIRLINE_ID": "airline_id", "UNIQUE_CARRIER_NAME": "carrier_name",
    "ORIGIN": "origin", "ORIGIN_CITY_NAME": "origin_city", "ORIGIN_STATE_ABR": "origin_state",
    "DEST": "dest", "DEST_CITY_NAME": "dest_city", "DEST_STATE_ABR": "dest_state",
    "AIRCRAFT_GROUP": "aircraft_group", "AIRCRAFT_TYPE": "aircraft_type", "AIRCRAFT_CONFIG": "aircraft_config",
    "DEPARTURES_PERFORMED": "departures", "SEATS": "seats", "PASSENGERS": "passengers",
    "FREIGHT": "freight", "MAIL": "mail", "DISTANCE": "distance",
    "YEAR": "year", "MONTH": "month", "CLASS": "class",
}
TABLE_COLS = ["year", "month", "unique_carrier", "airline_id", "carrier_name", "origin", "origin_city",
              "origin_state", "dest", "dest_city", "dest_state", "aircraft_group", "aircraft_type",
              "aircraft_config", "departures", "seats", "passengers", "freight", "mail", "distance", "class"]


def recent_periods(n: int, lag_months: int = 4) -> list:
    """The n most recent (year, month) periods likely published (BTS lags ~3-4 months)."""
    today = date.today()
    base = today.year * 12 + (today.month - 1) - lag_months
    return [((base - i) // 12, (base - i) % 12 + 1) for i in range(n)]


def download_month(page, year: int, month: int, log) -> str:
    """Drive the BTS form for one (year, month); return the extracted CSV path (or '' if empty)."""
    page.goto(FORM, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(700)

    def settle():
        page.wait_for_load_state("networkidle", timeout=60000)
        page.wait_for_timeout(600)

    page.select_option("#cboGeography", label="All"); settle()
    page.select_option("#cboYear", label=str(year)); settle()
    page.select_option("#cboPeriod", label=MONTHS[month]); settle()
    page.check("#chkAllVars", force=True); settle()
    with page.expect_download(timeout=240000) as dlinfo:
        page.click("input[value='Download']")
    dl = dlinfo.value
    os.makedirs(OUT, exist_ok=True)
    zip_path = os.path.join(OUT, f"T100D_{year}_{month:02d}.zip")
    dl.save_as(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
        out_csv = os.path.join(OUT, f"T100D_{year}_{month:02d}.csv")
        with zf.open(csv_name) as src, open(out_csv, "wb") as dst:
            dst.write(src.read())
    log.info(f"downloaded {year}-{month:02d}: {os.path.getsize(zip_path)/1e6:.1f} MB")
    return out_csv


def load_csv(path: str, log) -> int:
    df = pd.read_csv(path, dtype=str, usecols=lambda c: c.strip() in COLMAP).fillna("")
    if df.empty:
        return 0
    df = df.rename(columns={k: v for k, v in COLMAP.items()})
    df = df[[c for c in TABLE_COLS if c in df.columns]]
    df = df.drop_duplicates(subset=["year", "month", "unique_carrier", "origin", "dest",
                                    "aircraft_type", "aircraft_config", "class"])
    buf = io.StringIO(); df[TABLE_COLS].to_csv(buf, index=False, header=False); buf.seek(0)
    with db.cursor(dict_rows=False) as cur:
        cur.execute("CREATE TEMP TABLE _t100_stage (LIKE t100_segment INCLUDING DEFAULTS) ON COMMIT DROP")
        cur.copy_expert(f"COPY _t100_stage ({','.join(TABLE_COLS)}) FROM STDIN WITH (FORMAT csv)", buf)
        cur.execute("""
            INSERT INTO t100_segment SELECT * FROM _t100_stage
            ON CONFLICT (year, month, unique_carrier, origin, dest, aircraft_type, aircraft_config, class)
            DO UPDATE SET departures=EXCLUDED.departures, seats=EXCLUDED.seats, passengers=EXCLUDED.passengers,
                          freight=EXCLUDED.freight, mail=EXCLUDED.mail, distance=EXCLUDED.distance,
                          carrier_name=EXCLUDED.carrier_name""")
    return len(df)


def ingest_t100(log, run_id=None, months: int = 3) -> dict:
    from playwright.sync_api import sync_playwright
    periods = recent_periods(months)
    log.info(f"target periods: {periods}")
    total, loaded = 0, []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(accept_downloads=True)
        try:
            for (y, m) in periods:
                try:
                    csv = download_month(page, y, m, log)
                    n = load_csv(csv, log)
                    log.info(f"loaded {y}-{m:02d}: {n:,} segment rows")
                    total += n; loaded.append(f"{y}-{m:02d}")
                except Exception as e:
                    log.warning(f"skip {y}-{m:02d}: {e}")
        finally:
            browser.close()
    charter = db.query_one("SELECT count(*) c FROM charter_routes")["c"]
    return {"months_loaded": loaded, "rows": total, "charter_segments": charter}
