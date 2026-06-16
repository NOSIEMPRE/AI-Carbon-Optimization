"""
test_perturbation.py — Scenario-based perturbation validation on a tiny,
hand-traceable instance.

Requested by supervisor (meeting 2026-06-15): take a small instance (2-3
regions, ~4-6 time periods), keep ALL constraints active together, then
perturb ONE input at a time (CI, demand, deadline, capacity) and verify the
solution reacts in the expected direction. This is a different check from
test_validation.py (which verifies constraint satisfaction on one fixed
representative instance) — here the question is "does the model respond
correctly when an input changes," not "are the constraints satisfied."

Instance: 3 regions, 6 hours, synthetic but interpretable CI profiles
  R0 (home)   : flat, dirty   (400 gCO2/kWh every hour)
  R1 (clean)  : dips mid-window (100, 90, 80, 90, 100, 110)
  R2 (medium) : flat, medium  (250 gCO2/kWh every hour)

Baseline parameters: sigma=0.6, kappa=0.5, rho=0.7, eta=0.1, delta=6 (full
window), demand=10 kWh arriving at t=0, C_max=10 per region.

Usage: python src/test_perturbation.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from lp_model import solve

R, T = 3, 6
LABELS = ["Home", "Clean", "Medium"]

CI_BASE = np.array([
    [400, 400, 400, 400, 400, 400],   # Home: flat, dirty
    [100,  90,  80,  90, 100, 110],   # Clean: dips at t=2
    [250, 250, 250, 250, 250, 250],   # Medium: flat
], dtype=float)
CFE_BASE = np.zeros((R, T))  # alpha irrelevant here; isolate other effects

DEMAND  = 10.0
C_MAX   = np.full(R, 10.0)
C_MIN   = np.zeros(R)

BASE_PARAMS = dict(alpha=0.0, gamma=0.0, eta=0.1, sigma=0.6,
                   kappa=0.5, rho=0.7, delta=T, r0=0)

TOL = 1e-4


def check(condition, label):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    return condition


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
    print("=" * 66)
    print("  Perturbation Test — Tiny Hand-Traceable Instance (3 regions x 6h)")
    print("=" * 66)
    results = []

    # ── Scenario 0: baseline ────────────────────────────────────────────
    res0 = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                C_min=C_MIN, C_max=C_MAX, **BASE_PARAMS)
    x0 = res0.x
    print_alloc(x0, "Baseline allocation")
    tot0 = region_totals(x0)
    print(f"  Region totals: Home={tot0[0]:.2f}  Clean={tot0[1]:.2f}  Medium={tot0[2]:.2f}")

    # Expectation: Clean region (lowest CI) gets the majority of load.
    results.append(check(tot0[1] > tot0[0] and tot0[1] > tot0[2],
        f"S0  baseline: Clean region dominates allocation "
        f"(Home={tot0[0]:.2f}, Clean={tot0[1]:.2f}, Medium={tot0[2]:.2f})"))

    # ── Scenario 1: CI shock — make Clean region suddenly dirty ─────────
    # Expectation: load shifts away from Clean toward Medium (now cheapest).
    CI_shock = CI_BASE.copy()
    CI_shock[1, :] = 500.0  # Clean becomes dirtier than Home
    res1 = solve(CI=CI_shock, CFE=CFE_BASE, D_flex_batches=D_flex(),
                C_min=C_MIN, C_max=C_MAX, **BASE_PARAMS)
    x1 = res1.x
    print_alloc(x1, "Scenario 1: Clean region CI shocked to 500 (dirtier than Home)")
    tot1 = region_totals(x1)
    print(f"  Region totals: Home={tot1[0]:.2f}  Clean={tot1[1]:.2f}  Medium={tot1[2]:.2f}")

    results.append(check(tot1[1] < tot0[1],
        f"S1  CI shock: Clean region's share drops "
        f"({tot0[1]:.2f} -> {tot1[1]:.2f}) when its CI is shocked up"))
    results.append(check(tot1[2] > tot0[2],
        f"S1  CI shock: Medium region's share rises "
        f"({tot0[2]:.2f} -> {tot1[2]:.2f}) as load reroutes to the new "
        f"cheapest region"))

    # ── Scenario 2: demand increase ──────────────────────────────────────
    # Expectation: total served scales with demand (C1); per-region totals
    # increase or hold, none decrease, since more demand can only add load.
    res2 = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(demand=18.0),
                C_min=C_MIN, C_max=C_MAX, **BASE_PARAMS)
    x2 = res2.x
    print_alloc(x2, "Scenario 2: demand increased from 10 to 18 kWh")
    tot2 = region_totals(x2)
    print(f"  Region totals: Home={tot2[0]:.2f}  Clean={tot2[1]:.2f}  Medium={tot2[2]:.2f}")

    results.append(check(abs(x2.sum() - 18.0) < TOL,
        f"S2  demand increase: all 18 kWh served (C1) — served={x2.sum():.2f}"))
    results.append(check(tot2[1] >= tot0[1] - TOL,
        f"S2  demand increase: Clean region's load does not decrease "
        f"({tot0[1]:.2f} -> {tot2[1]:.2f}) when demand grows"))
    # With more demand than one region's C_max can absorb at the cheapest
    # hour, the LP must spread to Medium/Home too.
    results.append(check(tot2[2] > tot0[2] or tot2[0] > tot0[0],
        f"S2  demand increase: overflow load is absorbed by Medium and/or "
        f"Home once Clean and the sigma/ramp caps are exhausted "
        f"(Medium: {tot0[2]:.2f}->{tot2[2]:.2f}, Home: {tot0[0]:.2f}->{tot2[0]:.2f})"))

    # ── Scenario 3: deadline tightened (delta) ───────────────────────────
    # Expectation: forcing the batch to be served immediately (delta=1)
    # removes access to the clean dip at t=2, so carbon should rise.
    res3 = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                C_min=C_MIN, C_max=C_MAX,
                **{**BASE_PARAMS, "delta": 1})
    x3 = res3.x
    print_alloc(x3, "Scenario 3: deadline tightened to delta=1 (must serve at t=0)")
    print(f"  Carbon: baseline={res0.carbon:.1f}  delta=1: {res3.carbon:.1f}")

    results.append(check(res3.carbon > res0.carbon,
        f"S3  tighter deadline: carbon increases when access to the clean "
        f"window (t=2) is removed ({res0.carbon:.1f} -> {res3.carbon:.1f})"))
    results.append(check(float(x3[:, 1:].sum()) < TOL,
        "S3  tighter deadline: no load placed after t=0 (delta=1 enforced)"))

    # ── Scenario 4: capacity squeeze on the Clean region ─────────────────
    # First try a mild squeeze (3 kWh/h): with T=6h, Clean can still absorb
    # up to 18 kWh/window, well above the 6 kWh it wants — so NO overflow
    # should occur; the LP should just spread Clean's load over more hours.
    # This is itself a real prediction worth checking, not a trivial one.
    C_max_mild = C_MAX.copy()
    C_max_mild[1] = 3.0
    res4a = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                 C_min=C_MIN, C_max=C_max_mild, **BASE_PARAMS)
    x4a   = res4a.x
    tot4a = region_totals(x4a)
    print_alloc(x4a, "Scenario 4a: Clean capacity mildly squeezed to 3 kWh/h "
                     "(window can still fit 18 kWh — no overflow expected)")
    print(f"  Region totals: Home={tot4a[0]:.2f}  Clean={tot4a[1]:.2f}  Medium={tot4a[2]:.2f}")

    results.append(check(x4a[1].max() <= 3.0 + TOL,
        f"S4a mild squeeze: Clean region never exceeds its new C_max=3.0 "
        f"(observed max={x4a[1].max():.2f})"))
    results.append(check(abs(tot4a[1] - tot0[1]) < TOL,
        f"S4a mild squeeze: Clean's TOTAL is unchanged ({tot0[1]:.2f} -> "
        f"{tot4a[1]:.2f}) — capacity is per-hour, so the LP just spreads "
        f"over more hours within Clean instead of overflowing elsewhere"))

    # Now a severe squeeze (0.5 kWh/h): max window capacity = 0.5*6 = 3 kWh,
    # below the 6 kWh baseline wants in Clean — genuine overflow is forced.
    C_max_severe = C_MAX.copy()
    C_max_severe[1] = 0.5
    res4b = solve(CI=CI_BASE, CFE=CFE_BASE, D_flex_batches=D_flex(),
                 C_min=C_MIN, C_max=C_max_severe, **BASE_PARAMS)
    x4b   = res4b.x
    tot4b = region_totals(x4b)
    print_alloc(x4b, "Scenario 4b: Clean capacity severely squeezed to 0.5 kWh/h "
                     "(window cap = 3 kWh < 6 kWh wanted — overflow forced)")
    print(f"  Region totals: Home={tot4b[0]:.2f}  Clean={tot4b[1]:.2f}  Medium={tot4b[2]:.2f}")

    results.append(check(x4b[1].max() <= 0.5 + TOL,
        f"S4b severe squeeze: Clean region never exceeds its new C_max=0.5 "
        f"(observed max={x4b[1].max():.2f})"))
    results.append(check(tot4b[1] < tot0[1] - TOL,
        f"S4b severe squeeze: Clean's total drops below baseline "
        f"({tot0[1]:.2f} -> {tot4b[1]:.2f}) once the window-wide cap binds"))
    results.append(check(tot4b[2] > tot0[2] + TOL or tot4b[0] > tot0[0] + TOL,
        f"S4b severe squeeze: the shortfall is genuinely picked up by "
        f"Medium and/or Home (Medium: {tot0[2]:.2f}->{tot4b[2]:.2f}, "
        f"Home: {tot0[0]:.2f}->{tot4b[0]:.2f})"))

    # ── Result ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 66}")
    n_fail = results.count(False)
    if n_fail == 0:
        print("  All perturbation scenarios behaved in the expected direction.")
    else:
        print(f"  {n_fail} scenario(s) did not behave as expected. See above.")
    print()
    return n_fail == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
