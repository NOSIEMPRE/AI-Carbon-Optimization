"""
Sensitivity sweep for carbon-aware LP.

Outputs
-------
data/results/sensitivity_sweep.csv     one row per (param, value, season)
data/results/baseline_backtest.parquet per-window LP + heuristic carbon totals
data/results/schedule_sample.parquet   per-hour schedule for one representative week

Heuristics compared
-------------------
  uniform : demand / (R*T) at every slot
  fcfs    : fill earliest slots first within deadline, ignoring carbon
  greedy  : sort by effective cost CI*(1-α*CFE), fill cheapest slots first
  oracle  : LP solved over W=168h window (extended look-ahead upper bound)
  lp      : LP solved over W=24h rolling window (this model)

Usage
-----
    python src/run_sensitivity.py            # full 2-yr run
    python src/run_sensitivity.py --fast     # 4-week sample for quick testing
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from lp_model import solve

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZONES = {
    "US-MIDA-PJM": "PJM",
    "US-NY-NYIS":  "NYISO",
    "FI":          "Finland",
    "BE":          "Belgium",
    "SG":          "Singapore",
}
LABELS  = list(ZONES.values())
R       = len(LABELS)
DATA_DIR    = Path(__file__).parent.parent / "data" / "raw"
RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

BASELINE = dict(alpha=0.5, gamma=0.0, eta=0.0, sigma=1.0,
                kappa=1.0, rho=1.0, delta=24)

SWEEPS = {
    "alpha": [0.0, 0.25, 0.5, 0.75, 1.0],
    "sigma": [0.3, 0.5, 0.7, 0.9, 1.0],
    "delta": [6, 12, 24, 48],
    "kappa": [0.1, 0.2, 0.5, 0.8, 1.0],
    "rho":   [0.2, 0.4, 0.6, 0.8, 1.0],
    "eta":   [0.0, 0.1, 0.3, 0.5, 1.0],
}

SEASON_MAP = {12: "DJF", 1: "DJF", 2: "DJF",
              3:  "MAM", 4: "MAM", 5: "MAM",
              6:  "JJA", 7: "JJA", 8: "JJA",
              9:  "SON", 10:"SON", 11:"SON"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
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
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def fast_sample(df: pd.DataFrame) -> pd.DataFrame:
    """One representative week per season (168 h each = 672 h total)."""
    parts = []
    for month in [1, 4, 7, 10]:
        mask = (df.index.month == month) & (df.index.year == df.index.year.min())
        chunk = df[mask].iloc[:168]
        if len(chunk) == 168:
            parts.append(chunk)
    return pd.concat(parts) if parts else df.iloc[:672]


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

def uniform_carbon(ci_win: np.ndarray, demand: float) -> tuple[np.ndarray, float]:
    T = ci_win.shape[1]
    x = np.full((R, T), demand / (R * T))
    return x, float((x * ci_win).sum())


def fcfs_carbon(ci_win: np.ndarray, demand: float,
                c_max: np.ndarray, delta: int) -> tuple[np.ndarray, float]:
    """
    First-Come-First-Served: fill demand into the earliest available slots,
    home region first, within the deadline window. Ignores carbon entirely.
    This represents a naive scheduler with no carbon awareness.
    """
    T = ci_win.shape[1]
    x = np.zeros((R, T))
    remaining = demand
    # Fill home region (r=0) first, then others, slot by slot in time order
    for t in range(min(delta, T)):
        for r in range(R):
            if remaining <= 0:
                break
            alloc = min(remaining, c_max[r])
            x[r, t] += alloc
            remaining -= alloc
        if remaining <= 0:
            break
    return x, float((x * ci_win).sum())


def greedy_carbon(ci_win: np.ndarray, cfe_win: np.ndarray,
                  demand: float, alpha: float, gamma: float,
                  c_max: np.ndarray, r0: int = 0) -> tuple[np.ndarray, float]:
    """Sort region-hour pairs by effective cost; fill cheapest first."""
    T = ci_win.shape[1]
    eff = ci_win * (1.0 - alpha * cfe_win)
    eff[[r for r in range(R) if r != r0]] += gamma
    x = np.zeros((R, T))
    remaining = demand
    order = np.argsort(eff.flatten())
    for flat_idx in order:
        if remaining <= 0:
            break
        r_i = flat_idx // T
        alloc = min(remaining, c_max[r_i])
        x.flat[flat_idx] = alloc
        remaining -= alloc
    return x, float((x * ci_win).sum())


def lp_carbon(ci_win: np.ndarray, cfe_win: np.ndarray,
              demand: float, window: int, c_max: np.ndarray,
              alpha: float, gamma: float, eta: float,
              sigma: float, kappa: float, rho: float,
              delta: int, r0: int = 0):
    """Solve the LP for one window."""
    D_flex = np.zeros(window)
    D_flex[0] = demand
    res = solve(CI=ci_win, CFE=cfe_win, D_flex_batches=D_flex,
                C_min=np.zeros(R), C_max=c_max,
                alpha=alpha, gamma=gamma, eta=eta,
                delta=delta, sigma=sigma, kappa=kappa, rho=rho, r0=r0)
    return res.x, res.carbon


# ---------------------------------------------------------------------------
# Rolling-window backtest for one parameter setting
# ---------------------------------------------------------------------------

def run_backtest(df: pd.DataFrame, window: int, demand: float,
                 alpha: float, gamma: float, eta: float,
                 sigma: float, kappa: float, rho: float, delta: int,
                 oracle_window: int = 168,
                 save_schedule_month: int = 7) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """
    Run rolling-window LP + all heuristics over df.

    Returns
    -------
    df_win  : per-window aggregate results
    df_sched: per-hour schedule for the first week of save_schedule_month (or None)
    """
    ci_cols  = [f"ci_{l}"  for l in LABELS]
    cfe_cols = [f"cfe_{l}" for l in LABELS]
    ci_all   = df[ci_cols].values.astype(float)
    cfe_all  = df[cfe_cols].values.astype(float)
    T_total  = len(df)
    n_win    = T_total // window
    c_max    = np.full(R, demand)

    records  = []
    sched_rows = []
    sched_saved = False

    for i in range(n_win):
        t0, t1 = i * window, (i + 1) * window
        ci_win  = ci_all[t0:t1].T   # (R, W)
        cfe_win = cfe_all[t0:t1].T
        dt      = df.index[t0]
        season  = SEASON_MAP[dt.month]

        # LP (rolling window)
        x_lp, c_lp = lp_carbon(ci_win, cfe_win, demand, window, c_max,
                                alpha, gamma, eta, sigma, kappa, rho, delta)

        # Heuristics
        x_unif, c_unif = uniform_carbon(ci_win, demand)
        x_fcfs, c_fcfs = fcfs_carbon(ci_win, demand, c_max, delta)
        x_gr,   c_gr   = greedy_carbon(ci_win, cfe_win, demand,
                                       alpha, gamma, c_max)

        # Oracle: LP over extended window (oracle_window hours centred here)
        # We use the next oracle_window hours if available, else skip
        if t0 + oracle_window <= T_total and oracle_window > window:
            ci_orc  = ci_all[t0:t0 + oracle_window].T
            cfe_orc = cfe_all[t0:t0 + oracle_window].T
            c_max_orc = np.full(R, demand * (oracle_window / window))
            _, c_orc_full = lp_carbon(ci_orc, cfe_orc,
                                      demand * (oracle_window / window),
                                      oracle_window, c_max_orc,
                                      alpha, gamma, eta, sigma, kappa, rho,
                                      oracle_window)
            # Normalise back to per-window-equivalent
            c_orc = c_orc_full * window / oracle_window
        else:
            c_orc = c_lp   # fallback: same as LP

        records.append({
            "datetime":      dt,
            "season":        season,
            "carbon_lp":     c_lp,
            "carbon_uniform": c_unif,
            "carbon_fcfs":   c_fcfs,
            "carbon_greedy": c_gr,
            "carbon_oracle": c_orc,
            **{f"carbon_{lab}": float((x_lp[r] * ci_win[r]).sum())
               for r, lab in enumerate(LABELS)},
            **{f"x_lp_{lab}":   float(x_lp[r].sum())
               for r, lab in enumerate(LABELS)},
        })

        # Save per-hour schedule for one representative week (for visualization)
        if not sched_saved and dt.month == save_schedule_month and window <= 168:
            for h in range(window):
                row = {"datetime": df.index[t0 + h],
                       "ci_min":  float(ci_win[:, h].min())}
                for r, lab in enumerate(LABELS):
                    row[f"x_lp_{lab}"]      = float(x_lp[r, h])
                    row[f"x_fcfs_{lab}"]    = float(x_fcfs[r, h])
                    row[f"x_greedy_{lab}"]  = float(x_gr[r, h])
                    row[f"x_uniform_{lab}"] = float(x_unif[r, h])
                    row[f"ci_{lab}"]        = float(ci_win[r, h])
                    row[f"cfe_{lab}"]       = float(cfe_win[r, h])
                sched_rows.append(row)
            sched_saved = True

    df_win   = pd.DataFrame(records)
    df_sched = pd.DataFrame(sched_rows) if sched_rows else None
    return df_win, df_sched


# ---------------------------------------------------------------------------
# Aggregate helper
# ---------------------------------------------------------------------------

def aggregate(df_win: pd.DataFrame, param_name: str,
              param_value, subset: str = "ALL") -> dict | None:
    if subset != "ALL":
        df_win = df_win[df_win["season"] == subset]
    if len(df_win) == 0:
        return None
    c_lp   = df_win["carbon_lp"].sum()
    c_unif = df_win["carbon_uniform"].sum()
    c_gr   = df_win["carbon_greedy"].sum()
    c_fcfs = df_win["carbon_fcfs"].sum()
    c_orc  = df_win["carbon_oracle"].sum()

    def pct(base, opt):
        return (base - opt) / base * 100 if base > 0 else 0.0

    rec = {
        "param":              param_name,
        "value":              param_value,
        "season":             subset,
        "windows":            len(df_win),
        "carbon_lp":          c_lp,
        "carbon_uniform":     c_unif,
        "carbon_greedy":      c_gr,
        "carbon_fcfs":        c_fcfs,
        "carbon_oracle":      c_orc,
        "saving_lp_pct":      pct(c_unif, c_lp),
        "saving_greedy_pct":  pct(c_unif, c_gr),
        "saving_fcfs_pct":    pct(c_unif, c_fcfs),
        "saving_oracle_pct":  pct(c_unif, c_orc),
    }
    for lab in LABELS:
        col = f"carbon_{lab}"
        if col in df_win.columns:
            rec[f"share_{lab}_pct"] = (df_win[col].sum() / c_lp * 100
                                       if c_lp > 0 else 0)
    return rec


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast",   action="store_true",
                        help="4-week sample for quick testing")
    parser.add_argument("--window", type=int,   default=24)
    parser.add_argument("--demand", type=float, default=1.0)
    args = parser.parse_args()

    print("Loading data …")
    df = load_data()
    print(f"  {len(df):,} hours  |  {df.index.min().date()} → {df.index.max().date()}")

    if args.fast:
        df = fast_sample(df)
        print(f"  Fast mode: {len(df)} hours (4 representative weeks)")

    window = args.window
    demand = args.demand
    seasons = ["ALL", "DJF", "MAM", "JJA", "SON"]
    bl = BASELINE

    # ── Baseline backtest (all heuristics + schedule export) ────────────────
    print("\nRunning baseline backtest …")
    df_bl, df_sched = run_backtest(
        df, window, demand,
        alpha=bl["alpha"], gamma=bl["gamma"], eta=bl["eta"],
        sigma=bl["sigma"], kappa=bl["kappa"], rho=bl["rho"],
        delta=bl["delta"],
    )
    df_bl.to_parquet(RESULTS_DIR / "baseline_backtest.parquet", index=False)
    if df_sched is not None:
        df_sched.to_parquet(RESULTS_DIR / "schedule_sample.parquet", index=False)
        print(f"  Schedule sample (unconstrained): {len(df_sched)} hours saved")

    # ── Constrained schedule sample (C6 + C7 active) for F0 comparison ──────
    print("Running constrained schedule sample (κ=0.2, ρ=0.4) …")
    _, df_sched_c = run_backtest(
        df, window, demand,
        alpha=bl["alpha"], gamma=bl["gamma"], eta=bl["eta"],
        sigma=bl["sigma"], kappa=0.2, rho=0.4,
        delta=bl["delta"],
    )
    if df_sched_c is not None:
        df_sched_c.to_parquet(RESULTS_DIR / "schedule_sample_constrained.parquet",
                              index=False)
        print(f"  Schedule sample (constrained): {len(df_sched_c)} hours saved")

    sweep_records = []
    for s in seasons:
        rec = aggregate(df_bl, "baseline", "baseline", subset=s)
        if rec:
            sweep_records.append(rec)

    # ── Parameter sweeps ────────────────────────────────────────────────────
    for param_name, values in SWEEPS.items():
        print(f"\nSweeping {param_name} …")
        for val in tqdm(values, desc=param_name):
            params = dict(bl)
            params[param_name] = val
            df_run, _ = run_backtest(
                df, window, demand,
                alpha=params["alpha"], gamma=params["gamma"], eta=params["eta"],
                sigma=params["sigma"], kappa=params["kappa"], rho=params["rho"],
                delta=params["delta"],
            )
            for s in seasons:
                rec = aggregate(df_run, param_name, val, subset=s)
                if rec:
                    sweep_records.append(rec)

    pd.DataFrame(sweep_records).to_csv(
        RESULTS_DIR / "sensitivity_sweep.csv", index=False)

    # ── Summary ─────────────────────────────────────────────────────────────
    bl_all = next(r for r in sweep_records
                  if r["param"] == "baseline" and r["season"] == "ALL")
    print(f"\nBaseline (W={window}h):")
    print(f"  LP     : {bl_all['saving_lp_pct']:.1f}% saving vs uniform")
    print(f"  Greedy : {bl_all['saving_greedy_pct']:.1f}%")
    print(f"  FCFS   : {bl_all['saving_fcfs_pct']:.1f}%")
    print(f"  Oracle : {bl_all['saving_oracle_pct']:.1f}%")


if __name__ == "__main__":
    main()
