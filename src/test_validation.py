"""
test_validation.py — Integration test for the carbon-aware scheduling LP.

Runs the full model (C1-C7 simultaneously active) on a 7-day window of real
CI/CFE data for three regions (PJM, Finland, Belgium).  Verifies that all
constraints are satisfied in the same solution and that the LP outperforms
the uniform baseline.

Usage: python src/test_validation.py
"""

import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from lp_model import solve
from run_sensitivity import load_data, LABELS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REGIONS = ["PJM", "Finland", "Belgium"]   # home region first (r0 = 0)
T_HOURS = 168                             # 7-day window
DEMAND  = 1.0                             # kWh — one batch per 24-hour block

# All seven constraints active; values chosen to be genuinely binding on
# this region/data combination.
PARAMS = dict(
    alpha = 0.5,
    gamma = 0.0,
    eta   = 0.3,   # fairness weight: M term active
    sigma = 0.5,   # geographic cap: at most 50 % of hourly load off-home
    kappa = 0.2,   # ramp rate: at most 20 % of C_max change per hour
    rho   = 0.4,   # dynamic range: peak-to-trough ≤ 40 % of C_max
    delta = 24,    # latency: each batch must be served within 24 h
    r0    = 0,     # home region index
)
# Parameters match the "Full model (+ Fairness)" scenario from CONSTRAINT_SCENARIOS
# in run_sensitivity.py — the most constrained configuration actually analysed in
# the thesis.  A slack constraint in this test is informative: it means the
# constraint is not the binding factor for this data window and parameter set.

TOL = 1e-4

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(condition, label):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    return condition

# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

