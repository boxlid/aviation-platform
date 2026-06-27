"""Load FAA source files into Postgres and build the charter-fleet join.

Steps:
  1. apply db/schema.sql (idempotent)
  2. load operators + part135_aircraft from 135aircraft.xlsx
  3. load faa_registry from the Releasable MASTER.txt (bulk COPY)
  4. report row counts and a sample of the joined charter_fleet view

Connection: DATABASE_URL env var, default 'postgresql:///aviation'
(local Homebrew Postgres, socket auth as the current user — no password).
"""
import io
import os
import sys

import pandas as pd
import psycopg2

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
RAW = os.path.join(ROOT, "data", "raw")
SCHEMA = os.path.join(ROOT, "db", "schema.sql")
DB = os.environ.get("DATABASE_URL", "postgresql:///aviation")


def find_col(df: pd.DataFrame, *needles: str) -> str:
    """Return the first column whose lowercased name contains all needles. Resilient to FAA header drift."""
    for c in df.columns:
        lc = c.strip().lower()
        if all(n in lc for n in needles):
            return c
    raise KeyError(f"no column matching {needles} in {list(df.columns)}")


def norm_tail(s: pd.Series) -> pd.Series:
    """Normalize N-numbers to uppercase WITH a single leading 'N' (MASTER stores them without it)."""
    s = s.fillna("").astype(str).str.strip().str.upper()
    return s.where(s == "", "N" + s.str.lstrip("N"))


def load_part135(cur) -> None:
    path = os.path.join(RAW, "135aircraft.xlsx")
    print(f"Reading {path} ...")
    # Row 0 is a title/"UPDATED:" banner; the real header is on row index 1.
    df = pd.read_excel(path, dtype=str, header=1).fillna("")
    df.columns = [c.strip() for c in df.columns]

    c_name = find_col(df, "certificate", "holder")
    c_desig = find_col(df, "designator")
    c_fsdo = find_col(df, "district") if any("district" in c.lower() for c in df.columns) else find_col(df, "fsdo")
    c_tail = find_col(df, "n-number") if any("n-number" in c.lower() for c in df.columns) else find_col(df, "registration")
    c_serial = find_col(df, "serial")
    c_model = find_col(df, "make")  # "Make/Model/Series"
    # The CFR-part column is labeled "CFR" here (value '135'). Match "cfr" first;
    # a bare "part" match would wrongly hit "Part 135 Certificate Holder Name".
    c_part = None
    try:
        c_part = find_col(df, "cfr")
    except KeyError:
        for c in df.columns:
            if "part" in c.strip().lower() and c != c_name:
                c_part = c
                break

    df[c_tail] = norm_tail(df[c_tail])
    df = df[df[c_desig].str.strip() != ""]

    # operators: distinct by certificate designator
    ops = (
        df[[c_desig, c_name, c_fsdo] + ([c_part] if c_part else [])]
        .copy()
        .assign(**({} if c_part else {"__part": "135"}))
    )
    ops = ops.drop_duplicates(subset=[c_desig])
    op_rows = [
        (r[c_desig].strip(), r[c_name].strip(), (r[c_part].strip() if c_part else "135"), r[c_fsdo].strip())
        for _, r in ops.iterrows()
    ]
    cur.execute("TRUNCATE operators CASCADE")
    cur.executemany(
        "INSERT INTO operators (certificate_designator, operator_name, part, fsdo) "
        "VALUES (%s,%s,%s,%s) ON CONFLICT (certificate_designator) DO NOTHING",
        op_rows,
    )
    print(f"  operators: {len(op_rows)} rows")

    # part135_aircraft: tail -> operator
    ac = df[[c_tail, c_desig, c_serial, c_model]].drop_duplicates(subset=[c_tail, c_desig])
    ac_rows = [
        (r[c_tail].strip(), r[c_desig].strip(), r[c_serial].strip(), r[c_model].strip())
        for _, r in ac.iterrows()
        if r[c_tail].strip()
    ]
    cur.execute("TRUNCATE part135_aircraft")
    cur.executemany(
        "INSERT INTO part135_aircraft (n_number, certificate_designator, serial_number, make_model_series) "
        "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        ac_rows,
    )
    print(f"  part135_aircraft: {len(ac_rows)} rows")


