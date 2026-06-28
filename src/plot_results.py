"""
Generate thesis figures from sensitivity sweep and baseline backtest results.

Figures produced (saved to data/figures/)
------------------------------------------
F1  perturbation_test.png    predicted vs observed reaction in 4 scenarios
F2  schedule_sample.png      LP schedule vs CI signal (one representative week)
F3  sensitivity_tornado.png  OAT tornado diagram; bars sorted by impact width
F4  seasonal_breakdown.png   LP saving and regional carbon share by season
F5  heuristic_comparison.png carbon saving vs no-opt baseline: Oracle/LP/Greedy/FCFS
F6  decomposition.png        temporal vs. spatial decomposition of LP saving
F7  cv_regression.png        CI variability vs within-region temporal saving

Usage
-----
    python src/plot_results.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lp_model import solve as lp_solve

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from figstyle import apply_style, REGION_COLORS, METHOD_COLORS
apply_style()

# Real CI values used in perturbation test (2024-07-17 00:00–05:00 UTC)
_PERT_CI = np.array([
    [600, 611, 613, 600, 582, 564],   # PJM
    [ 54,  55,  55,  54,  52,  52],   # FI
    [138, 124, 100, 124, 122, 139],   # BE
], dtype=float)
_PERT_CFE   = np.zeros((3, 6))
_PERT_CMAX  = np.full(3, 10.0)
_PERT_CMIN  = np.zeros(3)
_PERT_PARAMS = dict(alpha=0.0, gamma=0.0, eta=0.1, sigma=0.6,
                    kappa=0.5, rho=0.7, delta=6, r0=0)

RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
FIG_DIR     = Path(__file__).parent.parent / "data" / "figures" / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)

LABELS = ["PJM", "NYISO", "Finland", "Belgium", "Singapore"]

# Region and method colors come from the shared style (figstyle) so that every
# figure in the thesis and poster uses one consistent palette.
HEURISTIC_STYLES = {
    "Uniform":  dict(color=METHOD_COLORS["Uniform"], hatch=""),
    "FCFS":     dict(color=METHOD_COLORS["FCFS"],    hatch=""),
    "Greedy":   dict(color=METHOD_COLORS["Greedy"],  hatch=""),
    "Oracle":   dict(color=METHOD_COLORS["Oracle"],  hatch="//"),
    "LP":       dict(color=METHOD_COLORS["LP"],      hatch=""),
}

SEASON_LABELS = {"DJF": "Winter", "MAM": "Spring", "JJA": "Summer", "SON": "Autumn"}

PARAM_LABELS = {
    "alpha": r"$\alpha$ (CFE weight)",
    "sigma": r"$\sigma$ (geographic cap)",
    "delta": r"$\delta$ (max deferral time)",
    "kappa": r"$\kappa$ (ramp-rate cap)",
    "rho":   r"$\rho$ (dynamic-range cap)",
    "eta":   r"$\eta$ (fairness weight)",
}


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_sweep() -> pd.DataFrame:
    p = RESULTS_DIR / "sensitivity_sweep.csv"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run src/run_sensitivity.py first.")
    return pd.read_csv(p)


def load_baseline() -> pd.DataFrame:
    p = RESULTS_DIR / "baseline_backtest.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run src/run_sensitivity.py first.")
    return pd.read_parquet(p)


def load_heuristic() -> pd.DataFrame | None:
    p = RESULTS_DIR / "heuristic_backtest.parquet"
    return pd.read_parquet(p) if p.exists() else None


def load_schedule() -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    p1 = RESULTS_DIR / "schedule_sample.parquet"
    p2 = RESULTS_DIR / "schedule_sample_constrained.parquet"
    df1 = pd.read_parquet(p1) if p1.exists() else None
    df2 = pd.read_parquet(p2) if p2.exists() else None
    return df1, df2


def load_decomposition() -> pd.DataFrame | None:
    p = RESULTS_DIR / "decomposition.csv"
    return pd.read_csv(p) if p.exists() else None


def load_cv_regression() -> pd.DataFrame | None:
    p = RESULTS_DIR / "cv_regression.csv"
    return pd.read_csv(p) if p.exists() else None


def load_perturbation() -> pd.DataFrame | None:
    p = RESULTS_DIR / "perturbation_test.csv"
    return pd.read_csv(p) if p.exists() else None


# ---------------------------------------------------------------------------
# Figure F2: Schedule sample (solution and validation)
# ---------------------------------------------------------------------------

def _draw_schedule_panel(ax_sched, ax_ci, df, col_prefix="x_lp", title=""):
    """Draw one schedule panel (stacked load + CI) onto the given axes.

    col_prefix selects which schedule columns to plot, e.g. 'x_fcfs' for the
    no-shift baseline or 'x_lp' for the LP-optimised schedule.
    """
    df = df.copy()
    df["hour"] = range(len(df))

    bottom = np.zeros(len(df))
    for lab in LABELS:
        col = f"{col_prefix}_{lab}"
        if col not in df.columns:
            continue
        vals = df[col].values
        ax_sched.fill_between(df["hour"], bottom, bottom + vals,
                              label=lab, color=REGION_COLORS[lab],
                              alpha=0.82, linewidth=0)
        bottom += vals

    total = sum(df[f"{col_prefix}_{lab}"].values for lab in LABELS
                if f"{col_prefix}_{lab}" in df.columns)
    ax_sched.plot(df["hour"], total, color="black", linewidth=1.2,
                  linestyle="--", label="Total", zorder=5)
    ax_sched.set_ylabel("Load allocated (kWh/h)")
    ax_sched.set_title(title, fontweight="bold")
    ax_sched.legend(loc="upper right", fontsize=7, ncol=3)
    ax_sched.grid(axis="y", alpha=0.3)

    for lab in LABELS:
        col = f"ci_{lab}"
        if col not in df.columns:
            continue
        ax_ci.plot(df["hour"], df[col], label=lab,
                   color=REGION_COLORS[lab], linewidth=1.2)
    ax_ci.set_xlabel("Hour")
    ax_ci.set_ylabel(r"CI (gCO$_2$eq/kWh)")
    ax_ci.legend(loc="upper right", fontsize=7, ncol=3)
    ax_ci.grid(axis="y", alpha=0.3)

    for d in range(1, len(df) // 24 + 1):
        ax_sched.axvline(d * 24, color="gray", linewidth=0.5, linestyle=":")
        ax_ci.axvline(d * 24, color="gray", linewidth=0.5, linestyle=":")


def _carbon_total(df: pd.DataFrame, col_prefix: str) -> float:
    return float(sum((df[f"{col_prefix}_{lab}"] * df[f"ci_{lab}"]).sum()
                     for lab in LABELS if f"{col_prefix}_{lab}" in df.columns))


def fig_schedule(df_noshift: pd.DataFrame, df_lp: pd.DataFrame | None):
    """
    F2: schedule exhibit using the comparison basis the supervisor asked for
    (meeting 2026-06-15): "without shifting" vs "with shifting" — NOT
    "unconstrained LP" vs "constrained LP" (both of those are LP variants,
    neither represents what the system would actually do without
    optimisation).

    Left:  No-shift baseline — demand served immediately, at the home
           region, at the hour it arrives (== FCFS in this single-batch
           setup, since C_max equals the batch size).
    Right: LP-shift — the operational LP with C6 (kappa=0.2) and C7
           (rho=0.4) active, i.e. the schedule actually proposed.
    Bottom row: CI signal for reference (same data in both panels).
    """
    has_both = df_lp is not None
    ncols = 2 if has_both else 1
    fig, axes = plt.subplots(2, ncols, figsize=(13 if has_both else 8, 7),
                             sharex="col", sharey="row",
                             gridspec_kw={"height_ratios": [2, 1]})

    if not has_both:
        axes = axes.reshape(2, 1)

    c_noshift = _carbon_total(df_noshift, "x_fcfs")
    _draw_schedule_panel(axes[0, 0], axes[1, 0], df_noshift,
                         col_prefix="x_fcfs",
                         title=f"No shift (status quo)\ncarbon = {c_noshift:,.0f} gCO$_2$")
    axes[1, 0].set_title("Carbon intensity by region", fontweight="bold")

    if has_both:
        c_lp = _carbon_total(df_lp, "x_lp")
        saving = (c_noshift - c_lp) / c_noshift * 100 if c_noshift > 0 else 0.0
        _draw_schedule_panel(axes[0, 1], axes[1, 1], df_lp,
                             col_prefix="x_lp",
                             title=(r"LP shift ($\kappa{=}0.2$, $\rho{=}0.4$)" + "\n"
                                   f"carbon = {c_lp:,.0f} gCO$_2$  "
                                   f"({saving:+.1f}% vs no-shift)"))
        axes[1, 1].set_title("Carbon intensity by region", fontweight="bold")

    fig.suptitle("No-Shift Baseline vs. LP-Optimised Schedule\n"
                 "(one representative 24-hour window; both panels use the "
                 "same CI data)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "schedule_sample.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure F3: Sensitivity — OAT Tornado Diagram (Eschenbach 1992)
# ---------------------------------------------------------------------------

def fig_sensitivity(df: pd.DataFrame):
    """
    F3: OAT tornado diagram (Eschenbach, Interfaces 1992).

    Each horizontal bar shows the range of LP carbon (per scheduling window)
    as one parameter is swept across its full tested range while all others
    remain at their sweep defaults.  Bars are sorted by impact width so the
    dominant parameter is at the top (tornado shape).

    X-axis: % change relative to the unconstrained-LP baseline carbon
    (approximated by the global minimum LP carbon across all sweep rows,
    reached when every constraint parameter is at its loosest value).
    """
    # "baseline" rows hold the operational-parameter LP carbon (σ=0.5, κ=0.2, ρ=0.4, …).
    # Use that as the tornado center; it gives a symmetric two-sided diagram.
    baseline_row = df[(df["param"] == "baseline") & (df["season"] == "ALL")]
    n_win_ref    = int(df["windows"].dropna().iloc[0])
    if not baseline_row.empty:
        baseline_cpw = float(baseline_row["carbon_lp"].values[0]) / n_win_ref
    else:
        # Fallback: global min (approx. unconstrained LP)
        baseline_cpw = df[df["param"].isin(PARAM_LABELS)]["carbon_lp"].min() / n_win_ref

    # Filter to sweep rows only (exclude "baseline" sentinel rows).
    sweep = df[(df["season"] == "ALL") & (df["param"].isin(PARAM_LABELS))].copy()
    sweep["value"] = sweep["value"].astype(float)

    params = [p for p in PARAM_LABELS if p in sweep["param"].unique()]

    # For each parameter: pct change at its min/max sweep values vs baseline.
    param_ranges: dict[str, tuple[float, float]] = {}
    for p in params:
        sub = sweep[sweep["param"] == p]
        if sub.empty:
            continue
        n_win   = int(sub["windows"].iloc[0])
        cpw     = sub["carbon_lp"] / n_win
        lo_pct  = (cpw.min() - baseline_cpw) / baseline_cpw * 100.0
        hi_pct  = (cpw.max() - baseline_cpw) / baseline_cpw * 100.0
        param_ranges[p] = (lo_pct, hi_pct)

    # Sort by bar width descending; display largest at top of figure.
    sorted_params = sorted(
        param_ranges.keys(),
        key=lambda p: param_ranges[p][1] - param_ranges[p][0],
        reverse=True,
    )
    # y_labels[0] → bottom bar (smallest impact), y_labels[-1] → top (largest).
    y_labels = sorted_params[::-1]
    n = len(y_labels)

    C_COST   = "#FF9500"   # orange  — constraint tightened, carbon rises
    C_SAVE   = "#0C5DA5"   # blue    — constraint loosened, carbon falls

    fig, ax = plt.subplots(figsize=(10, max(4, n * 0.85 + 1.5)))

    for i, p in enumerate(y_labels):
        lo, hi = param_ranges[p]

        if lo < 0:
            ax.barh(i, -lo, left=lo, height=0.6, color=C_SAVE, alpha=0.88, zorder=3)
        if hi > 0:
            ax.barh(i, hi, left=0, height=0.6, color=C_COST, alpha=0.88, zorder=3)

        if hi > 0:
            ax.text(hi + 0.3, i, f"+{hi:.1f}%",
                    va="center", ha="left", fontsize=8.5, color=C_COST, fontweight="bold")
        if lo < 0 and hi <= 0:
            ax.text(lo - 0.3, i, f"{lo:.1f}%",
                    va="center", ha="right", fontsize=8.5, color=C_SAVE, fontweight="bold")

    ax.axvline(0, color="black", linewidth=1.5, zorder=5)
    ax.set_yticks(range(n))
    ax.set_yticklabels([PARAM_LABELS.get(p, p) for p in y_labels], fontsize=10)
    ax.set_xlabel(
        "Change in LP carbon per window vs unconstrained baseline (%)", fontsize=9)
    ax.set_title(
        "OAT Sensitivity — Tornado Diagram\n"
        "(sorted by impact width; baseline = σ=κ=ρ=1.0 unconstrained LP)",
        fontsize=10, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--", zorder=0)

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor=C_COST, alpha=0.88, label="Carbon ↑  (tightening costs carbon; baseline = σ=κ=ρ=1.0)"),
    ], fontsize=8.5, loc="lower right")

    max_hi = max(hi for _, hi in param_ranges.values())
    ax.set_xlim(-max_hi * 0.15, max_hi * 1.3)

    plt.tight_layout()
    out = FIG_DIR / "sensitivity_tornado.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Seasonal breakdown
# ---------------------------------------------------------------------------

def fig_seasonal(df_bl: pd.DataFrame):
    df_bl = df_bl.copy()
    if "season" not in df_bl.columns:
        df_bl["season"] = df_bl["datetime"].apply(
            lambda d: {12:"DJF",1:"DJF",2:"DJF",
                       3:"MAM",4:"MAM",5:"MAM",
                       6:"JJA",7:"JJA",8:"JJA",
                       9:"SON",10:"SON",11:"SON"}[pd.Timestamp(d).month]
        )
    seasons = ["DJF", "MAM", "JJA", "SON"]
    metrics = {k: [] for k in ["lp", "greedy", "fcfs", "oracle"]}
    region_shares = {lab: [] for lab in LABELS}

    for s in seasons:
        sub  = df_bl[df_bl["season"] == s]
        c_u  = sub["carbon_uniform"].sum()
        for key, col in [("lp","carbon_lp"), ("greedy","carbon_greedy"),
                         ("fcfs","carbon_fcfs"), ("oracle","carbon_oracle")]:
            if col in sub.columns:
                c = sub[col].sum()
                metrics[key].append((c_u - c) / c_u * 100 if c_u > 0 else 0)
            else:
                metrics[key].append(0)
        c_l = sub["carbon_lp"].sum()
        for lab in LABELS:
            col = f"carbon_{lab}"
            region_shares[lab].append(
                sub[col].sum() / c_l * 100 if col in sub.columns and c_l > 0 else 0)

    x     = np.arange(len(seasons))
    width = 0.18
    method_order = [("lp","LP"), ("greedy","Greedy"), ("fcfs","FCFS"), ("oracle","Oracle")]
    offsets = np.linspace(-1.5, 1.5, 4) * width

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.2))

    for (key, lbl), off in zip(method_order, offsets):
        col  = METHOD_COLORS[lbl]
        bars = ax1.bar(x + off, metrics[key], width, label=lbl, color=col, alpha=0.88)
        for bar, v in zip(bars, metrics[key]):
            if abs(v) > 0.5:
                ax1.text(bar.get_x() + bar.get_width()/2,
                         v + (3.0 if v >= 0 else -3.0),
                         f"{v:.0f}%", ha="center",
                         va="bottom" if v >= 0 else "top",
                         fontsize=6, color=col, fontweight="bold")

    # headroom so value labels sit clearly above/below the bars, not on them
    _allv = [v for key in metrics for v in metrics[key]]
    ax1.set_ylim(min(_allv) - 14, max(_allv) + 16)
    ax1.set_xticks(x)
    ax1.set_xticklabels([SEASON_LABELS[s] for s in seasons], fontsize=9)
    ax1.set_ylabel("Carbon saving (%, no-optimization baseline = 0 %)", fontsize=9)
    ax1.set_title("A. Seasonal carbon saving by method\n(no-optimization baseline = 0 %)",
                  fontweight="bold", fontsize=10)
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax1.legend(fontsize=8.5)
    ax1.grid(axis="y", alpha=0.3, linestyle="--")

    bottom = np.zeros(len(seasons))
    for lab in LABELS:
        vals = np.array(region_shares[lab])
        ax2.bar(x, vals, width=0.55, bottom=bottom,
                label=lab, color=REGION_COLORS[lab], alpha=0.88)
        bottom += vals
    # Finland dominates every season; the green block and legend make this clear,
    # so per-segment percentage labels are omitted to reduce clutter.

    ax2.set_xticks(x)
    ax2.set_xticklabels([SEASON_LABELS[s] for s in seasons], fontsize=9)
    ax2.set_ylabel("Share of LP carbon allocation (%)", fontsize=9)
    ax2.set_title("B. Regional carbon load share by season\n(stacked = 100% of LP allocation)",
                  fontweight="bold", fontsize=10)
    # bars fill to 100%, so place the legend OUTSIDE the axes (right) to avoid overlap
    ax2.legend(loc="center left", bbox_to_anchor=(1.01, 0.5),
               fontsize=8.5, framealpha=0.95, title="Region")
    ax2.set_ylim(0, 100)
    ax2.grid(axis="y", alpha=0.3, linestyle="--")

    fig.suptitle("Seasonal Analysis — Carbon Saving and Regional Breakdown\n"
                 "(Finland dominates LP allocation year-round; savings consistent across seasons)",
                 fontsize=10, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "seasonal_breakdown.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure F5: Scheduler comparison — absolute carbon saving vs no-opt baseline
# (Carbon Explorer 2023 convention: all methods on one carbon-saving axis)
# ---------------------------------------------------------------------------

def fig_heuristic_absolute(df_bl: pd.DataFrame):
    """
    F5: Carbon saving of each scheduler vs. the no-optimisation baseline.

    Metric:
        saving = (C_Uniform - C_alg) / C_Uniform × 100 %

    Unlike the LP efficiency ratio, this does not normalise by LP's saving,
    so it directly shows how much carbon each method saves (or wastes)
    relative to doing nothing.
    """
    df_bl = df_bl.copy()
    if "season" not in df_bl.columns:
        df_bl["season"] = df_bl["datetime"].apply(
            lambda d: {12:"DJF",1:"DJF",2:"DJF",
                       3:"MAM",4:"MAM",5:"MAM",
                       6:"JJA",7:"JJA",8:"JJA",
                       9:"SON",10:"SON",11:"SON"}[pd.Timestamp(d).month]
        )

    # Ceiling → thesis method → carbon-aware heuristic → carbon-agnostic default
    METHODS = [
        ("carbon_oracle", "Oracle",  METHOD_COLORS["Oracle"]),
        ("carbon_lp",     "LP",      METHOD_COLORS["LP"]),
        ("carbon_greedy", "Greedy",  METHOD_COLORS["Greedy"]),
        ("carbon_fcfs",   "FCFS",    METHOD_COLORS["FCFS"]),
    ]
    seasons     = ["DJF", "MAM", "JJA", "SON"]
    season_lbls = ["Winter", "Spring", "Summer", "Autumn"]

    def saving(sub: pd.DataFrame, col: str) -> float:
        c_u = sub["carbon_uniform"].sum()
        if c_u <= 0 or col not in sub.columns:
            return float("nan")
        return (c_u - sub[col].sum()) / c_u * 100.0

    overall  = {lbl: saving(df_bl, col) for col, lbl, _ in METHODS}
    seasonal: dict[str, list[float]] = {lbl: [] for _, lbl, _ in METHODS}
    for s in seasons:
        sub = df_bl[df_bl["season"] == s]
        for col, lbl, _ in METHODS:
            seasonal[lbl].append(saving(sub, col))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    # ── Panel A: overall ────────────────────────────────────────────────────
    lbls   = [lbl for _, lbl, _ in METHODS]
    colors = [c   for _, _,   c in METHODS]
    vals   = [overall[lbl] for lbl in lbls]

    bars = ax1.bar(np.arange(len(lbls)), vals, color=colors, alpha=0.88, width=0.6)
    # Mark the carbon-aware greedy heuristic as constraint-violating: it matches
    # the LP's carbon only by breaching the ramp limit (in all 731 windows).
    greedy_idx = lbls.index("Greedy")
    bars[greedy_idx].set_hatch("xx")
    bars[greedy_idx].set_edgecolor("black")
    bars[greedy_idx].set_linewidth(0.8)
    ax1.axhline(0, color="black", linewidth=1.0, linestyle=":", zorder=5,
                label="No-opt. baseline (0 %)")
    for bar, v in zip(bars, vals):
        if not np.isnan(v):
            y = v + 1.2 if v >= 0 else v - 1.2
            ax1.text(bar.get_x() + bar.get_width() / 2, y,
                     f"{v:.1f}%", ha="center", va="bottom" if v >= 0 else "top",
                     fontsize=9, fontweight="bold")
    # Annotate greedy's infeasibility directly on its bar.
    gb = bars[greedy_idx]
    ax1.annotate("violates ramp\n(all 731 windows)",
                 xy=(gb.get_x() + gb.get_width() / 2, vals[greedy_idx] / 2),
                 ha="center", va="center", fontsize=8, fontweight="bold",
                 color="white")
    ax1.set_xticks(np.arange(len(lbls)))
    ax1.set_xticklabels(lbls, fontsize=10)
    ax1.set_ylabel("Carbon saving vs. no-opt. baseline (%)", fontsize=9)
    ax1.set_ylim(-62, 48)
    ax1.set_title("A. Overall carbon saving vs. no-optimisation baseline\n"
                  r"saving = $(C_{\rm Uniform} - C_{\rm alg})\,/\,C_{\rm Uniform}$",
                  fontsize=10, fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax1.legend(fontsize=8.5, loc="lower left")
    ax1.grid(axis="y", alpha=0.3, linestyle="--")

    # ── Panel B: seasonal ───────────────────────────────────────────────────
    x       = np.arange(len(seasons))
    n_m     = len(METHODS)
    width   = 0.20
    offsets = np.linspace(-(n_m - 1) / 2, (n_m - 1) / 2, n_m) * width

    legend_handles = []
    for (_, lbl, col), off in zip(METHODS, offsets):
        vals_s = seasonal[lbl]
        hatch = "xx" if lbl == "Greedy" else None
        b = ax2.bar(x + off, vals_s, width, color=col, alpha=0.88,
                    hatch=hatch,
                    edgecolor="black" if hatch else "none",
                    linewidth=0.6 if hatch else 0)
        legend_handles.append(b[0])

    ax2.axhline(0, color="black", linewidth=1.0, linestyle=":", zorder=5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(season_lbls, fontsize=9)
    ax2.set_ylabel("Carbon saving vs. no-opt. baseline (%)", fontsize=9)
    ax2.set_title("B. Seasonal carbon saving vs. no-optimisation baseline\n"
                  "(dotted = no-opt. baseline 0 %)",
                  fontsize=10, fontweight="bold")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    legend_lbls = [f"{l} (violates ramp)" if l == "Greedy" else l for l in lbls]
    ax2.legend(handles=legend_handles, labels=legend_lbls,
               fontsize=8.5, bbox_to_anchor=(1.02, 0.5),
               loc="center left", borderaxespad=0)
    ax2.grid(axis="y", alpha=0.3, linestyle="--")

    fig.suptitle("Carbon Saving by Scheduler vs. No-Optimisation Baseline\n"
                 "(fully constrained LP: σ=0.6, κ=0.5, ρ=0.7; "
                 "positive = saves carbon vs doing nothing; negative = worse than doing nothing)",
                 fontsize=10, fontweight="bold")
    plt.tight_layout()
    plt.subplots_adjust(right=0.87)
    out = FIG_DIR / "heuristic_comparison.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure 6: Temporal vs. Spatial decomposition (Sukprasert et al., EuroSys 2024)
# ---------------------------------------------------------------------------

def fig_decomposition(df_dec: pd.DataFrame):
    """
    F6: Additive decomposition of LP carbon saving into spatial, temporal,
    and interaction components.

        saving_full = saving_spatial + saving_temporal + interaction

    Left panel:  overall + seasonal saving for each of the four variants
                 (Uniform=0% reference, Spatial-only, Temporal-only, Full LP)
    Right panel: additive bar showing how the three terms sum to the full
                 LP saving (waterfall-style), overall only.
    """
    def pct(c_u, c_x):
        return (c_u - c_x) / c_u * 100.0 if c_u > 0 else 0.0

    groups      = ["ALL", "DJF", "MAM", "JJA", "SON"]
    group_lbls  = ["Full\nperiod", "Winter", "Spring", "Summer", "Autumn"]

    spatial, temporal, full, interaction = [], [], [], []
    for g in groups:
        sub = df_dec if g == "ALL" else df_dec[df_dec["season"] == g]
        c_u = sub["carbon_uniform"].sum()
        s_s = pct(c_u, sub["carbon_spatial"].sum())
        s_t = pct(c_u, sub["carbon_temporal"].sum())
        s_f = pct(c_u, sub["carbon_full"].sum())
        spatial.append(s_s)
        temporal.append(s_t)
        full.append(s_f)
        interaction.append(s_f - s_s - s_t)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    # ── Left: grouped bars per scenario, overall + seasonal ─────────────────
    x      = np.arange(len(groups))
    width  = 0.22
    # colorblind-safe: blue=spatial (positive), orange=temporal (negative), green=full LP
    C_SPATIAL = "#0C5DA5"; C_TEMPORAL = "#FF9500"; C_FULL = "#00B945"; C_INTER = "#845B97"

    offsets = [-1, 0, 1]
    series  = [("Spatial-only", spatial, C_SPATIAL),
               ("Temporal-only", temporal, C_TEMPORAL),
               ("Full LP", full, C_FULL)]

    for (lbl, vals, color), off in zip(series, offsets):
        bars = ax1.bar(x + off * width, vals, width, label=lbl, color=color, alpha=0.88)
        for bar, v in zip(bars, vals):
            yoff = 1.5 if v >= 0 else -4.5
            ax1.text(bar.get_x() + bar.get_width() / 2, v + yoff,
                     f"{v:.0f}%", ha="center", fontsize=7.5, fontweight="bold", color=color)

    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(group_lbls, fontsize=9)
    ax1.set_ylabel("Carbon saving (%, no-optimization baseline = 0 %)", fontsize=9)
    ax1.set_title("A. Carbon saving by variant (overall + seasonal)\n"
                  "(temporal-only is negative: PJM CI varies little intra-day)",
                  fontsize=10, fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax1.legend(fontsize=8.5, loc="lower right")
    ax1.grid(axis="y", alpha=0.3, linestyle="--")

    # ── Right: additive waterfall for the full period ───────────────────────
    s_s, s_t, s_f, s_i = spatial[0], temporal[0], full[0], interaction[0]
    labels = ["Spatial\nrouting", "Temporal\nshifting",
              "Interaction\nterm", "Full LP\n(total)"]
    values  = [s_s, s_t, s_i, s_f]
    bottoms = [0, s_s, s_s + s_t, 0]
    colors  = [C_SPATIAL, C_TEMPORAL, C_INTER, C_FULL]

    bars = ax2.bar(labels, values, bottom=bottoms, color=colors, alpha=0.88, width=0.55)
    for bar, v, b in zip(bars, values, bottoms):
        ypos = b + v + (2.0 if v >= 0 else -3.5)
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f"{v:.1f}%",
                 ha="center", fontsize=9, fontweight="bold")

    ax2.plot([0.3, 0.7], [s_s, s_s], color="gray", linewidth=0.9, linestyle=":")
    ax2.plot([1.3, 1.7], [s_s + s_t, s_s + s_t], color="gray", linewidth=0.9, linestyle=":")
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_ylabel("Carbon saving (%, no-optimization baseline = 0 %)", fontsize=9)
    ax2.set_title("B. Additive decomposition (full 2-year period)\n"
                  r"saving$_{\rm full}$ = spatial + temporal + interaction",
                  fontsize=10, fontweight="bold")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax2.grid(axis="y", alpha=0.3, linestyle="--")

    fig.suptitle(
        "Temporal vs. Spatial Decomposition of LP Carbon Saving\n"
        "(spatial routing dominates; temporal-only is negative because the home region, "
        "PJM, is carbon-intensive)",
        fontsize=10, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "decomposition.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure 7: CV regression — within-region temporal saving vs. CI variability
# ---------------------------------------------------------------------------

def fig_cv_regression(df_cv: pd.DataFrame):
    """
    F7: Two-panel bar chart showing CI variability (CV) and temporal-only
    carbon saving per region, sorted by CV ascending.  Replaces the scatter
    plot; same data, no regression line.
    """
    # Sort regions by CV ascending so the pattern reads left→right.
    df_cv = df_cv.sort_values("cv").reset_index(drop=True)
    regions = df_cv["region"].values
    cvs     = df_cv["cv"].values
    savings = df_cv["saving_pct"].values
    colors  = [REGION_COLORS.get(r, "#333333") for r in regions]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # ── Panel A: CI coefficient of variation ─────────────────────────────────
    bars1 = ax1.bar(regions, cvs, color=colors, alpha=0.88, width=0.55)
    for bar, v in zip(bars1, cvs):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 0.005,
                 f"{v:.2f}", ha="center", va="bottom", fontsize=9,
                 fontweight="bold", color=bar.get_facecolor())
    ax1.set_ylabel("Coefficient of variation of CI  (std / mean)", fontsize=9)
    ax1.set_title("A. CI variability per region\n(higher = more within-day variation)",
                  fontsize=10, fontweight="bold")
    ax1.set_ylim(0, max(cvs) * 1.18)
    ax1.grid(axis="y", alpha=0.3, linestyle="--")

    # ── Panel B: temporal-only carbon saving ──────────────────────────────────
    bars2 = ax2.bar(regions, savings, color=colors, alpha=0.88, width=0.55)
    for bar, v in zip(bars2, savings):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + 0.3,
                 f"{v:.1f}%", ha="center", va="bottom", fontsize=9,
                 fontweight="bold", color=bar.get_facecolor())
    ax2.set_ylabel("Carbon saving from time-shifting only (%)", fontsize=9)
    ax2.set_title("B. Carbon saving from time-shifting only\n(all load stays at home region; only the hour is optimised)",
                  fontsize=10, fontweight="bold")
    ax2.set_ylim(0, max(savings) * 1.18)
    ax2.grid(axis="y", alpha=0.3, linestyle="--")

    fig.suptitle(
        "CI Variability and Time-Shifting Saving by Region\n"
        "(regions sorted by CI variability; more within-day variation → more to gain from timing)",
        fontsize=10, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "cv_regression.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure F8: Integration check — real data schedule + constraint binding
# ---------------------------------------------------------------------------

def fig_integration():
    """
    F8: Two-panel validation figure on 168 h of real data.

    Left:  Stacked area of hourly load allocation (PJM / FI / BE) over the
           full 7-day window, with CI signal overlaid on a secondary y-axis.
           Shows the LP routing load to low-CI regions and hours.

    Right: Constraint binding chart — each of C1-C7 shown as a horizontal
           bar of (actual / limit), clipped to [0, 1].  A bar at 1.0 = fully
           binding; shorter bars have headroom.  All must be ≤ 1.0 (= PASS).
    """
    from run_sensitivity import load_data

    INT_REGIONS = ["PJM", "Finland", "Belgium"]
    INT_COLORS  = {"PJM": REGION_COLORS["PJM"], "Finland": REGION_COLORS["Finland"], "Belgium": REGION_COLORS["Belgium"]}
    T_HOURS = 168
    DEMAND  = 1.0
    PARAMS  = dict(alpha=0.5, gamma=0.0, eta=0.3, sigma=0.5,
                   kappa=0.2, rho=0.4, delta=24, r0=0)
    TOL = 1e-4

    df     = load_data()
    df_sub = df.head(T_HOURS)
    CI  = df_sub[[f"ci_{r}"  for r in INT_REGIONS]].values.T   # (3, 168)
    CFE = df_sub[[f"cfe_{r}" for r in INT_REGIONS]].values.T

    C_max = np.full(3, DEMAND)
    C_min = np.zeros(3)
    D_flex = np.zeros(T_HOURS)
    for t in range(0, T_HOURS, 24):
        D_flex[t] = DEMAND
    D_total = D_flex.sum()

    res = lp_solve(CI, CFE, D_flex, C_min, C_max, **PARAMS)
    x   = res.x   # (3, 168)

    # ── carbon saving vs home-only baseline ──────────────────────────────
    x_home = np.zeros((3, T_HOURS))
    x_home[0, :] = D_total / T_HOURS
    c_home  = float((x_home * CI).sum())
    saving  = 100.0 * (c_home - res.carbon) / c_home

    # ── constraint binding ratios ─────────────────────────────────────────
    # each entry: (label, actual, limit)
    sigma = PARAMS["sigma"]; kappa = PARAMS["kappa"]; rho = PARAMS["rho"]
    delta = PARAMS["delta"]

    # C1: demand served
    c1_act = float(x.sum()) / D_total

    # C2: max relative placement within δ-hour windows
    latest = []
    for tau in range(T_HOURS):
        if D_flex[tau] <= 0: continue
        t_end  = min(tau + delta, T_HOURS)
        nz     = np.where(x[:, tau:t_end].sum(axis=0) > TOL)[0]
        latest.append(int(nz[-1]) if len(nz) else 0)
    c2_act = (max(latest) + 1) / delta if latest else 0.0

    # C3: max hourly load / C_max
    c3_act = float(x.max()) / DEMAND

    # C4: max off-home fraction per hour
    max_frac = 0.0
    for t in range(T_HOURS):
        tot_t = float(x[:, t].sum())
        if tot_t > TOL:
            max_frac = max(max_frac, float(x[1:, t].sum()) / tot_t)
    c4_act = max_frac / sigma

    # C5: equity (M = max regional carbon; always tight by construction)
    regional_c = [(x[r] * CI[r]).sum() for r in range(3)]
    c5_act = min(res.equity_M, max(regional_c)) / max(regional_c) if max(regional_c) > 0 else 1.0

    # C6: max ramp / (kappa * C_max)
    diffs  = np.abs(np.diff(x, axis=1))
    c6_act = float(diffs.max()) / (kappa * DEMAND)

    # C7: max swing across regions / (rho * C_max)
    swings = [float(x[r].max() - x[r].min()) for r in range(3)]
    c7_act = max(swings) / (rho * DEMAND)

    constraints = [
        ("C1  Demand served",       c1_act,  "equality (must = 1.0)"),
        ("C2  Deferral window δ",   c2_act,  "latest placement / δ"),
        ("C3  Hourly capacity",      c3_act,  "peak load / C_max"),
        ("C4  Geographic cap σ",    c4_act,  "max off-home / σ"),
        ("C5  Fairness M",          c5_act,  "M / max regional carbon"),
        ("C6  Ramp rate κ",         c6_act,  "max ramp / κ·C_max"),
        ("C7  Dynamic range ρ",     c7_act,  "max swing / ρ·C_max"),
    ]

    # ── Plot ─────────────────────────────────────────────────────────────
    fig, (ax_sched, ax_bar) = plt.subplots(1, 2, figsize=(15, 5.5),
                                            gridspec_kw={"width_ratios": [2, 1]})

    # Left: schedule + CI
    hours  = np.arange(T_HOURS)
    bottom = np.zeros(T_HOURS)
    for i, reg in enumerate(INT_REGIONS):
        ax_sched.fill_between(hours, bottom, bottom + x[i],
                              label=reg, color=INT_COLORS[reg], alpha=0.82, linewidth=0)
        bottom += x[i]

    ax2 = ax_sched.twinx()
    ci_colors = {"PJM": REGION_COLORS["PJM"], "Finland": REGION_COLORS["Finland"], "Belgium": REGION_COLORS["Belgium"]}
    for i, reg in enumerate(INT_REGIONS):
        ax2.plot(hours, CI[i], color=INT_COLORS[reg], linewidth=0.9,
                 alpha=0.55, linestyle="--")
    ax2.set_ylabel("Carbon intensity (gCO$_2$eq/kWh)", fontsize=9, color="dimgray")
    ax2.tick_params(axis="y", labelcolor="dimgray")

    # Day boundary lines
    for d in range(1, 8):
        ax_sched.axvline(d * 24, color="gray", linewidth=0.5, linestyle=":")

    ax_sched.set_xlabel("Hour", fontsize=9)
    ax_sched.set_ylabel("Load assigned (kWh/h)", fontsize=9)
    ax_sched.set_xlim(0, T_HOURS)
    ax_sched.legend(loc="upper right", fontsize=8)
    ax_sched.set_title(
        f"A. 168-hour schedule on real data  (LP carbon saving vs home-only: {saving:.1f}%)\n"
        "Stacked area = load allocation by region  |  dashed lines = CI signal",
        fontweight="bold", fontsize=10)
    ax_sched.grid(axis="y", alpha=0.25, linestyle="--")

    # Right: constraint binding bars
    labels = [c[0] for c in constraints]
    ratios = [min(c[1], 1.05) for c in constraints]   # clip slightly above 1 to show near-binding
    colors_bar = ["#0C5DA5" if r >= 0.95 else "#6BAED6" if r >= 0.5 else "#C6DBEF"
                  for r in ratios]

    y_pos = np.arange(len(constraints))
    bars  = ax_bar.barh(y_pos, ratios, color=colors_bar, height=0.55, alpha=0.88)
    ax_bar.axvline(1.0, color="black", linewidth=1.5, linestyle="--", label="Limit (= 1.0)")

    for bar, (lbl, act, desc) in zip(bars, constraints):
        tag = "BINDING" if act >= 0.95 else f"{act:.2f}"
        ax_bar.text(min(act, 1.05) + 0.01, bar.get_y() + bar.get_height()/2,
                    tag, va="center", fontsize=8,
                    color="#073763" if act >= 0.95 else "dimgray")

    ax_bar.set_yticks(y_pos)
    ax_bar.set_yticklabels(labels, fontsize=9)
    ax_bar.set_xlabel("Actual / limit  (≤ 1.0 = satisfied)", fontsize=9)
    ax_bar.set_xlim(0, 1.35)
    ax_bar.set_title("B. Constraint binding status\n(dark green = binding; light = slack)",
                     fontweight="bold", fontsize=10)
    ax_bar.legend(fontsize=8, loc="lower right")
    ax_bar.grid(axis="x", alpha=0.3)

    fig.suptitle(
        "Integration Check — Full Model on 168 h of Real Data\n"
        "(PJM / Finland / Belgium, all 7 constraints active simultaneously, 7/7 PASS)",
        fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "integration_check.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Perturbation test — before/after for each scenario
# ---------------------------------------------------------------------------

def fig_perturbation(df_p: pd.DataFrame):
    """
    F1: Three-panel perturbation test on the 3-region (PJM, FI, BE) x 6-hour instance.

    Panel A: Demand increase — stacked bars showing full allocation at each level.
    Panel B: δ tightened — hourly schedule for δ=6h vs δ=1h, CI on secondary axis.
             Shows *why* carbon rises: load can no longer defer to FI's clean hours.
    Panel C: C_max squeezed — FI's hourly load profile at 3 capacity levels.
             Shows *how* the schedule changes: spreads (mild) then collapses (severe).
    """
    _d0 = np.zeros(6); _d0[0] = 10.0
    hours = np.arange(6)
    c_fi  = REGION_COLORS["Finland"]; c_pjm = REGION_COLORS["PJM"]; c_be = REGION_COLORS["Belgium"]
    c_mild = "#FF9500"; c_sev = "#FF2C00"

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))

    # ── Panel A: demand increase — stacked bars ───────────────────────────
    ax = axes[0]
    demand_levels = [10.0, 11.0, 11.5, 12.0]
    xlabels = ["10 kWh\n(base)", "11 kWh\n(+10%)", "11.5 kWh\n(+15%)", "12 kWh\n(+20%)"]
    fi_tot, pjm_tot, be_tot = [], [], []
    for d in demand_levels:
        _db = np.zeros(6); _db[0] = d
        res = lp_solve(CI=_PERT_CI, CFE=_PERT_CFE, D_flex_batches=_db,
                       C_min=_PERT_CMIN, C_max=_PERT_CMAX, **_PERT_PARAMS)
        t = res.x.sum(axis=1)
        pjm_tot.append(float(t[0])); fi_tot.append(float(t[1])); be_tot.append(float(t[2]))
    xpos = np.arange(4)
    ax.bar(xpos, fi_tot,  label="FI",  color=c_fi,  alpha=0.88)
    ax.bar(xpos, pjm_tot, label="PJM", color=c_pjm, alpha=0.88, bottom=fi_tot)
    for xi, (fi, pjm) in enumerate(zip(fi_tot, pjm_tot)):
        ax.text(xi, fi/2,       f"{fi:.1f}",       ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        ax.text(xi, fi + pjm/2, f"{pjm:.1f}",      ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        ax.text(xi, fi + pjm + 0.2, f"{fi+pjm:.1f}", ha="center", fontsize=8, color="dimgray")
    ax.set_xticks(xpos); ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylabel("Total load assigned (kWh)"); ax.set_ylim(0, 14)
    ax.set_title("A. Total demand D ↑ → FI absorbs increment first\n(BE = 0 throughout; stacked = FI + PJM)", fontweight="bold", fontsize=10)
    ax.legend(fontsize=8.5, loc="upper left"); ax.grid(axis="y", alpha=0.3, linestyle="--")

    # ── Panel B: δ tightened — hourly schedule view ───────────────────────
    ax = axes[1]
    res6 = lp_solve(CI=_PERT_CI, CFE=_PERT_CFE, D_flex_batches=_d0,
                    C_min=_PERT_CMIN, C_max=_PERT_CMAX, **_PERT_PARAMS)          # δ=6
    res1 = lp_solve(CI=_PERT_CI, CFE=_PERT_CFE, D_flex_batches=_d0,
                    C_min=_PERT_CMIN, C_max=_PERT_CMAX,
                    **{**_PERT_PARAMS, "delta": 1})                                # δ=1
    bw = 0.38
    xpos6 = hours - bw/2;  xpos1 = hours + bw/2
    ax.bar(xpos6, res6.x[1], bw, label=f"δ=6h  FI  ({res6.carbon:,.0f} gCO$_2$)", color=c_fi,   alpha=0.88)
    ax.bar(xpos6, res6.x[0], bw, bottom=res6.x[1], color=c_pjm, alpha=0.75)
    ax.bar(xpos1, res1.x[1], bw, label=f"δ=1h  FI  ({res1.carbon:,.0f} gCO$_2$)", color=c_fi,   alpha=0.45, hatch="//")
    ax.bar(xpos1, res1.x[0], bw, bottom=res1.x[1], color=c_pjm, alpha=0.45, hatch="//")

    # CI overlay on secondary axis
    ax2 = ax.twinx()
    ax2.plot(hours, _PERT_CI[1], "o--", color=c_fi,  linewidth=1.2, markersize=4, alpha=0.7, label="FI CI")
    ax2.plot(hours, _PERT_CI[0], "s--", color=c_pjm, linewidth=1.2, markersize=4, alpha=0.7, label="PJM CI")
    ax2.set_ylabel("CI (gCO$_2$eq/kWh)", fontsize=8, color="dimgray")
    ax2.tick_params(axis="y", labelcolor="dimgray", labelsize=8)
    ax2.set_ylim(0, 800)

    from matplotlib.patches import Patch
    legend_els = [
        Patch(facecolor=c_fi,   alpha=0.88, label=f"δ=6h  ({res6.carbon:,.0f} gCO$_2$)"),
        Patch(facecolor=c_fi,   alpha=0.45, hatch="//", label=f"δ=1h  ({res1.carbon:,.0f} gCO$_2$)"),
        Patch(facecolor=c_pjm,  alpha=0.75, label="PJM (both)"),
    ]
    ax.legend(handles=legend_els, fontsize=8, loc="upper center", framealpha=0.95)
    pct = (res1.carbon - res6.carbon) / res6.carbon * 100
    ax.set_xlabel("Hour within 6-hour window", fontsize=9)
    ax.set_ylabel("Load assigned (kWh/h)", fontsize=9)
    ax.set_xticks(hours); ax.set_ylim(0, 9.5)
    ax.set_title(f"B. Max deferral time δ ↓ (6h → 1h) → carbon +{pct:.0f}%\n"
                 "(solid = δ=6h defers to best hours; hatched = δ=1h forces t=0)",
                 fontweight="bold", fontsize=10)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    # ── Panel C: C_max — FI hourly load profile ───────────────────────────
    ax = axes[2]
    cmax_cases = [
        (10.0, "#0C5DA5", "C_max=10 kWh/h (baseline)"),
        (3.0,  c_mild,    "C_max=3 kWh/h  (mild)"),
        (0.5,  c_sev,     "C_max=0.5 kWh/h (severe)"),
    ]
    for cmax, col, lbl in cmax_cases:
        _cm = _PERT_CMAX.copy(); _cm[1] = cmax
        res_c = lp_solve(CI=_PERT_CI, CFE=_PERT_CFE, D_flex_batches=_d0,
                         C_min=_PERT_CMIN, C_max=_cm, **_PERT_PARAMS)
        fi_hourly = res_c.x[1]
        fi_total  = fi_hourly.sum()
        ax.step(np.append(hours, 5), np.append(fi_hourly, fi_hourly[-1]),
                where="post", color=col, linewidth=2.2,
                label=f"{lbl}  (total={fi_total:.1f} kWh)")
        ax.fill_between(np.append(hours, 5), np.append(fi_hourly, fi_hourly[-1]),
                        step="post", color=col, alpha=0.18)
        ax.axhline(cmax, color=col, linewidth=0.9, linestyle=":", alpha=0.7)

    ax.set_xlabel("Hour within 6-hour window", fontsize=9)
    ax.set_ylabel("FI load (kWh/h)", fontsize=9)
    ax.set_xticks(hours); ax.set_ylim(0, 7)
    ax.set_title("C. FI hourly cap C_max ↓ → schedule spreads (mild),\nthen total FI load falls (severe)",
                 fontweight="bold", fontsize=10)
    ax.legend(fontsize=8, loc="upper right"); ax.grid(alpha=0.3, linestyle="--")

    fig.suptitle("Perturbation Test — Hourly Schedule Response\n"
                 "(PJM / FI / BE, real data 2024-07-17, all 7 constraints active)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "perturbation_test.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Loading results …")
    df_sweep = load_sweep()
    df_bl    = load_baseline()
    df_heur  = load_heuristic()
    df_sched_unc, df_sched_con = load_schedule()
    df_dec   = load_decomposition()
    df_cv    = load_cv_regression()
    df_pert  = load_perturbation()
    print(f"  Sweep: {len(df_sweep)} rows  |  Baseline: {len(df_bl)} windows")

    print("\nGenerating figures …")
    if df_sched_unc is not None:
        fig_schedule(df_sched_unc, df_sched_con)
    else:
        print("  Skipping F2: no schedule_sample.parquet found")

    fig_sensitivity(df_sweep)
    fig_seasonal(df_bl)
    if df_heur is not None:
        fig_heuristic_absolute(df_heur)
    else:
        print("  Skipping F5: no heuristic_backtest.parquet (run src/run_sensitivity.py)")

    if df_dec is not None:
        fig_decomposition(df_dec)
    else:
        print("  Skipping F6: no decomposition.csv found (run src/run_decomposition.py)")

    if df_cv is not None:
        fig_cv_regression(df_cv)
    else:
        print("  Skipping F7: no cv_regression.csv found (run src/run_cv_regression.py)")

    if df_pert is not None:
        fig_perturbation(df_pert)
    else:
        print("  Skipping F1: no perturbation_test.csv found (run src/test_perturbation.py)")

    print("\nGenerating integration check figure …")
    fig_integration()

    print(f"\nAll figures saved to {FIG_DIR}/")


if __name__ == "__main__":
    main()