def test_integration():
    print("=" * 66)
    print("  Carbon-Aware LP — Integration Test")
    print(f"  Regions : {', '.join(REGIONS)}")
    print(f"  Window  : {T_HOURS} h ({T_HOURS // 24} days of real data)")
    print(f"  Active  : C1-C7 simultaneously")
    print("=" * 66)

    # ── 1. Load real data ──────────────────────────────────────────────────
    df     = load_data()
    df_sub = df.head(T_HOURS)
    T      = T_HOURS
    R      = len(REGIONS)

    CI  = df_sub[[f"ci_{r}"  for r in REGIONS]].values.T   # (R, T)
    CFE = df_sub[[f"cfe_{r}" for r in REGIONS]].values.T   # (R, T)

    print(f"\n  Data: {df_sub.index[0]}  to  {df_sub.index[-1]}")
    for i, reg in enumerate(REGIONS):
        print(f"    {reg:10s}  CI mean={CI[i].mean():.1f}  "
              f"std={CI[i].std():.1f}  "
              f"range=[{CI[i].min():.0f}, {CI[i].max():.0f}] gCO2/kWh")

    # ── 2. Demand: one 1-kWh batch every 24 h, deadline δ=24 h ───────────
    C_max  = np.full(R, DEMAND)
    C_min  = np.zeros(R)
    D_flex = np.zeros(T)
    for t in range(0, T, 24):
        D_flex[t] = DEMAND
    D_total = D_flex.sum()

    n_batches = int((D_flex > 0).sum())
    print(f"\n  Demand  : {n_batches} batches × {DEMAND} kWh  "
          f"= {D_total:.0f} kWh total  (δ={PARAMS['delta']} h per batch)")
    print(f"  Params  : α={PARAMS['alpha']}  σ={PARAMS['sigma']}  "
          f"κ={PARAMS['kappa']}  ρ={PARAMS['rho']}  η={PARAMS['eta']}")

    # ── 3. Solve ───────────────────────────────────────────────────────────
    res = solve(CI, CFE, D_flex, C_min, C_max, **PARAMS)

    print(f"\n  Solver  : {res.status}")
    if res.obj_value == float("inf"):
        print("  [FAIL] LP infeasible — cannot verify constraints.")
        return False

    x = res.x   # (R, T)

    # ── 4. Constraint checks + binding report ─────────────────────────────
    print("\n  Constraint checks  (observed → limit  |  TIGHT = at limit)")
    results = []

    # C1 — total demand served (equality, always tight)
    served = x.sum()
    tight  = abs(served - D_total) < TOL
    results.append(check(tight,
        f"C1  demand   {served:.4f} = {D_total:.1f} kWh  {'[TIGHT]' if tight else ''}"))

    # C2 — every batch served within its δ-hour window
    delta   = PARAMS["delta"]
    c2_ok   = True
    latest  = []   # how late within each window the LP places load
    for tau in range(T):
        if D_flex[tau] <= 0:
            continue
        t_end   = min(tau + delta, T)
        window  = x[:, tau:t_end]
        covered = float(window.sum())
        if covered < D_flex[tau] - TOL:
            c2_ok = False
            print(f"      violation at τ={tau}: covered {covered:.4f} < {D_flex[tau]:.1f}")
        nz = np.where(window.sum(axis=0) > TOL)[0]
        latest.append(int(nz[-1]) if len(nz) else 0)
    max_latest = max(latest) if latest else 0
    results.append(check(c2_ok,
        f"C2  deadline  all {n_batches} batches covered within δ={delta} h  "
        f"(latest placement at relative hour {max_latest}/{delta-1}"
        f"{'  [TIGHT]' if max_latest == delta - 1 else ''})"))

    # C3 — capacity bounds per region per hour
    lo, hi = x.min(), x.max()
    tight_lo = lo < TOL
    tight_hi = abs(hi - DEMAND) < TOL
    results.append(check(lo >= -TOL and hi <= DEMAND + TOL,
        f"C3  capacity  min={lo:.4f} (C_min=0{'  [TIGHT]' if tight_lo else ''})  "
        f"max={hi:.4f} (C_max={DEMAND}{'  [TIGHT]' if tight_hi else ''})"))

    # C4 — geographic transfer fraction per hour
    sigma   = PARAMS["sigma"]
    c4_vio  = 0
    max_frac = 0.0
    for t in range(T):
        total_t = float(x[:, t].sum())
        away_t  = float(x[1:, t].sum())
        if total_t > TOL:
            frac = away_t / total_t
            if frac > max_frac:
                max_frac = frac
            if away_t > sigma * total_t + TOL:
                c4_vio += 1
    results.append(check(c4_vio == 0,
        f"C4  geo cap   max off-home fraction={max_frac:.4f}  limit=σ={sigma}"
        f"{'  [TIGHT]' if abs(max_frac - sigma) < 1e-3 else ''}"))

    # C5 — equity auxiliary: M ≥ regional carbon for all r
    regional_carbon = [(x[r] * CI[r]).sum() for r in range(R)]
    M_required = max(regional_carbon)
    tight_M = abs(res.equity_M - M_required) < 1.0
    results.append(check(tight_M,
        f"C5  fairness  M={res.equity_M:.1f}  max_regional_carbon={M_required:.1f}"
        f"{'  [TIGHT]' if tight_M else ''}"))

    # C6 — ramp rate between consecutive hours
    kappa   = PARAMS["kappa"]
    limit_k = kappa * C_max
    diffs   = np.abs(np.diff(x, axis=1))
    c6_vio  = int((diffs > limit_k[:, None] + TOL).sum())
    tight_k = abs(diffs.max() - limit_k[0]) < 1e-3
    results.append(check(c6_vio == 0,
        f"C6  ramp      max={diffs.max():.4f}  limit=κ·C_max={limit_k[0]:.4f}"
        f"{'  [TIGHT]' if tight_k else ''}"))

    # C7 — dynamic range per region over full horizon
    rho    = PARAMS["rho"]
    c7_ok  = True
    swings = []
    for r, reg in enumerate(REGIONS):
        swing = float(x[r].max() - x[r].min())
        limit = rho * C_max[r]
        swings.append((reg, swing, limit))
        if swing > limit + TOL:
            c7_ok = False
    tight_c7 = any(abs(s - l) < 1e-3 for _, s, l in swings)
    swing_str = "  ".join(f"{reg}:{s:.4f}/{l:.4f}" for reg, s, l in swings)
    results.append(check(c7_ok,
        f"C7  dyn range  {swing_str}  limit=ρ·C_max={rho*DEMAND:.4f}"
        f"{'  [TIGHT]' if tight_c7 else ''}"))

    # Sanity — LP carbon < home-only baseline (all demand served at home region
    # uniformly across the horizon).  Appropriate comparison when sigma < 1.
    x_home      = np.zeros((R, T))
    x_home[0, :] = D_total / T
    c_home   = float((x_home * CI).sum())
    saving   = 100.0 * (c_home - res.carbon) / c_home if c_home > 0 else 0.0
    results.append(check(saving > 0,
        f"Sanity    LP {res.carbon:,.1f} < home-only {c_home:,.1f} gCO2"
        f"  (saving {saving:.1f} %)"))

    # ── 5. Schedule summary ────────────────────────────────────────────────
    print(f"\n  Load allocation by region:")
    for r, reg in enumerate(REGIONS):
        pct   = 100.0 * x[r].sum() / D_total if D_total > 0 else 0.0
        swing = float(x[r].max() - x[r].min())
        print(f"    {reg:10s}: {x[r].sum():.3f} kWh ({pct:.1f} %)  "
              f"swing={swing:.3f}  peak={x[r].max():.3f}  floor={x[r].min():.3f}")

    # ── 6. Binding summary ─────────────────────────────────────────────────
    print(f"\n  Note: [TIGHT] = constraint is binding (at its limit).")
    print(f"        Slack constraints are informative: they indicate the")
    print(f"        parameter is not the bottleneck for this data window.")

    # ── 7. Result ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 66}")
    all_pass = all(results)
    n_fail   = results.count(False)
    if all_pass:
        print("  All checks passed. C1-C7 simultaneously satisfied on real data.")
        print("  Parameters: full-model scenario (sigma=0.5, kappa=0.2, rho=0.4, eta=0.3).")
    else:
        print(f"  {n_fail} check(s) failed. See details above.")
    print()
    return all_pass


if __name__ == "__main__":
    sys.exit(0 if test_integration() else 1)
