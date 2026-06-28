"""
test_perturbation.py — Scenario-based perturbation validation on a small
instance using real CI data.

Requested by supervisor (meeting 2026-06-15): take a small instance (2-3
regions, ~4-6 time periods), keep ALL constraints active together, then
perturb ONE input at a time (CI, demand, deadline, capacity) and verify the
solution reacts in the expected direction. The question this answers is
"does the model respond correctly when an input changes," not "are the
constraints satisfied" (that is test_validation.py's job).

Instance: 3 regions, 6 hours, real CI data (2024-07-17 00:00–05:00 UTC)
  R0 (PJM)  : dirty home region, CI ≈ 564–613 gCO2/kWh
  R1 (FI)   : cleanest region,   CI ≈  52–55 gCO2/kWh
  R2 (BE)   : medium region,     CI ≈ 100–138 gCO2/kWh (dips at t=2)

Baseline parameters: sigma=0.6, kappa=0.5, rho=0.7, eta=0.1, delta=6 (full
window), demand=10 kWh arriving at t=0, C_max=10 per region.

Outputs
-------
data/results/perturbation_test.csv   one row per check, with predicted vs.
                                      observed direction and magnitude

Usage: python src/test_perturbation.py
"""

import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from lp_model import solve

RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

R, T = 3, 6
LABELS = ["PJM", "FI", "BE"]

# Real CI values: 2024-07-17 00:00–05:00 UTC
# Source: data/raw/ parquet files, hourly carbon intensity (gCO2/kWh)
CI_BASE = np.array([
    [600, 611, 613, 600, 582, 564],   # PJM: dirty home region
    [ 54,  55,  55,  54,  52,  52],   # FI:  cleanest, low flat profile
    [138, 124, 100, 124, 122, 139],   # BE:  medium, dips at t=2
], dtype=float)
CFE_BASE = np.zeros((R, T))  # alpha=0 in BASE_PARAMS; isolate CI effects

DEMAND  = 10.0
C_MAX   = np.full(R, 10.0)
C_MIN   = np.zeros(R)

BASE_PARAMS = dict(alpha=0.0, gamma=0.0, eta=0.1, sigma=0.6,
                   kappa=0.5, rho=0.7, delta=T, r0=0)

TOL = 1e-4

# Accumulates one row per check
RECORDS: list[dict] = []


def record(scenario: str, change: str, metric: str,
          predicted: str, before: float, after: float,
          passed: bool) -> bool:
    delta = after - before
    pct = (delta / before * 100) if abs(before) > TOL else float("nan")
    RECORDS.append(dict(
        scenario=scenario, change=change, metric=metric, predicted=predicted,
        before=round(before, 3), after=round(after, 3),
        delta=round(delta, 3), pct_change=round(pct, 1) if pct == pct else None,
        result="PASS" if passed else "FAIL",
    ))
    flag = "PASS" if passed else "FAIL"
    print(f"  [{flag}] {scenario}: {metric} {before:.2f} -> {after:.2f} "
         f"(predicted: {predicted})")
    return passed


def D_flex(demand=DEMAND, T=T):
    d = np.zeros(T)
    d[0] = demand
    return d


def region_totals(x):
    return x.sum(axis=1)  # (R,)


def print_alloc(x, title):
    print(f"\n  {title}")
    for r, lab in enumerate(LABELS):
        print(f"    {lab:8s}: " + " ".join(f"{v:5.2f}" for v in x[r]))


