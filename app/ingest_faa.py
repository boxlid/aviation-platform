"""FAA ingestion logic, shared by the managed services.

Three datasets:
  ingest_registry   — Releasable MASTER  -> faa_registry   (tail, owner, Mode S hex)
  ingest_reference  — Releasable ACFTREF -> aircraft_ref   (make/model/category decode)
  ingest_part135    — 135aircraft.xlsx   -> operators + part135_aircraft (tail -> operator)
"""
import io
import os
import time
import zipfile

import pandas as pd
import requests

from . import db
from .config import RAW_DIR

PART135_URL = "https://www.faa.gov/sites/faa.gov/files/about/office_org/field_offices/fsdo/135aircraft.xlsx"
RELEASABLE_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Decode tables for ACFTREF
_TYPE_ACFT = {"1": "Glider", "2": "Balloon", "3": "Blimp/Dirigible", "4": "Fixed wing single-engine",
              "5": "Fixed wing multi-engine", "6": "Rotorcraft", "7": "Weight-shift-control",
              "8": "Powered parachute", "9": "Gyroplane", "H": "Hybrid lift", "O": "Other"}
_TYPE_ENG = {"0": "None", "1": "Reciprocating", "2": "Turbo-prop", "3": "Turbo-shaft", "4": "Turbo-jet",
             "5": "Turbo-fan", "6": "Ramjet", "7": "2-cycle", "8": "4-cycle", "9": "Unknown",
             "10": "Electric", "11": "Rotary"}


def _fetch(url: str, dest: str, log) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    log.info(f"GET {url}")
    with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    log.info(f"saved {dest} ({os.path.getsize(dest)/1e6:.1f} MB)")
    return dest


def ensure_releasable(log, max_age_hours: float = 6.0) -> str:
    """Download + extract the registry zip unless a fresh copy already exists. Returns the extract dir."""
    out_dir = os.path.join(RAW_DIR, "releasable")
    master = os.path.join(out_dir, "MASTER.txt")
    if os.path.exists(master) and (time.time() - os.path.getmtime(master)) < max_age_hours * 3600:
        log.info(f"using cached registry extract ({(time.time()-os.path.getmtime(master))/3600:.1f}h old)")
        return out_dir
    zip_path = _fetch(RELEASABLE_URL, os.path.join(RAW_DIR, "ReleasableAircraft.zip"), log)
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    log.info(f"extracted registry -> {out_dir}")
    return out_dir


def _find_col(df, *needles):
    for c in df.columns:
        lc = c.strip().lower()
        if all(n in lc for n in needles):
            return c
    raise KeyError(f"no column matching {needles} in {list(df.columns)}")


def _norm_tail(s):
    s = s.fillna("").astype(str).str.strip().str.upper()
    return s.where(s == "", "N" + s.str.lstrip("N"))


# ── Service entry points ──────────────────────────────────────────────────────

def ingest_registry(log, run_id=None) -> dict:
    out_dir = ensure_releasable(log)
    path = os.path.join(out_dir, "MASTER.txt")
    log.info("parsing MASTER.txt")
    df = pd.read_csv(path, dtype=str, skipinitialspace=True, low_memory=False).fillna("")
    df.columns = [c.strip() for c in df.columns]
    cols = {
        "n_number": _find_col(df, "n-number"), "serial_number": _find_col(df, "serial"),
        "mfr_mdl_code": _find_col(df, "mfr", "mdl", "code"), "year_mfr": _find_col(df, "year", "mfr"),
        "registrant_type": _find_col(df, "type", "registrant"), "registrant_name": _find_col(df, "name"),
        "city": _find_col(df, "city"), "state": _find_col(df, "state"), "status_code": _find_col(df, "status"),
        "mode_s_code_octal": _find_col(df, "mode", "code"), "mode_s_hex": _find_col(df, "mode", "hex"),
    }
    out = pd.DataFrame({k: df[v].str.strip() for k, v in cols.items()})
    out["n_number"] = _norm_tail(out["n_number"])
    out["mode_s_hex"] = out["mode_s_hex"].str.upper()
    out = out.drop_duplicates(subset=["n_number"])
    buf = io.StringIO(); out.to_csv(buf, index=False, header=False); buf.seek(0)
    with db.cursor(dict_rows=False) as cur:
        cur.execute("TRUNCATE faa_registry")
        cur.copy_expert(
            "COPY faa_registry (n_number, serial_number, mfr_mdl_code, year_mfr, registrant_type, "
            "registrant_name, city, state, status_code, mode_s_code_octal, mode_s_hex) FROM STDIN WITH (FORMAT csv)",
            buf,
        )
    log.info(f"loaded faa_registry: {len(out):,} rows")
    return {"rows": int(len(out)), "table": "faa_registry"}


