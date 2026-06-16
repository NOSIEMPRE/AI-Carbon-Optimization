"""
diagnose_sensitivity.py — Investigate why kappa, rho, alpha show small impact
in the full two-year sensitivity sweep, despite kappa/rho being clearly binding
in the small validation instance.

Raised by supervisor (meeting 2026-06-15): "if you put a ramp per cap of 0.2 up
to 1, you have the same solution... I believe it's wrong." This script checks
three hypotheses without assuming the result is correct:

  H1 (kappa/rho): the "basic LP" (sigma=kappa=rho=1, eta=0) naturally produces
     narrow ramps/swings in most windows, so tightening kappa/rho only binds
     in a minority of windows; the AGGREGATE effect over 731 windows is small
     even though specific windows (like the July example) show large effects.

  H2 (alpha): CI and CFE are strongly correlated within each region, so
     ranking (region,hour) pairs by CI alone vs by CI*(1-alpha*CFE) gives
     nearly the same ordering, hence nearly the same optimal allocation,
     hence nearly the same realized carbon — even though alpha changes the
     objective function value.

  H3 (bug check): explicitly compare the optimal allocation x (not just the
     objective) across alpha=0 vs alpha=1 on a sample of windows. If x is
     identical everywhere, that is a stronger flag than carbon being similar.

Usage:
    python src/diagnose_sensitivity.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from lp_model import solve
from run_sensitivity import load_data, LABELS, R

WINDOW = 24
DEMAND = 1.0
C_MAX  = np.full(R, DEMAND)


def basic_lp_natural_ramp_and_swing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Solve the 'basic LP' (no C4/C6/C7, eta=0) over every window and record
    the natural max ramp and max swing actually produced, as a fraction of
    C_max. This tells us what fraction of windows WOULD be bound by each
    tested kappa/rho threshold.
    """
    ci_cols  = [f"ci_{l}"  for l in LABELS]
    cfe_cols = [f"cfe_{l}" for l in LABELS]
    ci_all   = df[ci_cols].values.astype(float)
    cfe_all  = df[cfe_cols].values.astype(float)
    n_win    = len(df) // WINDOW

    records = []
    for i in range(n_win):
        t0, t1  = i * WINDOW, (i + 1) * WINDOW
        ci_win  = ci_all[t0:t1].T
        cfe_win = cfe_all[t0:t1].T

        D_flex = np.zeros(WINDOW)
        D_flex[0] = DEMAND
        res = solve(CI=ci_win, CFE=cfe_win, D_flex_batches=D_flex,
                    C_min=np.zeros(R), C_max=C_MAX,
                    alpha=0.5, gamma=0.0, eta=0.0,
                    delta=WINDOW, sigma=1.0, kappa=1.0, rho=1.0, r0=0)
        x = res.x  # (R, WINDOW)

        max_ramp  = float(np.abs(np.diff(x, axis=1)).max())
        max_swing = float((x.max(axis=1) - x.min(axis=1)).max())
        records.append(dict(window=i, max_ramp=max_ramp, max_swing=max_swing))

    return pd.DataFrame(records)


def alpha_allocation_diff(df: pd.DataFrame, n_sample: int = 100) -> pd.DataFrame:
    """
    For a sample of windows, solve at alpha=0 and alpha=1 (otherwise identical
    settings) and report ||x_alpha0 - x_alpha1||, plus whether the *set* of
    (region,hour) pairs receiving load differs.
    """
    ci_cols  = [f"ci_{l}"  for l in LABELS]
    cfe_cols = [f"cfe_{l}" for l in LABELS]
    ci_all   = df[ci_cols].values.astype(float)
    cfe_all  = df[cfe_cols].values.astype(float)
    n_win    = len(df) // WINDOW
    rng      = np.random.default_rng(0)
    sample   = rng.choice(n_win, size=min(n_sample, n_win), replace=False)

    records = []
    for i in sample:
        t0, t1  = i * WINDOW, (i + 1) * WINDOW
        ci_win  = ci_all[t0:t1].T
        cfe_win = cfe_all[t0:t1].T
        D_flex  = np.zeros(WINDOW)
        D_flex[0] = DEMAND

        common = dict(CI=ci_win, CFE=cfe_win, D_flex_batches=D_flex,
                      C_min=np.zeros(R), C_max=C_MAX,
                      gamma=0.0, eta=0.0, delta=WINDOW, sigma=1.0,
                      kappa=1.0, rho=1.0, r0=0)
        x0 = solve(**common, alpha=0.0).x
        x1 = solve(**common, alpha=1.0).x

        l1_diff   = float(np.abs(x0 - x1).sum())
        same_mask = np.isclose(x0, x1, atol=1e-6)
        records.append(dict(window=int(i), l1_diff=l1_diff,
                            frac_identical_cells=float(same_mask.mean())))

    return pd.DataFrame(records)


