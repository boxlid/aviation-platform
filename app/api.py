"""JSON API: services control, fleet/operator search, emails, Gmail OAuth."""
from typing import Optional

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import RedirectResponse

from . import db, gmail, notifications, scheduler, weather

router = APIRouter(prefix="/api")


# ── Notifications ─────────────────────────────────────────────────────────────
@router.get("/notifications")
def list_notifications(limit: int = 50):
    return {"unread": notifications.unread_count(), "items": notifications.recent(limit)}


@router.post("/notifications/read")
def read_notifications():
    notifications.mark_all_read()
    return {"ok": True}


# ── Services ──────────────────────────────────────────────────────────────────
@router.get("/services")
def list_services():
    return db.query("SELECT * FROM services ORDER BY category, display_name")


@router.get("/services/{name}")
def get_service(name: str):
    return db.query_one("SELECT * FROM services WHERE name=%s", (name,))


@router.post("/services/{name}/run")
def run_service(name: str):
    scheduler.trigger_now(name)
    return {"ok": True, "triggered": name}


@router.post("/services/{name}/pause")
def pause_service(name: str):
    scheduler.pause_service(name)
    return {"ok": True}


@router.post("/services/{name}/resume")
def resume_service(name: str):
    scheduler.resume_service(name)
    return {"ok": True}


@router.patch("/services/{name}/interval")
def set_interval(name: str, seconds: int = Body(..., embed=True)):
    seconds = max(30, int(seconds))
    scheduler.set_interval(name, seconds)
    return {"ok": True, "interval_seconds": seconds}


@router.get("/services/{name}/runs")
def service_runs(name: str, limit: int = 25):
    return db.query("SELECT * FROM service_runs WHERE service=%s ORDER BY started_at DESC LIMIT %s", (name, limit))


@router.get("/services/{name}/logs")
def service_logs(name: str, limit: int = 200, level: Optional[str] = None):
    if level:
        return db.query("SELECT * FROM service_logs WHERE service=%s AND level=%s ORDER BY ts DESC LIMIT %s",
                        (name, level.upper(), limit))
    return db.query("SELECT * FROM service_logs WHERE service=%s ORDER BY ts DESC LIMIT %s", (name, limit))


@router.get("/logs")
def all_logs(limit: int = 300, level: Optional[str] = None, service: Optional[str] = None, q: Optional[str] = None):
    sql = "SELECT * FROM service_logs WHERE 1=1"
    params: list = []
    if level:
        sql += " AND level=%s"; params.append(level.upper())
    if service:
        sql += " AND service=%s"; params.append(service)
    if q:
        sql += " AND message ILIKE %s"; params.append(f"%{q}%")
    sql += " ORDER BY ts DESC LIMIT %s"; params.append(limit)
    return db.query(sql, params)


# ── Fleet / operators / aircraft ──────────────────────────────────────────────
_FLEET_SELECT = """
  SELECT p.n_number, o.operator_name, o.certificate_designator, o.fsdo,
         p.make_model_series, r.mode_s_hex, r.registrant_name AS registered_owner,
         r.registrant_type, r.year_mfr, r.status_code,
         ar.manufacturer, ar.model, ar.category, ar.aircraft_type, ar.engine_type, ar.num_seats
  FROM part135_aircraft p
  JOIN operators o USING (certificate_designator)
  LEFT JOIN faa_registry r ON r.n_number = p.n_number
  LEFT JOIN aircraft_ref ar ON ar.code = r.mfr_mdl_code
"""


@router.get("/fleet")
def fleet(q: Optional[str] = None, category: Optional[str] = None, operator: Optional[str] = None,
          adsb_ready: bool = False, limit: int = 100, offset: int = 0):
    sql = _FLEET_SELECT + " WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (p.n_number ILIKE %s OR o.operator_name ILIKE %s OR p.make_model_series ILIKE %s OR ar.manufacturer ILIKE %s)"
        like = f"%{q}%"; params += [like, like, like, like]
    if category:
        sql += " AND ar.category = %s"; params.append(category)
    if operator:
        sql += " AND o.operator_name = %s"; params.append(operator)
    if adsb_ready:
        sql += " AND r.mode_s_hex IS NOT NULL AND r.mode_s_hex <> ''"
    sql += " ORDER BY o.operator_name, p.n_number LIMIT %s OFFSET %s"
    params += [min(limit, 500), offset]
    return db.query(sql, params)


@router.get("/aircraft/{n_number}")
def aircraft(n_number: str):
    n = n_number.upper()
    registry = db.query_one("""
      SELECT r.n_number, r.serial_number, r.mfr_mdl_code, r.year_mfr, r.registrant_type,
             r.registrant_name, r.city, r.state, r.status_code, r.mode_s_code_octal, r.mode_s_hex,
             ar.manufacturer, ar.model, ar.aircraft_type, ar.engine_type, ar.category,
             ar.num_engines, ar.num_seats
      FROM faa_registry r LEFT JOIN aircraft_ref ar ON ar.code = r.mfr_mdl_code
      WHERE r.n_number = %s""", (n,))
    operators = db.query("""
      SELECT p.certificate_designator, o.operator_name, o.fsdo, p.serial_number, p.make_model_series
      FROM part135_aircraft p JOIN operators o USING (certificate_designator)
      WHERE p.n_number = %s ORDER BY o.operator_name""", (n,))
    if not registry and not operators:
        return None
    return {"n_number": n, "registry": registry, "operators": operators}