def load_registry(cur) -> None:
    path = os.path.join(RAW, "releasable", "MASTER.txt")
    print(f"Reading {path} ...")
    # MASTER.txt is comma-delimited with a header row and trailing whitespace.
    df = pd.read_csv(path, dtype=str, skipinitialspace=True, low_memory=False).fillna("")
    df.columns = [c.strip() for c in df.columns]

    cols = {
        "n_number": find_col(df, "n-number"),
        "serial_number": find_col(df, "serial"),
        "mfr_mdl_code": find_col(df, "mfr", "mdl", "code"),
        "year_mfr": find_col(df, "year", "mfr"),
        "registrant_type": find_col(df, "type", "registrant"),
        "registrant_name": find_col(df, "name"),
        "city": find_col(df, "city"),
        "state": find_col(df, "state"),
        "status_code": find_col(df, "status"),
        "mode_s_code_octal": find_col(df, "mode s code") if any(c.strip().lower() == "mode s code" for c in df.columns) else find_col(df, "mode", "code"),
        "mode_s_hex": find_col(df, "mode", "hex"),
    }
    out = pd.DataFrame({k: df[v].str.strip() for k, v in cols.items()})
    out["n_number"] = norm_tail(out["n_number"])
    out["mode_s_hex"] = out["mode_s_hex"].str.upper()
    out = out.drop_duplicates(subset=["n_number"])

    buf = io.StringIO()
    out.to_csv(buf, index=False, header=False)
    buf.seek(0)
    cur.execute("TRUNCATE faa_registry")
    cur.copy_expert(
        "COPY faa_registry (n_number, serial_number, mfr_mdl_code, year_mfr, registrant_type, "
        "registrant_name, city, state, status_code, mode_s_code_octal, mode_s_hex) "
        "FROM STDIN WITH (FORMAT csv)",
        buf,
    )
    print(f"  faa_registry: {len(out)} rows")


def report(cur) -> None:
    print("\n=== Counts ===")
    for tbl in ("operators", "part135_aircraft", "faa_registry"):
        cur.execute(f"SELECT count(*) FROM {tbl}")
        print(f"  {tbl:18} {cur.fetchone()[0]:>8,}")

    cur.execute("SELECT count(*) FROM charter_fleet")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM charter_fleet WHERE mode_s_hex IS NOT NULL AND mode_s_hex <> ''")
    with_hex = cur.fetchone()[0]
    print(f"\n  charter_fleet rows: {total:,}  ({with_hex:,} joined to a Mode S hex => ADS-B-ready)")

    print("\n=== Sample: charter_fleet (operator vs registered owner) ===")
    cur.execute(
        "SELECT n_number, operator_name, make_model_series, mode_s_hex, registered_owner "
        "FROM charter_fleet WHERE mode_s_hex <> '' ORDER BY operator_name LIMIT 8"
    )
    for n, op, mdl, hexc, owner in cur.fetchall():
        print(f"  {n:8} {hexc:7} {(mdl or '')[:14]:14} op={op[:26]:26} owner={owner[:26]}")

    print("\n=== Top 10 operators by fleet size ===")
    cur.execute(
        "SELECT operator_name, count(*) n FROM charter_fleet GROUP BY operator_name ORDER BY n DESC LIMIT 10"
    )
    for op, n in cur.fetchall():
        print(f"  {n:>4}  {op}")


def main() -> int:
    print(f"Connecting: {DB}")
    conn = psycopg2.connect(DB)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            with open(SCHEMA) as f:
                cur.execute(f.read())
            load_part135(cur)
            load_registry(cur)
            report(cur)
        conn.commit()
    finally:
        conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
