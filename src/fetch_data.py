"""
Fetch hourly carbon intensity (CI) and power breakdown (RF) data
from the ElectricityMaps API for five target regions.

Usage:
    conda run -n thesis python src/fetch_data.py

Output:
    data/raw/{zone}_ci.parquet   — carbon intensity (gCO2eq/kWh)
    data/raw/{zone}_rf.parquet   — renewable fraction (%)
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

API_KEY   = os.getenv("ELECTRICITY_MAPS_API_KEY")
BASE_URL  = "https://api.electricitymap.org/v3"
HEADERS   = {"auth-token": API_KEY}

ZONES = {
    "US-MIDA-PJM": "PJM",
    "US-NY-NYIS":  "NYISO",
    "FI":          "Finland",
    "BE":          "Belgium",
    "SG":          "Singapore",
}

START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE   = datetime(2025, 12, 31, tzinfo=timezone.utc)

RENEWABLE_SOURCES = {"wind", "solar", "hydro", "geothermal", "biomass", "nuclear"}
CLEAN_SOURCES     = {"wind", "solar", "hydro", "geothermal", "biomass"}   # excludes nuclear for RF


def fetch_carbon_intensity(zone: str, dt: datetime) -> dict | None:
    """Fetch carbon intensity for a zone at a specific UTC datetime."""
    url = f"{BASE_URL}/carbon-intensity/history"
    resp = requests.get(url, headers=HEADERS, params={"zone": zone}, timeout=30)
    if resp.status_code == 200:
        data = resp.json().get("history", [])
        # find the entry closest to dt
        for entry in data:
            entry_dt = datetime.fromisoformat(entry["datetime"].replace("Z", "+00:00"))
            if entry_dt.date() == dt.date() and entry_dt.hour == dt.hour:
                return {"datetime": entry_dt, "carbon_intensity": entry.get("carbonIntensity")}
    return None


def fetch_power_breakdown(zone: str, dt: datetime) -> dict | None:
    """Fetch power breakdown and compute renewable fraction for a zone at a specific UTC datetime."""
    url = f"{BASE_URL}/power-breakdown/history"
    resp = requests.get(url, headers=HEADERS, params={"zone": zone}, timeout=30)
    if resp.status_code == 200:
        data = resp.json().get("history", [])
        for entry in data:
            entry_dt = datetime.fromisoformat(entry["datetime"].replace("Z", "+00:00"))
            if entry_dt.date() == dt.date() and entry_dt.hour == dt.hour:
                breakdown = entry.get("powerConsumptionBreakdown", {})
                total = sum(v for v in breakdown.values() if v and v > 0)
                if total > 0:
                    renewable = sum(breakdown.get(s, 0) or 0 for s in CLEAN_SOURCES)
                    rf = renewable / total
                else:
                    rf = None
                return {"datetime": entry_dt, "renewable_fraction": rf}
    return None


def fetch_past_carbon_intensity(zone: str, dt: datetime) -> dict | None:
    """Fetch a single historical CI data point using the /past endpoint."""
    url = f"{BASE_URL}/carbon-intensity/past"
    params = {"zone": zone, "datetime": dt.strftime("%Y-%m-%dT%H:%M:%SZ")}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    if resp.status_code == 200:
        entry = resp.json()
        return {
            "datetime": datetime.fromisoformat(entry["datetime"].replace("Z", "+00:00")),
            "carbon_intensity": entry.get("carbonIntensity"),
        }
    return None


def fetch_past_power_breakdown(zone: str, dt: datetime) -> dict | None:
    """Fetch a single historical power breakdown and compute RF using the /past endpoint."""
    url = f"{BASE_URL}/power-breakdown/past"
    params = {"zone": zone, "datetime": dt.strftime("%Y-%m-%dT%H:%M:%SZ")}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    if resp.status_code == 200:
        entry = resp.json()
        breakdown = entry.get("powerConsumptionBreakdown", {})
        total = sum(v for v in breakdown.values() if v and v > 0)
        rf = None
        if total > 0:
            renewable = sum(breakdown.get(s, 0) or 0 for s in CLEAN_SOURCES)
            rf = renewable / total
        return {
            "datetime": datetime.fromisoformat(entry["datetime"].replace("Z", "+00:00")),
            "renewable_fraction": rf,
        }
    return None


def generate_hourly_range(start: datetime, end: datetime):
    current = start
    while current <= end:
        yield current
        current += timedelta(hours=1)


def fetch_zone(zone: str, label: str):
    """Fetch all hourly CI and RF data for a zone and save to parquet."""
    out_ci = f"data/raw/{zone}_ci.parquet"
    out_rf = f"data/raw/{zone}_rf.parquet"

    # resume from last saved point if file exists
    if os.path.exists(out_ci):
        existing = pd.read_parquet(out_ci)
        last_dt = pd.to_datetime(existing["datetime"]).max().to_pydatetime().replace(tzinfo=timezone.utc)
        start = last_dt + timedelta(hours=1)
        ci_records = existing.to_dict("records")
        print(f"  Resuming {label} CI from {start.date()}")
    else:
        start = START_DATE
        ci_records = []

    if os.path.exists(out_rf):
        existing_rf = pd.read_parquet(out_rf)
        rf_records = existing_rf.to_dict("records")
    else:
        rf_records = []

    hours = list(generate_hourly_range(start, END_DATE))
    if not hours:
        print(f"  {label}: already up to date.")
        return

    for dt in tqdm(hours, desc=f"{label} CI+RF", unit="hr"):
        ci = fetch_past_carbon_intensity(zone, dt)
        if ci:
            ci_records.append(ci)

        rf = fetch_past_power_breakdown(zone, dt)
        if rf:
            rf_records.append(rf)

        time.sleep(0.5)   # ~2 req/sec to stay within rate limits

        # save checkpoint every 48 hours of data
        if len(ci_records) % 48 == 0 and ci_records:
            pd.DataFrame(ci_records).to_parquet(out_ci, index=False)
            pd.DataFrame(rf_records).to_parquet(out_rf, index=False)

    pd.DataFrame(ci_records).to_parquet(out_ci, index=False)
    pd.DataFrame(rf_records).to_parquet(out_rf, index=False)
    print(f"  {label}: saved {len(ci_records)} CI rows, {len(rf_records)} RF rows.")


if __name__ == "__main__":
    if not API_KEY:
        raise ValueError("ELECTRICITY_MAPS_API_KEY not set in .env")

    os.makedirs("data/raw", exist_ok=True)

    for zone, label in ZONES.items():
        print(f"\nFetching {label} ({zone})...")
        fetch_zone(zone, label)

    print("\nAll zones done.")