_OPERATOR_AGG = """
  SELECT o.certificate_designator, o.operator_name, o.fsdo, count(p.n_number) AS fleet_size,
         count(*) FILTER (WHERE ar.category='Jet') AS jets,
         count(*) FILTER (WHERE ar.category='Turboprop') AS turboprops,
         count(*) FILTER (WHERE ar.category='Helicopter') AS helicopters
  FROM operators o
  LEFT JOIN part135_aircraft p USING (certificate_designator)
  LEFT JOIN faa_registry r ON r.n_number = p.n_number
  LEFT JOIN aircraft_ref ar ON ar.code = r.mfr_mdl_code
"""


@router.get("/operators/{designator}")
def operator_detail(designator: str):
    rows = db.query(_OPERATOR_AGG + " WHERE o.certificate_designator=%s GROUP BY 1,2,3", (designator,))
    if not rows:
        return None
    fleet = db.query(_FLEET_SELECT + " WHERE o.certificate_designator=%s ORDER BY ar.category NULLS LAST, p.n_number",
                     (designator,))
    return {"operator": rows[0], "fleet": fleet}


@router.get("/fsdo")
def fsdo_detail(name: str):
    operators = db.query(_OPERATOR_AGG + " WHERE o.fsdo=%s GROUP BY 1,2,3 ORDER BY fleet_size DESC", (name,))
    totals = db.query_one(
        "SELECT count(DISTINCT o.certificate_designator) ops, count(p.n_number) aircraft "
        "FROM operators o LEFT JOIN part135_aircraft p USING (certificate_designator) WHERE o.fsdo=%s", (name,))
    return {"fsdo": name, "totals": totals, "operators": operators}


@router.get("/operators")
def operators(q: Optional[str] = None, limit: int = 100):
    sql = _OPERATOR_AGG
    params: list = []
    if q:
        sql += " WHERE o.operator_name ILIKE %s"; params.append(f"%{q}%")
    sql += " GROUP BY o.certificate_designator, o.operator_name, o.fsdo ORDER BY fleet_size DESC LIMIT %s"
    params.append(limit)
    return db.query(sql, params)


@router.get("/routes")
def routes(q: Optional[str] = None, origin: Optional[str] = None, dest: Optional[str] = None, limit: int = 300):
    sql = """
      SELECT unique_carrier, carrier_name, origin, split_part(origin_city, ',', 1) AS origin_city, origin_state,
             dest, split_part(dest_city, ',', 1) AS dest_city, dest_state,
             sum(departures) AS departures, sum(passengers) AS passengers,
             round(max(distance)) AS distance, count(DISTINCT (year, month)) AS months
      FROM charter_routes WHERE 1=1
    """
    params: list = []
    if q:
        sql += " AND carrier_name ILIKE %s"; params.append(f"%{q}%")
    if origin:
        sql += " AND origin = %s"; params.append(origin.upper())
    if dest:
        sql += " AND dest = %s"; params.append(dest.upper())
    sql += (" GROUP BY unique_carrier, carrier_name, origin, origin_city, origin_state, dest, dest_city, dest_state "
            " HAVING sum(departures) > 0 ORDER BY departures DESC LIMIT %s")
    params.append(min(limit, 800))
    return db.query(sql, params)


@router.get("/route")
def route_detail(carrier: str, origin: str, dest: str):
    args = (carrier, origin.upper(), dest.upper())
    where = "WHERE unique_carrier=%s AND origin=%s AND dest=%s"
    summary = db.query_one(
        f"SELECT carrier_name, split_part(origin_city, ',', 1) AS origin_city, origin_state, "
        f"split_part(dest_city, ',', 1) AS dest_city, dest_state, "
        f"sum(departures) departures, sum(passengers) passengers, sum(seats) seats, "
        f"round(max(distance)) distance, count(DISTINCT (year,month)) months "
        f"FROM charter_routes {where} GROUP BY carrier_name, origin_city, origin_state, dest_city, dest_state", args)
    if not summary:
        return None
    monthly = db.query(
        f"SELECT year, month, sum(departures) departures, sum(seats) seats, sum(passengers) passengers "
        f"FROM charter_routes {where} GROUP BY year, month ORDER BY year, month", args)
    aircraft = db.query(
        f"SELECT aircraft_type, atr.description AS aircraft_name, "
        f"sum(departures) departures, sum(passengers) passengers "
        f"FROM charter_routes LEFT JOIN aircraft_type_ref atr ON atr.code = lpad(aircraft_type, 3, '0') "
        f"{where} GROUP BY aircraft_type, atr.description ORDER BY departures DESC", args)

    def airport(code):
        return db.query_one("SELECT ident, name FROM airports WHERE iata_code=%s OR local_code=%s "
                            "ORDER BY (type='large_airport') DESC LIMIT 1", (code, code))
    return {"carrier": carrier, "summary": summary, "origin": origin.upper(), "dest": dest.upper(),
            "origin_airport": airport(origin.upper()), "dest_airport": airport(dest.upper()),
            "monthly": monthly, "aircraft": aircraft}