def main():
    print("=" * 70)
    print("  Perturbation Test — Real Instance: PJM / FI / BE, 6 hours")
    print("  CI source: 2024-07-17 00:00–05:00 UTC")
    print("=" * 70)
    all_pass = True

    # ── Scenario 0: baseline ────────────────────────────────────────────
    res0 = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                C_min=C_MIN, C_max=C_MAX, **BASE_PARAMS)
    x0 = res0.x
    print_alloc(x0, "Baseline allocation")
    tot0 = region_totals(x0)
    print(f"  Region totals: PJM={tot0[0]:.2f}  FI={tot0[1]:.2f}  BE={tot0[2]:.2f}")

    all_pass &= record("S0 baseline", "none (reference run)",
                       "FI region's share of total load",
                       "FI dominates (lowest CI at ~52–55)",
                       0.0, tot0[1],
                       tot0[1] > tot0[0] and tot0[1] > tot0[2])

    # ── Scenario 1: CI shock — make FI suddenly dirty ───────────────────
    CI_shock = CI_BASE.copy()
    CI_shock[1, :] = 700.0   # FI shocked to 700, dirtier than PJM (~600)
    res1 = solve(CI=CI_shock, CFE=CFE_BASE, D_flex_batches=D_flex(),
                C_min=C_MIN, C_max=C_MAX, **BASE_PARAMS)
    x1 = res1.x
    print_alloc(x1, "Scenario 1: FI CI shocked to 700 flat (dirtier than PJM)")
    tot1 = region_totals(x1)
    print(f"  Region totals: PJM={tot1[0]:.2f}  FI={tot1[1]:.2f}  BE={tot1[2]:.2f}")

    all_pass &= record("S1 CI shock", "FI CI: 52–55 -> 700 flat",
                       "FI region's load (kWh)", "drops, no longer cheapest",
                       tot0[1], tot1[1], tot1[1] < tot0[1])
    all_pass &= record("S1 CI shock", "same as above",
                       "BE region's load (kWh)", "rises, becomes cheapest off-home option",
                       tot0[2], tot1[2], tot1[2] > tot0[2])

    # ── Scenario 2: demand increase ──────────────────────────────────────
    res2 = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(demand=18.0),
                C_min=C_MIN, C_max=C_MAX, **BASE_PARAMS)
    x2 = res2.x
    print_alloc(x2, "Scenario 2: demand increased from 10 to 18 kWh")
    tot2 = region_totals(x2)
    print(f"  Region totals: PJM={tot2[0]:.2f}  FI={tot2[1]:.2f}  BE={tot2[2]:.2f}")

    all_pass &= record("S2 demand increase", "demand: 10 -> 18 kWh",
                       "Total load served (kWh)", "all 18 kWh served (C1)",
                       10.0, float(x2.sum()), abs(x2.sum() - 18.0) < TOL)
    all_pass &= record("S2 demand increase", "same as above",
                       "FI region's load (kWh)", "does not decrease",
                       tot0[1], tot2[1], tot2[1] >= tot0[1] - TOL)
    all_pass &= record("S2 demand increase", "same as above",
                       "BE + PJM load (kWh)", "overflow picked up once FI is exhausted",
                       tot0[2] + tot0[0], tot2[2] + tot2[0],
                       tot2[2] > tot0[2] or tot2[0] > tot0[0])

    # ── Scenario 3: deadline tightened (delta) ───────────────────────────
    res3 = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                C_min=C_MIN, C_max=C_MAX,
                **{**BASE_PARAMS, "delta": 1})
    x3 = res3.x
    print_alloc(x3, "Scenario 3: deadline tightened to delta=1 (must serve at t=0)")
    print(f"  Carbon: baseline={res0.carbon:.1f}  delta=1: {res3.carbon:.1f}")

    all_pass &= record("S3 deadline tightened", "delta: 6h -> 1h",
                       "Total carbon (gCO2)", "rises, can no longer defer to FI's best hours",
                       res0.carbon, res3.carbon, res3.carbon > res0.carbon)
    all_pass &= record("S3 deadline tightened", "same as above",
                       "Load placed after t=0 (kWh)", "zero, deadline forces immediate service",
                       0.0, float(x3[:, 1:].sum()), float(x3[:, 1:].sum()) < TOL)

    # ── Scenario 4: capacity squeeze on FI ───────────────────────────────
    C_max_mild = C_MAX.copy()
    C_max_mild[1] = 3.0   # FI: 3 kWh/h × 6h = 18 kWh capacity, still enough
    res4a = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                 C_min=C_MIN, C_max=C_max_mild, **BASE_PARAMS)
    x4a   = res4a.x
    tot4a = region_totals(x4a)
    print_alloc(x4a, "Scenario 4a: FI capacity mildly squeezed to 3 kWh/h "
                     "(window total still enough — no overflow expected)")
    print(f"  Region totals: PJM={tot4a[0]:.2f}  FI={tot4a[1]:.2f}  BE={tot4a[2]:.2f}")

    all_pass &= record("S4a mild capacity squeeze",
                       "FI C_max: 10 -> 3 kWh/h (window cap 18 kWh, still enough)",
                       "FI region's peak hourly load (kWh)", "never exceeds 3.0",
                       float(x0[1].max()), float(x4a[1].max()), x4a[1].max() <= 3.0 + TOL)
    all_pass &= record("S4a mild capacity squeeze", "same as above",
                       "FI region's total load (kWh)", "unchanged — spreads over more hours instead",
                       tot0[1], tot4a[1], abs(tot4a[1] - tot0[1]) < TOL)

    C_max_severe = C_MAX.copy()
    C_max_severe[1] = 0.5   # FI: 0.5 kWh/h × 6h = 3 kWh cap < needed allocation
    res4b = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                 C_min=C_MIN, C_max=C_max_severe, **BASE_PARAMS)
    x4b   = res4b.x
    tot4b = region_totals(x4b)
    print_alloc(x4b, "Scenario 4b: FI capacity severely squeezed to 0.5 kWh/h "
                     "(window cap = 3 kWh < needed — overflow forced)")
    print(f"  Region totals: PJM={tot4b[0]:.2f}  FI={tot4b[1]:.2f}  BE={tot4b[2]:.2f}")

    all_pass &= record("S4b severe capacity squeeze",
                       "FI C_max: 10 -> 0.5 kWh/h (window cap 3 kWh < needed)",
                       "FI region's peak hourly load (kWh)", "never exceeds 0.5",
                       float(x0[1].max()), float(x4b[1].max()), x4b[1].max() <= 0.5 + TOL)
    all_pass &= record("S4b severe capacity squeeze", "same as above",
                       "FI region's total load (kWh)", "drops — window-wide cap now binds",
                       tot0[1], tot4b[1], tot4b[1] < tot0[1] - TOL)
    all_pass &= record("S4b severe capacity squeeze", "same as above",
                       "BE + PJM load (kWh)", "genuine overflow picked up elsewhere",
                       tot0[2] + tot0[0], tot4b[2] + tot4b[0],
                       tot4b[2] > tot0[2] + TOL or tot4b[0] > tot0[0] + TOL)

    # ── Results table ──────────────────────────────────────────────────
    df = pd.DataFrame(RECORDS)
    out = RESULTS_DIR / "perturbation_test.csv"
    df.to_csv(out, index=False)

    print(f"\n{'=' * 70}")
    print("  Summary")
    print(f"{'=' * 70}")
    with pd.option_context("display.max_colwidth", 28, "display.width", 140):
        print(df[["scenario", "metric", "before", "after", "predicted", "result"]]
              .to_string(index=False))

    n_fail = (df["result"] == "FAIL").sum()
    print(f"\n  {len(df)} checks, {len(df) - n_fail} pass, {n_fail} fail.")
    if n_fail == 0:
        print("  Every metric moved in the predicted direction.")
    print(f"  Saved -> {out}")
    print()
    return n_fail == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
