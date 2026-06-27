"""BTS L_AIRCRAFT_TYPE lookup — aircraft-type code → human-readable name.

The lookup download param is ROT13-encoded on TransStats; 'Y_NVePeNSg_glcR' = 'L_AIRCRAFT_TYPE'.
Returns a clean Code,Description CSV.
"""
import csv
import io

import requests

from . import db

URL = "https://www.transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_NVePeNSg_glcR"
H = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/124.0 Safari/537.36", "Accept": "text/csv,*/*",
     "Referer": "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=GEE"}


def ingest_aircraft_types(log, run_id=None) -> dict:
    log.info(f"GET {URL}")
    r = requests.get(URL, headers=H, timeout=60)
    r.raise_for_status()
    rows = []
    for row in csv.DictReader(io.StringIO(r.text)):
        code = (row.get("Code") or "").strip()
        if code:
            rows.append((code, (row.get("Description") or "").strip()))
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    buf.seek(0)
    with db.cursor(dict_rows=False) as cur:
        cur.execute("TRUNCATE aircraft_type_ref")
        cur.copy_expert("COPY aircraft_type_ref (code, description) FROM STDIN WITH (FORMAT csv)", buf)
    log.info(f"loaded aircraft_type_ref: {len(rows):,} codes")
    return {"codes": len(rows)}
