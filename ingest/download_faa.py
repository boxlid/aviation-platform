"""Download the free FAA source files for the charter-fleet registry.

  1. 135aircraft.xlsx        — Part 135 operators & aircraft (tail -> certificate holder)
  2. ReleasableAircraft.zip  — full US aircraft registry (tail -> Mode S hex, owner, etc.)

The FAA *landing pages* return HTTP 403 to automated fetchers, but the file URLs
themselves download cleanly with a normal User-Agent. Files land in data/raw/.
"""
import os
import sys
import zipfile

import requests

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PART135_URL = "https://www.faa.gov/sites/faa.gov/files/about/office_org/field_offices/fsdo/135aircraft.xlsx"
RELEASABLE_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
# A plain browser UA — the file endpoints serve fine, the landing pages 403 scrapers.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fetch(url: str, dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"  GET {url}")
    with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    mb = os.path.getsize(dest) / 1e6
    print(f"  -> {dest} ({mb:.1f} MB)")
    return dest


def main() -> int:
    print("Downloading FAA Part 135 list...")
    fetch(PART135_URL, os.path.join(RAW, "135aircraft.xlsx"))

    print("Downloading FAA Releasable Aircraft Database...")
    zip_path = fetch(RELEASABLE_URL, os.path.join(RAW, "ReleasableAircraft.zip"))

    out_dir = os.path.join(RAW, "releasable")
    os.makedirs(out_dir, exist_ok=True)
    print(f"Extracting registry to {out_dir} ...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    names = sorted(os.listdir(out_dir))
    print(f"  -> {len(names)} files: {', '.join(names)}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
