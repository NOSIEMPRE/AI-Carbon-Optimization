"""
run_decomposition.py — Temporal vs. Spatial decomposition backtest.

Decomposes the LP's carbon saving into a spatial-routing component, a
temporal-shifting component, and an interaction term, following the
three-variant design in Sukprasert et al. (EuroSys 2024) and the
spatio-temporal load-shifting literature (see Essays/decomposition_methodology.md
for the full derivation and references).

Four variants are solved on the same 731 rolling 24-hour windows used by
run_sensitivity.py / run_backtest.py:

  uniform        demand / (R*T) at every (region, hour)        — zero-saving reference
  spatial_only   delta=1  (must serve immediately), sigma=1.0  — routing only, no deferral
  temporal_only  delta=24 (full window), sigma=0.0             — timing only, locked to home
  full_lp        delta=24, sigma=1.0                            — both free (unconstrained LP)

All four share alpha=0.5, gamma=0, eta=0, kappa=1.0, rho=1.0 (C6/C7 inactive) so the
decomposition isolates the temporal/spatial axes from the operational constraints
analysed separately in the sensitivity study.

Usage
-----
    python src/run_decomposition.py            # full 2-yr run (731 windows)
    python src/run_decomposition.py --fast     # 4-week sample for quick testing
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from lp_model import solve
from run_sensitivity import load_data, fast_sample, LABELS, R, SEASON_MAP

RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

WINDOW = 24
DEMAND = 1.0

# Shared objective weights; only delta/sigma vary across the three LP variants.
COMMON = dict(alpha=0.5, gamma=0.0, eta=0.0, kappa=1.0, rho=1.0, r0=0)

VARIANTS = {
    "spatial":  dict(delta=1,      sigma=1.0),  # route only, no deferral
    "temporal": dict(delta=WINDOW, sigma=0.0),  # defer only, locked to home region
    "full":     dict(delta=WINDOW, sigma=1.0),  # unconstrained LP (both free)
}


def uniform_carbon(ci_win: np.ndarray, demand: float) -> float:
    T = ci_win.shape[1]
    x = np.full((R, T), demand / (R * T))
    return float((x * ci_win).sum())


def run(df: pd.DataFrame) -> pd.DataFrame:
    ci_cols  = [f"ci_{l}"  for l in LABELS]
    cfe_cols = [f"cfe_{l}" for l in LABELS]
    ci_all   = df[ci_cols].values.astype(float)
    cfe_all  = df[cfe_cols].values.astype(float)
    T_total  = len(df)
    n_win    = T_total // WINDOW
    c_max    = np.full(R, DEMAND)

    records = []
    for i in tqdm(range(n_win), desc="Decomposition backtest"):
        t0, t1 = i * WINDOW, (i + 1) * WINDOW
        ci_win  = ci_all[t0:t1].T
        cfe_win = cfe_all[t0:t1].T
        dt      = df.index[t0]

        row = {
            "window_id": i,
            "datetime":  dt,
            "season":    SEASON_MAP[dt.month],
            "carbon_uniform": uniform_carbon(ci_win, DEMAND),
        }

        for name, overrides in VARIANTS.items():
            D_flex = np.zeros(WINDOW)
            D_flex[0] = DEMAND
            res = solve(CI=ci_win, CFE=cfe_win, D_flex_batches=D_flex,
                        C_min=np.zeros(R), C_max=c_max,
                        **COMMON, **overrides)
            row[f"carbon_{name}"] = res.carbon

        records.append(row)

    return pd.DataFrame(records)


def summarize(df: pd.DataFrame) -> None:
    def pct(base, opt):
        return (base - opt) / base * 100 if base > 0 else 0.0

    print("\n" + "=" * 62)
    print("  Temporal vs. Spatial Decomposition — Summary")
    print("=" * 62)

    groups = [("ALL", df)] + [(s, df[df["season"] == s])
                               for s in ["DJF", "MAM", "JJA", "SON"]]
    for label, sub in groups:
        c_u = sub["carbon_uniform"].sum()
        c_s = sub["carbon_spatial"].sum()
        c_t = sub["carbon_temporal"].sum()
        c_f = sub["carbon_full"].sum()

        s_spatial  = pct(c_u, c_s)
        s_temporal = pct(c_u, c_t)
        s_full     = pct(c_u, c_f)
        interaction = s_full - s_spatial - s_temporal

        print(f"\n  [{label}]  ({len(sub)} windows)")
        print(f"    Spatial-only   saving : {s_spatial:+7.2f} %")
        print(f"    Temporal-only  saving : {s_temporal:+7.2f} %")
        print(f"    Full LP        saving : {s_full:+7.2f} %")
        print(f"    Interaction term       : {interaction:+7.2f} %"
              f"   (= full − spatial − temporal)")
    print("\n" + "=" * 62)


def main():
    parser = argparse.ArgumentParser(description="Temporal vs spatial decomposition")
    parser.add_argument("--fast", action="store_true",
                        help="4-week sample (one week per season) for quick testing")
    args = parser.parse_args()

    print("Loading data …")
    df = load_data()
    if args.fast:
        df = fast_sample(df)
        print(f"  --fast: using {len(df)} hours")
    else:
        print(f"  {len(df):,} hours  |  {df.index.min().date()} → {df.index.max().date()}")

    results = run(df)
    summarize(results)

    out = RESULTS_DIR / "decomposition.csv"
    results.to_csv(out, index=False)
    print(f"\n  Saved → {out}")


if __name__ == "__main__":
    main()
