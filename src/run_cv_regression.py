"""
run_cv_regression.py — Within-region temporal saving vs. CI variability.

For each of the 5 regions, treats that region as the sole home region (locked,
σ=0) and measures how much carbon a temporal-only LP saves relative to a
uniform-in-time baseline confined to that same region. Plots this saving
against the region's coefficient of variation of carbon intensity (CV = std/mean).

This is a diagnostic extension of the temporal-vs-spatial decomposition
(see Essays/cv_regression_methodology.md) — 5 data points, not a formal
statistical test.

Usage
-----
    python src/run_cv_regression.py            # full 2-yr run
    python src/run_cv_regression.py --fast     # 4-week sample for quick testing
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from lp_model import solve
from run_sensitivity import load_data, fast_sample, LABELS, R

RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

WINDOW = 24
DEMAND = 1.0
COMMON = dict(alpha=0.5, gamma=0.0, eta=0.0, kappa=1.0, rho=1.0,
              delta=WINDOW, sigma=0.0)   # locked to home region, full deferral


def run(df: pd.DataFrame) -> pd.DataFrame:
    ci_cols  = [f"ci_{l}"  for l in LABELS]
    cfe_cols = [f"cfe_{l}" for l in LABELS]
    ci_all   = df[ci_cols].values.astype(float)
    cfe_all  = df[cfe_cols].values.astype(float)
    T_total  = len(df)
    n_win    = T_total // WINDOW
    c_max    = np.full(R, DEMAND)

    records = []
    for r0, label in enumerate(LABELS):
        cv = float(ci_all[:, r0].std() / ci_all[:, r0].mean())

        total_uniform  = 0.0
        total_temporal = 0.0
        for i in tqdm(range(n_win), desc=f"{label} (r0={r0})", leave=False):
            t0, t1  = i * WINDOW, (i + 1) * WINDOW
            ci_win  = ci_all[t0:t1].T
            cfe_win = cfe_all[t0:t1].T

            # Uniform-within-region-r0: demand spread evenly over the window,
            # entirely within region r0.
            total_uniform += (DEMAND / WINDOW) * float(ci_win[r0].sum())

            # Temporal-only within region r0: LP locked to home=r0.
            D_flex = np.zeros(WINDOW)
            D_flex[0] = DEMAND
            res = solve(CI=ci_win, CFE=cfe_win, D_flex_batches=D_flex,
                        C_min=np.zeros(R), C_max=c_max, r0=r0, **COMMON)
            total_temporal += res.carbon

        saving = (total_uniform - total_temporal) / total_uniform * 100.0 \
                 if total_uniform > 0 else 0.0
        records.append(dict(region=label, cv=cv, saving_pct=saving,
                            carbon_uniform=total_uniform, carbon_temporal=total_temporal))

    return pd.DataFrame(records)


def summarize(df: pd.DataFrame) -> None:
    print("\n" + "=" * 56)
    print("  Within-Region Temporal Saving vs. CI Variability")
    print("=" * 56)
    print(df[["region", "cv", "saving_pct"]].to_string(index=False,
          formatters={"cv": "{:.3f}".format, "saving_pct": "{:+.2f}".format}))

    # Simple OLS for reference (5 points — diagnostic only, see methodology doc)
    x, y = df["cv"].values, df["saving_pct"].values
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    print(f"\n  OLS (diagnostic, n=5): saving_pct = {slope:.1f}·CV + {intercept:.1f}"
          f"   (R² = {r2:.3f})")
    print("=" * 56)


def main():
    parser = argparse.ArgumentParser(description="CV vs within-region temporal saving")
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

    out = RESULTS_DIR / "cv_regression.csv"
    results.to_csv(out, index=False)
    print(f"\n  Saved → {out}")


if __name__ == "__main__":
    main()
