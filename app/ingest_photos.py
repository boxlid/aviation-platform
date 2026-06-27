"""Aircraft photos from the Planespotters public API (free, attribution required).

Polls reasonably (rate-limited), downloads the large thumbnail for each tail, and
self-hosts it under data/photos/ (served at /photos/<tail>.jpg). Records 'no photo'
results too so we don't re-poll them every run. Planespotters requires a descriptive
User-Agent with a contact URL/email.
"""
import os
import time

import requests

from . import db
from .config import PHOTOS_DIR

UA = "SonicFlightsCRM/1.0 - (harrison@sonicflights.com)"
API = "https://api.planespotters.net/pub/photos/reg/{reg}"
H = {"User-Agent": UA, "Accept": "application/json"}


def _fetch(n_number: str):
    r = requests.get(API.format(reg=n_number), headers=H, timeout=20)
    if r.status_code != 200:
        return None  # transient (rate limit etc.) — leave unrecorded so we retry later
    photos = r.json().get("photos", [])
    if not photos:
        return {"has_photo": False}
    p = photos[0]
    large = (p.get("thumbnail_large") or {}).get("src") or (p.get("thumbnail") or {}).get("src")
    return {"has_photo": True, "photo_id": p.get("id"), "thumbnail_url": large,
            "page_link": p.get("link"), "photographer": p.get("photographer")}


def _download(url: str, dest: str):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)


def ingest_photos(log, run_id=None, limit: int = 250, delay: float = 0.5) -> dict:
    # Tails with no photo record yet, jets first (most charter-relevant).
    tails = db.query("""
      SELECT DISTINCT p.n_number, (ar.category='Jet') AS is_jet
      FROM part135_aircraft p
      LEFT JOIN faa_registry r ON r.n_number = p.n_number
      LEFT JOIN aircraft_ref ar ON ar.code = r.mfr_mdl_code
      LEFT JOIN aircraft_photos ph ON ph.n_number = p.n_number
      WHERE ph.n_number IS NULL
      ORDER BY is_jet DESC NULLS LAST, p.n_number
      LIMIT %s""", (limit,))
    processed = with_photo = errors = 0
    for row in tails:
        n = row["n_number"]
        try:
            res = _fetch(n)
            if res is None:
                errors += 1
                time.sleep(delay)
                continue
            local = None
            if res.get("has_photo") and res.get("thumbnail_url"):
                try:
                    _download(res["thumbnail_url"], os.path.join(PHOTOS_DIR, f"{n}.jpg"))
                    local = f"/photos/{n}.jpg"
                    with_photo += 1
                except Exception as e:
                    log.warning(f"{n}: image download failed: {e}")
            db.execute("""
              INSERT INTO aircraft_photos (n_number, has_photo, photo_id, thumbnail_url, page_link, photographer, local_path, fetched_at)
              VALUES (%s,%s,%s,%s,%s,%s,%s, now())
              ON CONFLICT (n_number) DO UPDATE SET has_photo=EXCLUDED.has_photo, photo_id=EXCLUDED.photo_id,
                thumbnail_url=EXCLUDED.thumbnail_url, page_link=EXCLUDED.page_link,
                photographer=EXCLUDED.photographer, local_path=EXCLUDED.local_path, fetched_at=now()""",
              (n, res.get("has_photo", False), res.get("photo_id"), res.get("thumbnail_url"),
               res.get("page_link"), res.get("photographer"), local))
            processed += 1
        except Exception as e:
            errors += 1
            log.warning(f"{n}: {e}")
        time.sleep(delay)
    log.info(f"processed {processed} tails, {with_photo} new photos, {errors} errors")
    return {"processed": processed, "photos": with_photo, "errors": errors}
