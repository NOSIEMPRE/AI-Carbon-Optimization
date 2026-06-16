"""
Re-fetch power breakdown to add nuclear_fraction and cfe_fraction to existing RF parquets.

Reads existing RF parquet files for datetime lists, calls /power-breakdown/past for each
hour, then rewrites the parquet with three columns:
  renewable_fraction  — wind + solar + hydro + geothermal + biomass (excludes nuclear)
  nuclear_fraction    — nuclear share only
  cfe_fraction        — all carbon-free sources (RF + nuclear)

Usage:
    /Users/isabelwu/miniconda3/envs/thesis/bin/python src/fetch_cfe.py

Estimated time: ~3–6 hours depending on API rate limits. Safe to interrupt and resume.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ELECTRICITY_MAPS_API_KEY")
BASE_URL = "https://api.electricitymap.org/v3"
HEADERS  = {"auth-token": API_KEY}

ZONES = {
    "US-MIDA-PJM": "PJM",
    "US-NY-NYIS":  "NYISO",
    "FI":          "Finland",
    "BE":          "Belgium",
    "SG":          "Singapore",
}

CLEAN_SOURCES   = {"wind", "solar", "hydro", "geothermal", "biomass"}
NUCLEAR_SOURCES = {"nuclear"}

SLEEP_SECONDS = 0.35   # ~2.8 req/s — adjust down if API allows higher rate


def fetch_breakdown(zone: str, dt: datetime) -> dict | None:
    url    = f"{BASE_URL}/power-breakdown/past"
    params = {"zone": zone, "datetime": dt.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if resp.status_code != 200:
            return None
        entry     = resp.json()
        breakdown = entry.get("powerConsumptionBreakdown", {})
        total     = sum(v for v in breakdown.values() if v and v > 0)
        if total <= 0:
            return None
        rf      = sum(breakdown.get(s, 0) or 0 for s in CLEAN_SOURCES)   / total
        nuclear = sum(breakdown.get(s, 0) or 0 for s in NUCLEAR_SOURCES) / total
        return {
            "datetime":         dt,
            "renewable_fraction": rf,
            "nuclear_fraction": nuclear,
            "cfe_fraction":     rf + nuclear,
        }
    except Exception:
        return None


def process_zone(zone: str, label: str):
    out_path  = f"data/raw/{zone}_rf.parquet"
    ci_path   = f"data/raw/{zone}_ci.parquet"
    tmp_path  = f"data/raw/{zone}_cfe_tmp.parquet"

    # Authoritative datetime list always comes from CI parquet (never truncated)
    if not os.path.exists(ci_path):
        print(f"  {label}: no CI parquet found, skipping.")
        return
    all_dts = (
        pd.read_parquet(ci_path, columns=["datetime"])["datetime"]
        .pipe(pd.to_datetime)
        .dt.to_pydatetime()
        .tolist()
    )
    all_dts = [dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
               for dt in all_dts]

    # Load already-fetched results from tmp file (safe: never overwrites source)
    if os.path.exists(tmp_path):
        done_df   = pd.read_parquet(tmp_path)
        done_set  = set(pd.to_datetime(done_df["datetime"]).dt.to_pydatetime())
        done_rows = done_df.to_dict("records")
    else:
        done_set  = set()
        done_rows = []

    todo_dts = [dt for dt in all_dts if dt not in done_set]

    if not todo_dts:
        print(f"  {label}: CFE already complete, skipping.")
    else:
        print(f"  {label}: {len(done_rows)} done, {len(todo_dts)} remaining.")

    new_rows = []
    for dt in tqdm(todo_dts, desc=label, unit="hr"):
        row = fetch_breakdown(zone, dt)
        new_rows.append(row if row else {
            "datetime":           dt,
            "renewable_fraction": None,
            "nuclear_fraction":   None,
            "cfe_fraction":       None,
        })
        time.sleep(SLEEP_SECONDS)

        # checkpoint every 100 rows — write to tmp only, never touch source
        if len(new_rows) % 100 == 0:
            pd.DataFrame(done_rows + new_rows).to_parquet(tmp_path, index=False)

    # Final save to tmp
    all_fetched = pd.DataFrame(done_rows + new_rows).sort_values("datetime")
    all_fetched.to_parquet(tmp_path, index=False)

    # Merge fetched CFE columns back into source parquet
    # Source RF parquet may be truncated (bug from earlier run); rebuild from CI datetime list
    ci_df = pd.read_parquet(ci_path, columns=["datetime"]).set_index("datetime")
    cfe_cols = all_fetched.set_index("datetime")[
        ["renewable_fraction", "nuclear_fraction", "cfe_fraction"]
    ]
    merged = ci_df.join(cfe_cols, how="left").reset_index()
    merged.to_parquet(out_path, index=False)
    n_done = merged["cfe_fraction"].notna().sum()
    print(f"  {label}: saved {len(merged)} rows, {n_done} with CFE.")


if __name__ == "__main__":
    if not API_KEY:
        raise ValueError("ELECTRICITY_MAPS_API_KEY not set in .env")

    for zone, label in ZONES.items():
        print(f"\nProcessing {label} ({zone})...")
        process_zone(zone, label)

    print("\nDone. Run the EDA notebook to see updated CFE analysis.")
