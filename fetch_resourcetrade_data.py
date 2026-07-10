"""
Automates pulling commodity-level Metals & Minerals trade data from
resourcetrade.earth for Philippines, Thailand, and Malaysia
(exports-to-world and imports-from-world), across all years 2000-2024,
and merges it all into one combined CSV.

"Metals and minerals" is category id 5 on the site, but that id is an
aggregate whose export file only breaks resources down to 6 subcategory
names (e.g. "Precious metals"). To get actual commodities (Gold,
Platinum, Iron ores and concentrates, ...) each subcategory id must be
queried on its own - see CATEGORIES below.

HOW IT WORKS (reverse-engineered from the site's own network calls):
  1. GET  .../downloads?year=Y&exporter=CODE&category=ID&units=weight
       -> kicks off an async export job, returns {"job": "<id>"}
     (use importer=CODE instead of exporter=CODE for the reverse flow)
  2. GET  .../downloads/<id>
       -> poll until {"status": "completed", "url": "<s3 link>"}
  3. Download the .xlsx from the returned S3 url. Its "Trades" sheet
     holds one row per (exporter, importer, commodity, year); the
     "year" query param returns a trailing 5-year window ending at
     that year, so 5 checkpoint years tile 2000-2024 without gaps.

Run with:
    pip install requests pandas openpyxl
    python fetch_resourcetrade_data.py

Output:
    ./raw_downloads/*.xlsx          (every individual file, cached so re-runs are fast)
    ./resourcetrade_metals_2000_2024.csv   (final combined long-format table)
"""

import os
import time
import json
import requests
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

BASE = "https://api.resourcetrade.earth/api/rt/2.7/downloads"

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://resourcetrade.earth/",
    "origin": "https://resourcetrade.earth",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
}

# UN M49 country codes
COUNTRIES = {
    "Philippines": 608,
    "Thailand": 764,
    "Malaysia": 458,
}

# Metals and Minerals (top-level category 5) is an aggregate id whose
# Trades sheet only breaks resources down to these 6 subcategory names.
# To get real commodity-level detail (Gold, Platinum, Iron ore, etc.) each
# subcategory must be queried separately.
CATEGORIES = {
    34: "Industrial minerals",
    35: "Iron and steel",
    37: "Non-ferrous metals",
    38: "Precious metals",
    39: "Specialty metals",
    160: "Metals not specified",
}
UNITS = "weight"       # also supports "value" if you want USD instead of tonnes

# Each request's "year" param returns a *trailing 5-year window* ending at
# that year (confirmed: year=2004 -> rows for 2000-2004, year=2023 -> rows
# for 2019-2023). These 5 checkpoints tile 2000-2024 with no gaps/overlap,
# so only 5 requests are needed per country/direction/category instead of 25.
YEAR_CHECKPOINTS = [2004, 2009, 2014, 2019, 2024]

RAW_DIR = "raw_downloads"
os.makedirs(RAW_DIR, exist_ok=True)

POLL_INTERVAL = 2       # seconds between status checks
POLL_TIMEOUT = 60       # give up after this many seconds per file
REQUEST_PAUSE = 1.5     # be polite between requests, avoid rate-limiting


# ---------------------------------------------------------------------------
# CORE FUNCTIONS
# ---------------------------------------------------------------------------

def create_job(year, country_code, direction, category):
    """direction: 'exporter' or 'importer'"""
    params = {
        "year": year,
        direction: country_code,
        "category": category,
        "units": UNITS,
        "autozoom": 1,
    }
    r = requests.get(BASE, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["job"]


def poll_job(job_id):
    url = f"{BASE}/{job_id}"
    waited = 0
    while waited < POLL_TIMEOUT:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "completed":
            return data["url"], data["filename"]
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    raise TimeoutError(f"Job {job_id} did not complete in time")


def download_file(file_url, filename):
    local_path = os.path.join(RAW_DIR, filename)
    if os.path.exists(local_path):
        return local_path  # already cached from a previous run
    r = requests.get(file_url, timeout=60)
    r.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(r.content)
    return local_path


def fetch_one(year, country_code, direction, category):
    job_id = create_job(year, country_code, direction, category)
    file_url, filename = poll_job(job_id)
    return download_file(file_url, filename)


def parse_xlsx(local_path, country_name, direction, category_name):
    """
    Reads the "Trades" sheet, which carries commodity-level rows
    (e.g. Gold, Iron ores and concentrates) rather than the
    category-aggregated rows found on other sheets. Each row already
    carries its own correct "Year" column (the file spans a 5-year
    window), so we don't re-tag it with the checkpoint year.
    """
    df = pd.read_excel(local_path, sheet_name="Trades")

    df["_country"] = country_name
    df["_direction"] = "export_to_world" if direction == "exporter" else "import_from_world"
    df["_category"] = category_name
    return df


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------

def main():
    all_frames = []
    errors = []

    total = len(COUNTRIES) * 2 * len(CATEGORIES) * len(list(YEAR_CHECKPOINTS))
    done = 0

    for name, code in COUNTRIES.items():
        for direction in ("exporter", "importer"):
            for cat_id, cat_name in CATEGORIES.items():
                for year in YEAR_CHECKPOINTS:
                    done += 1
                    label = f"[{done}/{total}] {name} {year} ({direction}, {cat_name})"
                    try:
                        path = fetch_one(year, code, direction, cat_id)
                        df = parse_xlsx(path, name, direction, cat_name)
                        all_frames.append(df)
                        print(f"{label}: OK ({len(df)} rows)")
                    except Exception as e:
                        print(f"{label}: FAILED - {e}")
                        errors.append(label)
                    time.sleep(REQUEST_PAUSE)

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        out_path = "resourcetrade_metals_2000_2024.csv"
        combined.to_csv(out_path, index=False)
        print(f"\nSaved combined dataset -> {out_path} ({len(combined)} rows)")

        exports = combined[combined["_direction"] == "export_to_world"]
        imports = combined[combined["_direction"] == "import_from_world"]
        exports.to_csv("resourcetrade_metals_2000_2024_exports.csv", index=False)
        imports.to_csv("resourcetrade_metals_2000_2024_imports.csv", index=False)
        print(f"Saved exports -> resourcetrade_metals_2000_2024_exports.csv ({len(exports)} rows)")
        print(f"Saved imports -> resourcetrade_metals_2000_2024_imports.csv ({len(imports)} rows)")

        xlsx_path = "resourcetrade_metals_2000_2024.xlsx"
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            for name in COUNTRIES:
                for direction, label in (("export_to_world", "export"), ("import_from_world", "import")):
                    sheet = combined[(combined["_country"] == name) & (combined["_direction"] == direction)]
                    sheet.to_excel(writer, sheet_name=f"{name} ({label})", index=False)
        print(f"Saved workbook -> {xlsx_path} (one sheet per country x direction)")
    else:
        print("\nNo data was successfully retrieved.")

    if errors:
        print("\nThe following combinations failed and may need re-running:")
        for e in errors:
            print(" -", e)


if __name__ == "__main__":
    main()