def ci_cfe_correlation(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lab in LABELS:
        ci  = df[f"ci_{lab}"].values
        cfe = df[f"cfe_{lab}"].values
        if cfe.std() > 0:
            corr = float(np.corrcoef(ci, cfe)[0, 1])
        else:
            corr = float("nan")
        rows.append(dict(region=lab, corr_CI_CFE=corr,
                         cfe_mean=float(cfe.mean()), cfe_std=float(cfe.std())))
    return pd.DataFrame(rows)


def main():
    print("Loading data …")
    df = load_data()
    print(f"  {len(df):,} hours\n")

    # ── H1: kappa / rho ──────────────────────────────────────────────────
    print("=" * 70)
    print("H1: Natural ramp/swing distribution (basic LP, sigma=kappa=rho=1)")
    print("=" * 70)
    nat = basic_lp_natural_ramp_and_swing(df)
    nat.to_csv("data/results/diagnostic_natural_ramp_swing.csv", index=False)

    print(f"\n  Max ramp  (fraction of C_max) — percentiles across {len(nat)} windows:")
    for q in [10, 25, 50, 75, 90, 95, 99, 100]:
        print(f"    p{q:<3d}: {np.percentile(nat['max_ramp'], q):.3f}")

    print(f"\n  Max swing (fraction of C_max) — percentiles across {len(nat)} windows:")
    for q in [10, 25, 50, 75, 90, 95, 99, 100]:
        print(f"    p{q:<3d}: {np.percentile(nat['max_swing'], q):.3f}")

    print("\n  % of windows where natural ramp EXCEEDS each tested kappa "
          "(i.e. kappa WOULD bind):")
    for k in [0.1, 0.2, 0.5, 0.8, 1.0]:
        pct = float((nat["max_ramp"] > k).mean() * 100)
        print(f"    kappa={k:<4}: {pct:5.1f}% of windows bound")

    print("\n  % of windows where natural swing EXCEEDS each tested rho "
          "(i.e. rho WOULD bind):")
    for r in [0.2, 0.4, 0.6, 0.8, 1.0]:
        pct = float((nat["max_swing"] > r).mean() * 100)
        print(f"    rho={r:<4}: {pct:5.1f}% of windows bound")

    # ── H2: CI/CFE correlation ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("H2: CI–CFE correlation per region (explains alpha's small effect)")
    print("=" * 70)
    corr = ci_cfe_correlation(df)
    print(corr.to_string(index=False))

    # ── H3: explicit allocation diff at alpha=0 vs alpha=1 ───────────────
    print("\n" + "=" * 70)
    print("H3: Allocation x(alpha=0) vs x(alpha=1) — bug check (n=100 windows)")
    print("=" * 70)
    diff = alpha_allocation_diff(df, n_sample=100)
    diff.to_csv("data/results/diagnostic_alpha_allocation_diff.csv", index=False)
    print(f"\n  Windows with ANY difference in x: "
          f"{(diff['l1_diff'] > 1e-6).sum()} / {len(diff)}")
    print(f"  Mean L1 diff (kWh) across sample: {diff['l1_diff'].mean():.4f}")
    print(f"  Mean fraction of identical cells: {diff['frac_identical_cells'].mean():.4f}")
    print(f"  Max L1 diff observed:             {diff['l1_diff'].max():.4f}")

    print("\n" + "=" * 70)
    print("Interpretation")
    print("=" * 70)
    print("""
  If H1 holds (most windows have natural ramp/swing well below the tested
  kappa/rho thresholds), the small aggregate sensitivity is NOT a bug — it
  means the LP's unconstrained temporal pattern is already smooth in most
  windows, and only a minority of windows (like the July example used in
  Section 5) are sharply peaked enough for kappa/rho to bind hard.

  If H2/H3 hold (CI and CFE are highly correlated, and the allocation barely
  changes between alpha=0 and alpha=1), alpha's small effect is explained by
  the discount rarely flipping the rank order of (region,hour) pairs — the
  cleanest CI hours are usually also the highest-CFE hours, so there is
  little room for the discount to redirect the schedule.
""")


if __name__ == "__main__":
    main()