def ingest_reference(log, run_id=None) -> dict:
    out_dir = ensure_releasable(log)
    path = os.path.join(out_dir, "ACFTREF.txt")
    log.info("parsing ACFTREF.txt")
    df = pd.read_csv(path, dtype=str, skipinitialspace=True, low_memory=False).fillna("")
    df.columns = [c.strip() for c in df.columns]
    c_code = _find_col(df, "code"); c_mfr = _find_col(df, "mfr"); c_model = _find_col(df, "model")
    c_tacft = _find_col(df, "type", "acft"); c_teng = _find_col(df, "type", "eng")
    c_neng = _find_col(df, "no-eng") if any("no-eng" in c.lower() for c in df.columns) else _find_col(df, "eng")
    c_seats = _find_col(df, "seat")

    def category(tacft, teng):
        if tacft in ("6", "9"):
            return "Helicopter"
        if teng in ("4", "5"):
            return "Jet"
        if teng in ("2", "3"):
            return "Turboprop"
        if teng in ("1", "7", "8"):
            return "Piston"
        if teng == "10":
            return "Electric"
        return "Other"

    rows = []
    for _, r in df.iterrows():
        code = r[c_code].strip()
        if not code:
            continue
        ta, te = r[c_tacft].strip(), r[c_teng].strip()
        rows.append((code, r[c_mfr].strip(), r[c_model].strip(), _TYPE_ACFT.get(ta, ta),
                     _TYPE_ENG.get(te, te), category(ta, te), r[c_neng].strip(), r[c_seats].strip()))
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False, header=False); buf.seek(0)
    with db.cursor(dict_rows=False) as cur:
        cur.execute("TRUNCATE aircraft_ref CASCADE")
        cur.copy_expert(
            "COPY aircraft_ref (code, manufacturer, model, aircraft_type, engine_type, category, "
            "num_engines, num_seats) FROM STDIN WITH (FORMAT csv)", buf)
    log.info(f"loaded aircraft_ref: {len(rows):,} rows")
    return {"rows": len(rows), "table": "aircraft_ref"}


def ingest_part135(log, run_id=None) -> dict:
    path = _fetch(PART135_URL, os.path.join(RAW_DIR, "135aircraft.xlsx"), log)
    log.info("parsing 135aircraft.xlsx")
    df = pd.read_excel(path, dtype=str, header=1).fillna("")   # row 0 is a title banner
    df.columns = [c.strip() for c in df.columns]
    c_name = _find_col(df, "certificate", "holder"); c_desig = _find_col(df, "designator")
    c_fsdo = _find_col(df, "district"); c_tail = _find_col(df, "registration"); c_serial = _find_col(df, "serial")
    c_model = _find_col(df, "make")
    try:
        c_part = _find_col(df, "cfr")
    except KeyError:
        c_part = None
    df[c_tail] = _norm_tail(df[c_tail])
    df = df[df[c_desig].str.strip() != ""]

    ops = df[[c_desig, c_name, c_fsdo]].drop_duplicates(subset=[c_desig])
    op_rows = [(r[c_desig].strip(), r[c_name].strip(), (df.loc[i, c_part].strip() if c_part else "135"), r[c_fsdo].strip())
               for i, r in ops.iterrows()]
    ac = df[[c_tail, c_desig, c_serial, c_model]].drop_duplicates(subset=[c_tail, c_desig])
    ac_rows = [(r[c_tail].strip(), r[c_desig].strip(), r[c_serial].strip(), r[c_model].strip())
               for _, r in ac.iterrows() if r[c_tail].strip()]
    with db.cursor(dict_rows=False) as cur:
        cur.execute("TRUNCATE part135_aircraft"); cur.execute("TRUNCATE operators CASCADE")
        cur.executemany("INSERT INTO operators (certificate_designator, operator_name, part, fsdo) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (certificate_designator) DO NOTHING", op_rows)
        cur.executemany("INSERT INTO part135_aircraft (n_number, certificate_designator, serial_number, make_model_series) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", ac_rows)
    log.info(f"loaded operators: {len(op_rows):,}, part135_aircraft: {len(ac_rows):,}")
    return {"operators": len(op_rows), "part135_aircraft": len(ac_rows)}
