"""FAA NASR airport detail — based-aircraft counts + owner/manager contacts.

The NASR APT subscription is a fixed-width APT.txt (no CSV). FAA's Akamai 403s
headless browsers and throws intermittent 503s, but a plain request with a real
browser User-Agent + retry-on-503 works. We discover the current 28-day cycle from
the NASR page, download that cycle's APT.zip, and parse the APT base records.
"""
import io
import re
import time
import zipfile
from datetime import date

import requests

from . import db

NASR_PAGE = "https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/"
CYCLE_ZIP = "https://nfdc.faa.gov/webContent/28DaySub/{cycle}/APT.zip"
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,*/*", "Accept-Language": "en-US,en;q=0.9"}

# APT base record: element -> (1-based start, length), from Layout_Data/apt_rf.txt
FIELDS = {
    "location_id": (28, 4), "site_number": (4, 11), "state": (51, 20), "city": (94, 40),
    "facility_name": (134, 50), "owner_name": (188, 35), "owner_phone": (340, 16),
    "manager_name": (356, 35), "manager_phone": (508, 16),
    "based_single": (1005, 3), "based_multi": (1008, 3), "based_jet": (1011, 3),
    "based_heli": (1014, 3), "based_glider": (1017, 3), "based_military": (1020, 3),
    "based_ultralight": (1023, 3),
}
TEXT_COLS = ["location_id", "site_number", "facility_name", "city", "state",
             "owner_name", "owner_phone", "manager_name", "manager_phone"]
INT_COLS = ["based_single", "based_multi", "based_jet", "based_heli", "based_glider",
            "based_military", "based_ultralight"]
ALL_COLS = TEXT_COLS + INT_COLS + ["based_total"]


def _get(url: str, tries: int = 6) -> requests.Response:
    """GET with browser headers + retry through FAA's intermittent Akamai 503s."""
    last = None
    for i in range(tries):
        last = requests.get(url, headers=H, timeout=120)
        if last.status_code == 200:
            return last
        time.sleep(2.5)
    last.raise_for_status()
    return last


def current_cycle(log) -> str:
    """Scrape the NASR page for 28-day cycle dates; return the latest one <= today."""
    html = _get(NASR_PAGE).text
    dates = sorted(set(re.findall(r"NASR_Subscription/(\d{4}-\d{2}-\d{2})", html)))
    today = date.today().isoformat()
    eligible = [d for d in dates if d <= today]
    cycle = eligible[-1] if eligible else (dates[-1] if dates else None)
    if not cycle:
        raise RuntimeError("could not determine NASR cycle from page")
    log.info(f"NASR cycle: {cycle}")
    return cycle


def _field(line: str, start: int, ln: int) -> str:
    return line[start - 1:start - 1 + ln].strip()


def ingest_faa_airports(log, run_id=None) -> dict:
    cycle = current_cycle(log)
    url = CYCLE_ZIP.format(cycle=cycle)
    log.info(f"GET {url}")
    content = _get(url).content
    log.info(f"APT.zip {len(content)//1024} KB")
    zf = zipfile.ZipFile(io.BytesIO(content))
    apt = [n for n in zf.namelist() if n.upper().endswith("APT.TXT")][0]

    rows = []
    with zf.open(apt) as f:
        for raw in io.TextIOWrapper(f, encoding="latin-1"):
            if raw[:3] != "APT":            # only base airport records
                continue
            rec = {k: _field(raw, *pos) for k, pos in FIELDS.items()}
            ints = {c: int(rec[c]) if rec[c].isdigit() else 0 for c in INT_COLS}
            rec.update(ints)
            rec["based_total"] = sum(ints.values())
            rows.append(tuple(rec[c] for c in ALL_COLS))

    buf = io.StringIO()
    import csv
    csv.writer(buf).writerows(rows)
    buf.seek(0)
    with db.cursor(dict_rows=False) as cur:
        cur.execute("TRUNCATE faa_airport_detail")
        cur.copy_expert(f"COPY faa_airport_detail ({','.join(ALL_COLS)}) FROM STDIN WITH (FORMAT csv)", buf)

    jets = db.query_one("SELECT count(*) c, COALESCE(sum(based_jet),0) s FROM faa_airport_detail WHERE based_jet > 0")
    log.info(f"loaded faa_airport_detail: {len(rows):,} airports; {jets['s']:,} based jets at {jets['c']:,} airports")
    return {"airports": len(rows), "airports_with_jets": jets["c"], "total_based_jets": jets["s"]}