@router.get("/airports")
def airports(q: Optional[str] = None, country: Optional[str] = None, type: Optional[str] = None,
             min_runway: int = 0, limit: int = 200):
    sql = "SELECT * FROM airport_capability WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (name ILIKE %s OR municipality ILIKE %s OR iata_code ILIKE %s OR ident ILIKE %s)"
        like = f"%{q}%"; params += [like, like, like, like]
    if country:
        sql += " AND iso_country = %s"; params.append(country.upper())
    if type:
        sql += " AND type = %s"; params.append(type)
    else:
        # Default to landplane airports — seaplane "runways" are lake lengths, heliports have none.
        sql += " AND type NOT IN ('seaplane_base', 'heliport', 'balloonport', 'closed')"
    if min_runway:
        sql += " AND longest_runway_ft >= %s"; params.append(min_runway)
    sql += " ORDER BY longest_runway_ft DESC NULLS LAST LIMIT %s"
    params.append(min(limit, 500))
    return db.query(sql, params)


@router.get("/airports/{ident}")
def airport_detail(ident: str):
    ap = db.query_one("SELECT * FROM airports WHERE ident=%s", (ident,))
    if not ap:
        return None
    cap = db.query_one("SELECT longest_runway_ft, runway_count FROM airport_capability WHERE ident=%s", (ident,))
    runways = db.query(
        "SELECT le_ident, he_ident, length_ft, width_ft, surface, lighted, closed "
        "FROM runways WHERE airport_ident=%s ORDER BY length_ft DESC NULLS LAST", (ident,))
    # FAA airport detail (US): owner/manager contacts, joined on FAA location id = local_code.
    faa = None
    if ap.get("local_code"):
        faa = db.query_one(
            "SELECT owner_name, owner_phone, manager_name, manager_phone FROM faa_airport_detail WHERE location_id=%s",
            (ap["local_code"],))
    return {"airport": ap, "capability": cap, "runways": runways, "faa": faa}


@router.get("/airports/{ident}/weather")
def airport_weather(ident: str):
    ap = db.query_one("SELECT icao_code, ident, latitude_deg, longitude_deg FROM airports WHERE ident=%s", (ident,))
    if not ap:
        return None
    icao = (ap.get("icao_code") or ap["ident"]).strip()
    return weather.report(icao, ap.get("latitude_deg"), ap.get("longitude_deg"))


@router.get("/stats")
def stats():
    one = db.query_one
    out = {
        "operators": one("SELECT count(*) c FROM operators")["c"],
        "aircraft": one("SELECT count(*) c FROM part135_aircraft")["c"],
        "registry": one("SELECT count(*) c FROM faa_registry")["c"],
        "reference": one("SELECT count(*) c FROM aircraft_ref")["c"],
        "emails": one("SELECT count(*) c FROM emails")["c"],
        "adsb_ready": one("SELECT count(*) c FROM charter_fleet WHERE mode_s_hex IS NOT NULL AND mode_s_hex<>''")["c"],
        "charter_segments": one("SELECT count(*) c FROM charter_routes")["c"],
        "airports": one("SELECT count(*) c FROM airports")["c"],
    }
    out["by_category"] = db.query("""
        SELECT COALESCE(ar.category,'Unknown') category, count(*) n
        FROM part135_aircraft p LEFT JOIN faa_registry r ON r.n_number=p.n_number
        LEFT JOIN aircraft_ref ar ON ar.code=r.mfr_mdl_code
        GROUP BY 1 ORDER BY n DESC""")
    out["top_operators"] = db.query("""
        SELECT o.operator_name, count(*) n FROM part135_aircraft p
        JOIN operators o USING (certificate_designator) GROUP BY 1 ORDER BY n DESC LIMIT 10""")
    out["services"] = db.query("SELECT name, display_name, status, enabled, last_finished_at FROM services ORDER BY display_name")
    return out


# ── Emails + Gmail ────────────────────────────────────────────────────────────
@router.get("/emails")
def emails(q: Optional[str] = None, limit: int = 50):
    return gmail.search(q, limit)


@router.get("/gmail/status")
def gmail_status():
    return {"has_credentials": gmail.has_credentials(), "connected": gmail.is_connected()}


@router.get("/gmail/connect")
def gmail_connect():
    try:
        return RedirectResponse(gmail.auth_url())
    except Exception as e:
        return RedirectResponse(f"/emails?error={e}")


@router.get("/gmail/callback")
def gmail_callback(request: Request):
    try:
        gmail.handle_callback(str(request.url))
        return RedirectResponse("/emails?connected=1")
    except Exception as e:
        return RedirectResponse(f"/emails?error={e}")


@router.post("/gmail/disconnect")
def gmail_disconnect():
    gmail.disconnect()
    return {"ok": True}
