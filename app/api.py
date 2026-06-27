"""JSON API: services control, fleet/operator search, emails, Gmail OAuth."""
from typing import Optional

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import RedirectResponse

from . import db, gmail, notifications, scheduler

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
    rows = db.query(_FLEET_SELECT + " WHERE p.n_number = %s", (n_number.upper(),))
    return rows[0] if rows else None


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
def routes(q: Optional[str] = None, origin: Optional[str] = None, dest: Optional[str] = None, limit: int = 200):
    sql = """
      SELECT carrier_name, origin, origin_city, dest, dest_city,
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
    sql += (" GROUP BY carrier_name, origin, origin_city, dest, dest_city "
            " HAVING sum(departures) > 0 ORDER BY departures DESC LIMIT %s")
    params.append(min(limit, 500))
    return db.query(sql, params)


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
