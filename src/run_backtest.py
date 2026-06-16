"""
Rolling-window LP backtest for carbon-aware compute scheduling.

For each non-overlapping window of W hours the LP is solved independently,
treating each window as a self-contained planning horizon (equivalent to
Riepin et al.'s daily conservation constraint when W=24).

Array shape convention: (R, T) throughout, matching lp_model.py.

Baselines computed alongside the LP:
  - uniform  : demand split equally across all (region, hour) pairs
  - ci_only  : LP with α=0 (no CFE discount) — isolates CFE bonus
  - greedy   : sort (region, hour) by effective cost, fill greedily

Usage:
    python src/run_backtest.py                              # defaults
    python src/run_backtest.py --alpha 0.3 --window 48
    python src/run_backtest.py --alpha 0.5 --gamma 0.1 --eta 0.1
    python src/run_backtest.py --kappa 0.3 --rho 0.5       # with C6/C7
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from lp_model import solve, LPResult

# ---------------------------------------------------------------------------
# Zone definitions
# ---------------------------------------------------------------------------

ZONES = {
    "US-MIDA-PJM": "PJM",
    "US-NY-NYIS":  "NYISO",
    "FI":          "Finland",
    "BE":          "Belgium",
    "SG":          "Singapore",
}
LABELS = list(ZONES.values())
R = len(LABELS)

DATA_DIR    = Path(__file__).parent.parent / "data" / "raw"
RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    """
    Merge CI and CFE data for all zones into a single hourly DataFrame.

    CI  columns : ci_PJM, ci_NYISO, …
    CFE columns : cfe_PJM, cfe_NYISO, …  (falls back to 0 where unavailable)
    """
    ci_dfs, cfe_series = [], []

    for zone, label in ZONES.items():
        ci = pd.read_parquet(DATA_DIR / f"{zone}_ci.parquet")
        ci = ci.set_index("datetime")[["carbon_intensity"]].rename(
            columns={"carbon_intensity": f"ci_{label}"}
        )
        ci_dfs.append(ci)

        rf = pd.read_parquet(DATA_DIR / f"{zone}_rf.parquet").set_index("datetime")
        if "cfe_fraction" in rf.columns:
            col = rf["cfe_fraction"]
        elif "renewable_fraction" in rf.columns:
            col = rf["renewable_fraction"]
        else:
            col = pd.Series(dtype=float, name=f"cfe_{label}")
        cfe_series.append(col.rename(f"cfe_{label}"))

    df = ci_dfs[0].join(ci_dfs[1:], how="inner")
    cfe_df = pd.concat(cfe_series, axis=1)
    df = df.join(cfe_df, how="left")

    for label in LABELS:
        col = f"cfe_{label}"
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0).clip(0.0, 1.0)

    df.sort_index(inplace=True)
    return df


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def uniform_carbon(ci_win: np.ndarray, demand: float) -> tuple[np.ndarray, float]:
    """Uniform: demand / (R*T) at every (region, hour)."""
    R_loc, T = ci_win.shape
    x = np.full((R_loc, T), demand / (R_loc * T))
    return x, float(np.sum(x * ci_win))


def greedy_carbon(
    eff_cost: np.ndarray, ci_win: np.ndarray, demand: float, c_max: np.ndarray
) -> tuple[np.ndarray, float]:
    """Greedy: fill cheapest (region, hour) slots first. Arrays are (R, T)."""
    R_loc, T = eff_cost.shape
    x = np.zeros((R_loc, T))
    remaining = demand
    order = np.argsort(eff_cost.flatten())
    ub = np.repeat(c_max, T)   # (R*T,) — same cap for every hour
    for flat_idx in order:
        if remaining <= 0:
            break
        cap = ub[flat_idx] if not np.isinf(ub[flat_idx]) else remaining
        alloc = min(remaining, cap)
        x.flat[flat_idx] = alloc
        remaining -= alloc
    return x, float(np.sum(x * ci_win))


def _make_lp_inputs(
    ci_win: np.ndarray, cfe_win: np.ndarray,
    demand: float, window: int, c_max: np.ndarray,
) -> dict:
    """Build the common keyword arguments for lp_model.solve()."""
    R_loc = ci_win.shape[0]
    # All demand arrives at t=0; latency window = full horizon → C2 is slack.
    D_flex_batches = np.zeros(window)
    D_flex_batches[0] = demand
    return dict(
        CI             = ci_win,
        CFE            = cfe_win,
        D_flex_batches = D_flex_batches,
        C_min          = np.zeros(R_loc),
        C_max          = c_max,
        delta          = window,   # serve within full window
    )


# ---------------------------------------------------------------------------
# Backtest loop
# ---------------------------------------------------------------------------

def run_backtest(
    df     : pd.DataFrame,
    demand : float,
    alpha  : float,
    gamma  : float,
    eta    : float,
    sigma  : float,
    kappa  : float,
    rho    : float,
    window : int,
    c_max  : np.ndarray,
    r0     : int,
    solver : str,
) -> pd.DataFrame:
    ci_cols  = [f"ci_{l}"  for l in LABELS]
    cfe_cols = [f"cfe_{l}" for l in LABELS]

    # Load as (T_total, R) then transpose windows to (R, T)
    ci_all  = df[ci_cols].values.astype(float)
    cfe_all = df[cfe_cols].values.astype(float)
    T_total   = len(df)
    n_windows = T_total // window

    records = []

    for i in tqdm(range(n_windows), desc=f"W={window}h α={alpha}"):
        t0, t1 = i * window, (i + 1) * window

        # Transpose to (R, T) for lp_model
        ci_win  = ci_all[t0:t1].T   # (R, window)
        cfe_win = cfe_all[t0:t1].T  # (R, window)

        base_inputs = _make_lp_inputs(ci_win, cfe_win, demand, window, c_max)

        # Structural constraints shared by all LP variants
        struct = dict(sigma=sigma, kappa=kappa, rho=rho, r0=r0, solver=solver)

        # --- Main LP ---
        res = solve(**base_inputs, alpha=alpha, gamma=gamma, eta=eta, **struct)

        # --- CI-only LP (α=0, γ=0, η=0) — same structural constraints ---
        res0 = solve(**base_inputs, alpha=0.0, **struct)

        # --- Baselines ---
        x_uniform, carbon_uniform = uniform_carbon(ci_win, demand)
        eff_cost = ci_win * (1.0 - alpha * cfe_win)
        x_greedy, carbon_greedy = greedy_carbon(eff_cost, ci_win, demand, c_max)

        # --- Per-hour records (shape (R, T) → index [r, t]) ---
        for t_idx in range(window):
            abs_t = t0 + t_idx
            row: dict = {
                "datetime":  df.index[abs_t],
                "window_id": i,
            }
            for r_idx, label in enumerate(LABELS):
                row[f"x_lp_{label}"]      = res.x[r_idx, t_idx]
                row[f"x_ci_{label}"]      = res0.x[r_idx, t_idx]
                row[f"x_uniform_{label}"] = x_uniform[r_idx, t_idx]
                row[f"x_greedy_{label}"]  = x_greedy[r_idx, t_idx]
                row[f"ci_{label}"]        = ci_win[r_idx, t_idx]
                row[f"cfe_{label}"]       = cfe_win[r_idx, t_idx]

            row["carbon_lp"]      = float(np.sum(res.x[:, t_idx]  * ci_win[:, t_idx]))
            row["carbon_ci_only"] = float(np.sum(res0.x[:, t_idx] * ci_win[:, t_idx]))
            row["carbon_uniform"] = float(np.sum(x_uniform[:, t_idx] * ci_win[:, t_idx]))
            row["carbon_greedy"]  = float(np.sum(x_greedy[:, t_idx]  * ci_win[:, t_idx]))
            records.append(row)

        # Window-level aggregates on the last row of each window
        records[-1]["transfer_lp"]  = res.transfer
        records[-1]["equity_M_lp"]  = res.equity_M
        records[-1]["lp_status"]    = res.status
        records[-1]["carbon_greedy_window"] = carbon_greedy

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Summary + entry point
# ---------------------------------------------------------------------------

def print_summary(results: pd.DataFrame, args: argparse.Namespace) -> None:
    total_lp      = results["carbon_lp"].sum()
    total_uniform = results["carbon_uniform"].sum()
    total_ci_only = results["carbon_ci_only"].sum()
    total_greedy  = results["carbon_greedy"].sum()

    def pct_saved(base, opt):
        return (base - opt) / base * 100 if base > 0 else 0.0

    print("\n" + "=" * 58)
    print(f"  Backtest summary   α={args.alpha}  γ={args.gamma}  η={args.eta}")
    print(f"  W={args.window}h  κ={args.kappa}  ρ={args.rho}  σ={args.sigma}")
    print("=" * 58)
    print(f"  Hours covered      : {len(results):,}")
    print(f"  Uniform baseline   : {total_uniform:>14,.1f}  gCO2eq")
    print(f"  Greedy baseline    : {total_greedy:>14,.1f}  ({pct_saved(total_uniform, total_greedy):+.2f}%)")
    print(f"  CI-only LP (α=0)   : {total_ci_only:>14,.1f}  ({pct_saved(total_uniform, total_ci_only):+.2f}%)")
    print(f"  LP (α={args.alpha})         : {total_lp:>14,.1f}  ({pct_saved(total_uniform, total_lp):+.2f}%)")
    print(f"  CFE bonus vs CI-only   : {pct_saved(total_ci_only, total_lp):+.2f}%")

    n_windows = results["window_id"].nunique()
    transfer_col = results["transfer_lp"].dropna()
    if len(transfer_col):
        print(f"  Avg transfer/window    : {transfer_col.mean():,.2f}  kWh")
    print("=" * 58)


def main() -> None:
    parser = argparse.ArgumentParser(description="Carbon LP rolling-window backtest")
    parser.add_argument("--alpha",  type=float, default=0.5,
                        help="CFE discount α ∈ [0,1]  (default 0.5)")
    parser.add_argument("--gamma",  type=float, default=0.0,
                        help="Transfer cost coefficient  (default 0.0)")
    parser.add_argument("--eta",    type=float, default=0.0,
                        help="Equity weight η  (default 0.0)")
    parser.add_argument("--sigma",  type=float, default=1.0,
                        help="Max off-home fraction ∈ (0,1]  (default 1.0 = inactive)")
    parser.add_argument("--kappa",  type=float, default=1.0,
                        help="Ramp-rate cap as fraction of C_max  (default 1.0 = inactive)")
    parser.add_argument("--rho",    type=float, default=1.0,
                        help="Dynamic-range cap as fraction of C_max  (default 1.0 = inactive)")
    parser.add_argument("--window", type=int,   default=24,
                        help="Window size in hours  (default 24)")
    parser.add_argument("--demand", type=float, default=1.0,
                        help="Flexible demand per window  (default 1.0)")
    parser.add_argument("--c_max",  type=float, default=None,
                        help="Max load per region per hour; default = demand/R")
    parser.add_argument("--r0",     type=int,   default=0,
                        help="Home region index  (default 0 = PJM)")
    parser.add_argument("--solver", type=str,   default="highs",
                        choices=["highs", "gurobi"],
                        help="LP solver backend  (default highs)")
    args = parser.parse_args()

    c_max = (
        np.full(R, args.c_max)
        if args.c_max is not None
        else np.full(R, args.demand)
    )

    print("Loading data …")
    df = load_data()
    print(f"  {len(df):,} hours  |  {df.index.min().date()} → {df.index.max().date()}")
    cfe_coverage = {l: int((df[f"cfe_{l}"] > 0).sum()) for l in LABELS}
    print(f"  CFE coverage (non-zero hours): {cfe_coverage}")

    results = run_backtest(
        df, demand=args.demand, alpha=args.alpha,
        gamma=args.gamma, eta=args.eta, sigma=args.sigma,
        kappa=args.kappa, rho=args.rho,
        window=args.window, c_max=c_max,
        r0=args.r0, solver=args.solver,
    )

    print_summary(results, args)

    tag = f"alpha{args.alpha}_W{args.window}_g{args.gamma}_e{args.eta}"
    if args.kappa < 1.0:
        tag += f"_k{args.kappa}"
    if args.rho < 1.0:
        tag += f"_r{args.rho}"
    out = RESULTS_DIR / f"lp_backtest_{tag}.parquet"
    results.to_parquet(out, index=False)
    print(f"\n  Saved → {out}")


if __name__ == "__main__":
    main()
