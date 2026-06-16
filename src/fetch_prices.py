"""
fetch_prices.py — Fetch historical day-ahead electricity prices for all 5 zones.

Sources and authentication
--------------------------
Finland (FI), Belgium (BE)  ENTSO-E Transparency Platform
                             Requires: ENTSOE_API_KEY in .env
                             Free registration: https://transparency.entsoe.eu
                             → My Account Settings > Web API Security Token

NYISO (US-NY-NYIS)          NYISO public monthly ZIP files — NO auth required
                             NYC zone (N.Y.C.) day-ahead LBMP, $/MWh

PJM (US-MIDA-PJM)           PJM API v1 — requires free subscription key
                             Requires: PJM_API_KEY in .env
                             Free registration: https://api.pjm.com/group
                             → Subscribe to "PJM Data Miner"
                             Western Hub LMP, $/MWh

Singapore (SG)               EMC Singapore — manual download required
                             1. Go to https://www.emcsg.com/marketdata/priceinformation
                             2. Download USEP historical data (Excel) for 2024–2025
                             3. Save as  data/raw/SG_price_raw.xlsx
                             This script will parse it automatically on next run.

Output
------
data/raw/{zone}_price.parquet
  columns: datetime (UTC, hourly), price_mwh (local currency), currency

Usage
-----
    python src/fetch_prices.py
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from dateutil import tz
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

ENTSOE_API_KEY = os.getenv("ENTSOE_API_KEY")
PJM_API_KEY    = os.getenv("PJM_API_KEY")

# Date range to match CI/CFE data
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE   = datetime(2026, 1, 1, tzinfo=timezone.utc)   # exclusive

EASTERN_TZ  = tz.gettz("America/New_York")
SINGAPORE_TZ = tz.gettz("Asia/Singapore")

DATA_DIR = "data/raw"


# ── ENTSO-E: Finland and Belgium ──────────────────────────────────────────────

ENTSOE_AREAS = {
    "FI": "10YFI-1--------U",
    "BE": "10YBE----------2",
}

def fetch_entsoe(zone: str) -> pd.DataFrame:
    """Fetch day-ahead prices from ENTSO-E for Finland or Belgium."""
    if not ENTSOE_API_KEY:
        raise ValueError(
            "ENTSOE_API_KEY not set in .env\n"
            "Register at https://transparency.entsoe.eu → Settings > Web API Security Token"
        )
    try:
        from entsoe import EntsoePandasClient
    except ImportError:
        raise ImportError("Run: pip install entsoe-py")

    import pandas as pd

    client   = EntsoePandasClient(api_key=ENTSOE_API_KEY)
    area     = ENTSOE_AREAS[zone]

    # Request in 6-month chunks to avoid timeout
    chunks = []
    cursor = START_DATE
    step   = timedelta(days=180)

    while cursor < END_DATE:
        chunk_end = min(cursor + step, END_DATE)
        start_ts  = pd.Timestamp(cursor)
        end_ts    = pd.Timestamp(chunk_end)

        print(f"    Fetching {zone}: {cursor.date()} → {chunk_end.date()} ...")
        try:
            series = client.query_day_ahead_prices(area, start=start_ts, end=end_ts)
            df = series.reset_index()
            df.columns = ["datetime", "price_mwh"]
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
            chunks.append(df)
        except Exception as e:
            print(f"    Warning: chunk failed ({e}). Skipping.")

        cursor = chunk_end
        time.sleep(1.0)

    if not chunks:
        raise RuntimeError(f"No data retrieved for {zone}")

    result = (
        pd.concat(chunks, ignore_index=True)
        .drop_duplicates("datetime")
        .sort_values("datetime")
        .assign(currency="EUR")
    )
    return result[["datetime", "price_mwh", "currency"]]


# ── PJM API v1: Western Hub LMP ───────────────────────────────────────────────
# Register free at https://api.pjm.com/group → Subscribe to "PJM Data Miner"

PJM_PNODE_ID   = 33092371    # PJM Western Hub
PJM_CHUNK_DAYS = 30

def fetch_pjm() -> pd.DataFrame:
    """Fetch PJM day-ahead Western Hub LMP via PJM API v1."""
    if not PJM_API_KEY:
        raise ValueError(
            "PJM_API_KEY not set in .env\n"
            "Register free at https://api.pjm.com/group → Subscribe to 'PJM Data Miner'"
        )

    base_url = "https://api.pjm.com/api/v1/da_hrl_lmps"
    headers  = {"Ocp-Apim-Subscription-Key": PJM_API_KEY}
    rows     = []
    cursor   = START_DATE

    pbar = tqdm(total=(END_DATE - START_DATE).days, desc="PJM", unit="day")
    while cursor < END_DATE:
        chunk_end = min(cursor + timedelta(days=PJM_CHUNK_DAYS), END_DATE)
        start_et  = cursor.astimezone(EASTERN_TZ).strftime("%Y-%m-%d %H:%M")
        end_et    = chunk_end.astimezone(EASTERN_TZ).strftime("%Y-%m-%d %H:%M")

        params = {
            "startRow":               1,
            "numRows":                5000,
            "datetime_beginning_ept": start_et,
            "datetime_ending_ept":    end_et,
            "pnode_id":               PJM_PNODE_ID,
            "fields":                 "datetime_beginning_utc,total_lmp_da",
        }
        try:
            resp = requests.get(base_url, headers=headers, params=params, timeout=60)
            resp.raise_for_status()
            for rec in resp.json():
                dt_str = rec.get("datetime_beginning_utc")
                price  = rec.get("total_lmp_da")
                if dt_str and price is not None:
                    rows.append({
                        "datetime":  pd.Timestamp(dt_str, tz="UTC"),
                        "price_mwh": float(price),
                        "currency":  "USD",
                    })
        except Exception as e:
            print(f"\n    PJM chunk {start_et} failed: {e}")

        pbar.update(PJM_CHUNK_DAYS)
        cursor = chunk_end
        time.sleep(0.3)

    pbar.close()
    if not rows:
        raise RuntimeError("No PJM data retrieved.")

    return (
        pd.DataFrame(rows)
        .drop_duplicates("datetime")
        .sort_values("datetime")
        .reset_index(drop=True)
    )


# ── NYISO: NYC zone day-ahead LBMP via monthly ZIP files ──────────────────────
# Confirmed working: https://mis.nyiso.com/public/csv/damlbmp/{YYYYMM01}damlbmp_zone_csv.zip
# Each ZIP contains all daily CSVs for that month.

NYISO_ZONE = "N.Y.C."
NYISO_BASE = "https://mis.nyiso.com/public/csv/damlbmp"

def fetch_nyiso() -> pd.DataFrame:
    """Fetch NYISO day-ahead LBMP for NYC zone via monthly ZIP files (no auth)."""
    import zipfile, io as _io

    rows   = []
    cursor = START_DATE.replace(day=1)
    months = []
    while cursor < END_DATE:
        months.append(cursor)
        # Advance to next month
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    for month_start in tqdm(months, desc="NYISO", unit="month"):
        date_str = month_start.strftime("%Y%m01")
        url = f"{NYISO_BASE}/{date_str}damlbmp_zone_csv.zip"

        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200:
                print(f"\n    NYISO {date_str}: HTTP {resp.status_code}, skipping.")
                continue

            z = zipfile.ZipFile(_io.BytesIO(resp.content))
            for fname in z.namelist():
                df = pd.read_csv(z.open(fname))
                zone_df = df[df["Name"].str.strip() == NYISO_ZONE]
                if zone_df.empty:
                    # Fall back to system average if zone not found
                    zone_df = df.groupby("Time Stamp", as_index=False)[
                        "LBMP ($/MWHr)"
                    ].mean()

                for _, row in zone_df.iterrows():
                    try:
                        ts_et  = datetime.strptime(str(row["Time Stamp"]), "%m/%d/%Y %H:%M")
                        ts_utc = ts_et.replace(tzinfo=EASTERN_TZ).astimezone(timezone.utc)
                        rows.append({
                            "datetime":  pd.Timestamp(ts_utc),
                            "price_mwh": float(row["LBMP ($/MWHr)"]),
                            "currency":  "USD",
                        })
                    except Exception:
                        pass
        except Exception as e:
            print(f"\n    NYISO {date_str} failed: {e}")

        time.sleep(0.3)

    if not rows:
        raise RuntimeError("No NYISO data retrieved.")

    return (
        pd.DataFrame(rows)
        .drop_duplicates("datetime")
        .sort_values("datetime")
        .reset_index(drop=True)
    )


# ── Singapore EMC: manual download + parser ───────────────────────────────────

SG_RAW_PATH = "data/raw/SG_price_raw.xlsx"

def parse_singapore() -> pd.DataFrame:
    """
    Parse manually downloaded EMC USEP Excel file.

    Download instructions:
      1. Go to https://www.emcsg.com/marketdata/priceinformation
      2. Select year range 2024–2025, download as Excel
      3. Save to data/raw/SG_price_raw.xlsx

    Expected columns in the Excel: Date, Period (1–48), USEP ($/MWh)
    Periods are half-hourly (SGT); this function aggregates to hourly UTC.
    """
    if not os.path.exists(SG_RAW_PATH):
        print(f"\n  Singapore: {SG_RAW_PATH} not found.")
        print("  Manual download required:")
        print("    1. https://www.emcsg.com/marketdata/priceinformation")
        print("    2. Download USEP historical data (Excel) for 2024–2025")
        print(f"    3. Save as {SG_RAW_PATH}")
        return None

    df = pd.read_excel(SG_RAW_PATH)

    # Try to auto-detect the relevant columns
    date_col  = next((c for c in df.columns if "date" in c.lower()), None)
    period_col = next((c for c in df.columns if "period" in c.lower()), None)
    price_col = next((c for c in df.columns if "usep" in c.lower() or "price" in c.lower()), None)

    if not all([date_col, price_col]):
        print(f"  Singapore: could not auto-detect columns. Found: {list(df.columns)}")
        return None

    rows = []
    for _, row in df.iterrows():
        try:
            date  = pd.Timestamp(row[date_col])
            price = float(row[price_col])
            period = int(row[period_col]) if period_col else 1
            # Each period is 30 minutes; period 1 = 00:00–00:30 SGT
            minutes_sgt = (period - 1) * 30
            dt_sgt = date.replace(hour=0, minute=0, second=0) + timedelta(minutes=minutes_sgt)
            dt_sgt = dt_sgt.replace(tzinfo=SINGAPORE_TZ)
            dt_utc = dt_sgt.astimezone(timezone.utc)
            rows.append({
                "datetime":  pd.Timestamp(dt_utc),
                "price_mwh": price,
                "currency":  "SGD",
            })
        except Exception:
            continue

    if not rows:
        return None

    # Resample half-hourly → hourly mean
    df_out = pd.DataFrame(rows)
    df_out["datetime"] = df_out["datetime"].dt.floor("h")
    df_out = (
        df_out.groupby("datetime", as_index=False)["price_mwh"]
        .mean()
        .assign(currency="SGD")
    )
    return df_out.sort_values("datetime").reset_index(drop=True)


# ── Zone dispatcher ───────────────────────────────────────────────────────────

def save_zone(zone: str, df: pd.DataFrame):
    out_path = os.path.join(DATA_DIR, f"{zone}_price.parquet")
    df.to_parquet(out_path, index=False)
    lo, hi = df["datetime"].min(), df["datetime"].max()
    print(f"  {zone}: saved {len(df)} rows  [{lo.date()} → {hi.date()}]")


def process_zone(zone: str):
    out_path = os.path.join(DATA_DIR, f"{zone}_price.parquet")
    if os.path.exists(out_path):
        existing = pd.read_parquet(out_path)
        print(f"  {zone}: already exists ({len(existing)} rows). Delete to re-fetch.")
        return

    print(f"\nFetching prices for {zone} ...")

    if zone == "FI":
        df = fetch_entsoe("FI")
    elif zone == "BE":
        df = fetch_entsoe("BE")
    elif zone == "US-MIDA-PJM":
        df = fetch_pjm()
    elif zone == "US-NY-NYIS":
        df = fetch_nyiso()
    elif zone == "SG":
        df = parse_singapore()
        if df is None:
            return
    else:
        print(f"  Unknown zone: {zone}")
        return

    save_zone(zone, df)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)

    zones = ["FI", "BE", "US-MIDA-PJM", "US-NY-NYIS", "SG"]

    print("=" * 60)
    print("  Electricity Price Fetch")
    print(f"  {START_DATE.date()} → {END_DATE.date()}")
    print("=" * 60)

    if not ENTSOE_API_KEY:
        print("\n  WARNING: ENTSOE_API_KEY not set — skipping Finland and Belgium.")
        print("  Add ENTSOE_API_KEY=<your_key> to .env")
        print("  Register free at https://transparency.entsoe.eu\n")

    if not PJM_API_KEY:
        print("\n  WARNING: PJM_API_KEY not set — skipping PJM.")
        print("  Add PJM_API_KEY=<your_key> to .env")
        print("  Register free at https://api.pjm.com/group\n")

    for zone in zones:
        if zone in ("FI", "BE") and not ENTSOE_API_KEY:
            continue
        if zone == "US-MIDA-PJM" and not PJM_API_KEY:
            continue
        process_zone(zone)

    print("\nDone. Price parquets saved to data/raw/.")
    print("Next: run lp_model.py to incorporate price signal into objective.")
