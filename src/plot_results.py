"""
Generate thesis figures from sensitivity sweep and baseline backtest results.

Figures produced (saved to data/figures/)
------------------------------------------
F0  schedule_sample.png      LP schedule vs CI signal (one representative week)
F1  sensitivity_tornado.png  OAT tornado diagram; bars sorted by impact width
F2  seasonal_breakdown.png   LP saving and regional carbon share by season
F3  heuristic_comparison.png LP efficiency ratio: Oracle/LP/Greedy/Uniform/FCFS
F6  decomposition.png        temporal vs. spatial decomposition of LP saving
F7  cv_regression.png        CI variability vs within-region temporal saving

Usage
-----
    python src/plot_results.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent.parent / "data" / "results"
FIG_DIR     = Path(__file__).parent.parent / "data" / "figures" / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)

LABELS = ["PJM", "NYISO", "Finland", "Belgium", "Singapore"]

REGION_COLORS = {
    "PJM":       "#1f77b4",
    "NYISO":     "#ff7f0e",
    "Finland":   "#2ca02c",
    "Belgium":   "#d62728",
    "Singapore": "#9467bd",
}

HEURISTIC_STYLES = {
    "Uniform":  dict(color="#999999", hatch=""),
    "FCFS":     dict(color="#fdae61", hatch=""),
    "Greedy":   dict(color="#ff7f0e", hatch=""),
    "Oracle":   dict(color="#74add1", hatch="//"),
    "LP":       dict(color="#1f77b4", hatch=""),
}

SEASON_LABELS = {"DJF": "Winter", "MAM": "Spring", "JJA": "Summer", "SON": "Autumn"}

PARAM_LABELS = {
    "alpha": r"$\alpha$ (CFE weight)",
    "sigma": r"$\sigma$ (geographic cap)",
    "delta": r"$\delta$ (deadline, hours)",
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


# ---------------------------------------------------------------------------
# Figure 0: Schedule sample (solution and validation)
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
    F0: schedule exhibit using the comparison basis the supervisor asked for
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
                             sharex="col",
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

    fig.suptitle("Figure F0: No-Shift Baseline vs. LP-Optimised Schedule\n"
                 "(one representative 24-hour window; both panels use the "
                 "same CI data)",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "schedule_sample.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure 1: Sensitivity — OAT Tornado Diagram (Eschenbach 1992)
# ---------------------------------------------------------------------------

def fig_sensitivity(df: pd.DataFrame):
    """
    F1: OAT tornado diagram (Eschenbach, Interfaces 1992).

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

    fig, ax = plt.subplots(figsize=(10, max(4, n * 0.85 + 1.5)))

    for i, p in enumerate(y_labels):
        lo, hi = param_ranges[p]
        rng    = hi - lo

        if lo < 0:
            ax.barh(i, -lo, left=lo, height=0.55,
                    color="#2ca02c", alpha=0.85, zorder=3)
        if hi > 0:
            ax.barh(i, hi, left=0, height=0.55,
                    color="#d62728", alpha=0.85, zorder=3)

        # Annotate right end of bar with % increase
        if hi > 0:
            ax.text(hi + 0.4, i, f"+{hi:.1f}%",
                    va="center", ha="left", fontsize=8, color="#d62728")
        if lo < 0 and hi <= 0:
            ax.text(lo - 0.4, i, f"{lo:.1f}%",
                    va="center", ha="right", fontsize=8, color="#2ca02c")

    ax.axvline(0, color="black", linewidth=1.5, zorder=5)
    ax.set_yticks(range(n))
    ax.set_yticklabels([PARAM_LABELS.get(p, p) for p in y_labels], fontsize=10)
    ax.set_xlabel(
        "Change in LP carbon per window relative to unconstrained baseline (%)",
        fontsize=10)
    ax.set_title(
        "Figure F1: OAT Sensitivity — Tornado Diagram\n"
        "(sorted by impact; red = cost of tightening, green = gain from loosening)",
        fontsize=11, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, zorder=0)

    # Add a subtle legend for the color convention
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor="#d62728", alpha=0.85, label="Carbon increase (constraint tightened)"),
        Patch(facecolor="#2ca02c", alpha=0.85, label="Carbon decrease (constraint loosened)"),
    ], fontsize=8, loc="lower right")

    max_hi = max(hi for _, hi in param_ranges.values())
    ax.set_xlim(-max_hi * 0.15, max_hi * 1.25)

    plt.tight_layout()
    out = FIG_DIR / "sensitivity_tornado.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure 2: Seasonal breakdown
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
    width = 0.2
    offsets = [-1.5, -0.5, 0.5, 1.5]
    labels  = ["LP", "Greedy", "FCFS", "Oracle"]
    colors  = ["#1f77b4", "#ff7f0e", "#d62728", "#74add1"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    for (key, lbl, col), off in zip(
            zip(["lp","greedy","fcfs","oracle"], labels, colors), offsets):
        ax1.bar(x + off * width, metrics[key], width,
                label=lbl, color=col, alpha=0.85)

    ax1.set_xticks(x)
    ax1.set_xticklabels([SEASON_LABELS[s] for s in seasons], fontsize=9)
    ax1.set_ylabel("Carbon saving vs uniform (%)")
    ax1.set_title("Seasonal savings: LP vs heuristics", fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=1))
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", alpha=0.3)

    bottom = np.zeros(len(seasons))
    for lab in LABELS:
        ax2.bar(x, region_shares[lab], width=0.6, bottom=bottom,
                label=lab, color=REGION_COLORS[lab], alpha=0.85)
        bottom += np.array(region_shares[lab])

    ax2.set_xticks(x)
    ax2.set_xticklabels([SEASON_LABELS[s] for s in seasons], fontsize=9)
    ax2.set_ylabel("Share of LP carbon allocation (%)")
    ax2.set_title("Regional carbon load share by season", fontweight="bold")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out = FIG_DIR / "seasonal_breakdown.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure 3: Heuristic comparison — LP efficiency ratio (Dolan & Moré 2002)
# ---------------------------------------------------------------------------

def fig_heuristic(df_bl: pd.DataFrame):
    """
    F3: Heuristic comparison using LP efficiency ratio.

    Metric (Carbon Explorer 2023 / Dolan & Moré 2002 convention):
        efficiency = (C_Uniform - C_alg) / (C_Uniform - C_LP) × 100 %

    Interpretation:
      LP      = 100 % (captures 100 % of its own saving potential, by definition)
      Oracle  > 100 % (longer look-ahead retrieves extra saving beyond 24-h LP)
      Greedy  ≈ 100 % when constraints are loose; drops when C6/C7 are binding
      Uniform =   0 % (no scheduling, no saving)
      FCFS    <   0 % (concentrates load in high-CI home-region slots;
                        worse than doing nothing)

    Two-panel layout:
      Left:  overall efficiency ratio, sorted bar chart
      Right: seasonal breakdown, grouped bars
    """
    df_bl = df_bl.copy()
    if "season" not in df_bl.columns:
        df_bl["season"] = df_bl["datetime"].apply(
            lambda d: {12:"DJF",1:"DJF",2:"DJF",
                       3:"MAM",4:"MAM",5:"MAM",
                       6:"JJA",7:"JJA",8:"JJA",
                       9:"SON",10:"SON",11:"SON"}[pd.Timestamp(d).month]
        )

    METHODS = [
        ("carbon_oracle", "Oracle",  "#74add1"),
        ("carbon_lp",     "LP",      "#1f77b4"),
        ("carbon_greedy", "Greedy",  "#ff7f0e"),
        ("carbon_uniform","Uniform", "#999999"),
        ("carbon_fcfs",   "FCFS",    "#d62728"),
    ]
    seasons     = ["DJF", "MAM", "JJA", "SON"]
    season_lbls = ["Winter", "Spring", "Summer", "Autumn"]

    def efficiency(sub: pd.DataFrame, col: str) -> float:
        c_u  = sub["carbon_uniform"].sum()
        c_lp = sub["carbon_lp"].sum()
        denom = c_u - c_lp
        if denom <= 0 or col not in sub.columns:
            return float("nan")
        c_alg = sub[col].sum()
        return (c_u - c_alg) / denom * 100.0

    # ── Overall efficiencies ──────────────────────────────────────────────
    overall = {lbl: efficiency(df_bl, col) for col, lbl, _ in METHODS}

    # ── Seasonal efficiencies ─────────────────────────────────────────────
    seasonal: dict[str, list[float]] = {lbl: [] for _, lbl, _ in METHODS}
    for s in seasons:
        sub = df_bl[df_bl["season"] == s]
        for col, lbl, _ in METHODS:
            seasonal[lbl].append(efficiency(sub, col))

    # ── Plot ──────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))

    # Left panel: overall sorted bar
    lbls   = [lbl for _, lbl, _ in METHODS]
    colors = [c   for _, _,   c in METHODS]
    vals   = [overall[lbl] for lbl in lbls]
    bar_colors = ["#d62728" if v < 0 else c for v, c in zip(vals, colors)]

    bars = ax1.bar(np.arange(len(lbls)), vals, color=bar_colors, alpha=0.85, width=0.55)
    ax1.axhline(100, color="#1f77b4", linewidth=1.5, linestyle="--",
                label="LP reference (100 %)", zorder=5)
    ax1.axhline(0,   color="black",   linewidth=1.0, linestyle=":",
                label="Uniform (0 %)", zorder=5)

    for bar, v in zip(bars, vals):
        if not np.isnan(v):
            yoff = 1.5 if v >= 0 else -4.0
            ax1.text(bar.get_x() + bar.get_width() / 2, v + yoff,
                     f"{v:.1f}%", ha="center", fontsize=8, fontweight="bold")

    ax1.set_xticks(np.arange(len(lbls)))
    ax1.set_xticklabels(lbls, fontsize=10)
    ax1.set_ylabel("LP efficiency ratio (%)", fontsize=10)
    ax1.set_title("Overall LP efficiency ratio\n"
                  r"eff = $(C_{\rm Uniform} - C_{\rm alg})/(C_{\rm Uniform} - C_{\rm LP})$",
                  fontsize=10, fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=1))
    ax1.legend(fontsize=8, loc="lower right")
    ax1.grid(axis="y", alpha=0.3)

    # Right panel: seasonal grouped bars
    x      = np.arange(len(seasons))
    n_m    = len(METHODS)
    width  = 0.15
    offsets = np.linspace(-(n_m - 1) / 2, (n_m - 1) / 2, n_m) * width

    for (_, lbl, col), off in zip(METHODS, offsets):
        vals_s = seasonal[lbl]
        bar_c  = [("#d62728" if v < 0 else col) for v in vals_s]
        for j, (v, bc) in enumerate(zip(vals_s, bar_c)):
            ax2.bar(x[j] + off, v, width, color=bc, alpha=0.85,
                    label=lbl if j == 0 else "")

    ax2.axhline(100, color="#1f77b4", linewidth=1.5, linestyle="--", zorder=5)
    ax2.axhline(0,   color="black",   linewidth=1.0, linestyle=":",  zorder=5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(season_lbls, fontsize=10)
    ax2.set_ylabel("LP efficiency ratio (%)", fontsize=10)
    ax2.set_title("Seasonal LP efficiency ratio\n(dashed = LP 100 %; dotted = Uniform 0 %)",
                  fontsize=10, fontweight="bold")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=1))
    ax2.legend([lbl for _, lbl, _ in METHODS], fontsize=8, loc="lower right")
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("Figure F3: Heuristic Comparison — LP Efficiency Ratio\n"
                 "(LP = 100 % reference; Oracle > 100 % captures look-ahead benefit; "
                 "FCFS < 0 % worsens carbon vs doing nothing)",
                 fontsize=10, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "heuristic_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
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
    offsets = [-1, 0, 1]
    series  = [("Spatial-only", spatial, "#2ca02c"),
               ("Temporal-only", temporal, "#d62728"),
               ("Full LP", full, "#1f77b4")]

    for (lbl, vals, color), off in zip(series, offsets):
        bars = ax1.bar(x + off * width, vals, width, label=lbl, color=color, alpha=0.85)
        for bar, v in zip(bars, vals):
            yoff = 1.5 if v >= 0 else -4.5
            ax1.text(bar.get_x() + bar.get_width() / 2, v + yoff,
                     f"{v:.0f}", ha="center", fontsize=7.5, fontweight="bold")

    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(group_lbls, fontsize=10)
    ax1.set_ylabel("Carbon saving vs Uniform baseline (%)")
    ax1.set_title("Carbon saving by variant\n(overall + seasonal)",
                  fontsize=10, fontweight="bold")
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax1.legend(fontsize=8, loc="lower right")
    ax1.grid(axis="y", alpha=0.3)

    # ── Right: additive waterfall for the full period ───────────────────────
    s_s, s_t, s_f, s_i = spatial[0], temporal[0], full[0], interaction[0]
    labels = ["Spatial\ncontribution", "Temporal\ncontribution",
              "Interaction\n(joint benefit)", "Full LP\n(total)"]
    values = [s_s, s_t, s_i, s_f]
    # Waterfall bottoms: spatial starts at 0; temporal stacks from spatial;
    # interaction stacks from (spatial+temporal); full is drawn from 0 as the total.
    bottoms = [0, s_s, s_s + s_t, 0]
    colors  = ["#2ca02c", "#d62728", "#9467bd", "#1f77b4"]

    bars = ax2.bar(labels, values, bottom=bottoms, color=colors, alpha=0.88, width=0.6)
    for bar, v, b in zip(bars, values, bottoms):
        ypos = b + v + (2.5 if v >= 0 else -2.5)
        ax2.text(bar.get_x() + bar.get_width() / 2, ypos,
                 f"{v:+.1f} pp" if bar is not bars[-1] else f"{v:.1f}%",
                 ha="center", fontsize=9, fontweight="bold")

    # Connector lines showing the additive chain
    ax2.plot([0.3, 0.7], [s_s, s_s], color="gray", linewidth=0.8, linestyle=":")
    ax2.plot([1.3, 1.7], [s_s + s_t, s_s + s_t], color="gray", linewidth=0.8, linestyle=":")
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_ylabel("Carbon saving vs Uniform baseline (%)")
    ax2.set_title("Additive decomposition (full period)\n"
                  r"saving$_{\rm full}$ = spatial + temporal + interaction",
                  fontsize=10, fontweight="bold")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle(
        "Figure F6: Temporal vs. Spatial Decomposition of LP Carbon Saving\n"
        "(spatial routing dominates; temporal-only is negative because the home region, "
        "PJM, is carbon-intensive)",
        fontsize=10, fontweight="bold")
    plt.tight_layout()
    out = FIG_DIR / "decomposition.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Figure 7: CV regression — within-region temporal saving vs. CI variability
# ---------------------------------------------------------------------------

def fig_cv_regression(df_cv: pd.DataFrame):
    """
    F7: Diagnostic scatter — coefficient of variation of regional CI vs.
    within-region temporal-only saving (5 points, one per region).

    Framed explicitly as a diagnostic, not a statistical test (n=5).
    See Essays/cv_regression_methodology.md.
    """
    x = df_cv["cv"].values
    y = df_cv["saving_pct"].values
    regions = df_cv["region"].values

    slope, intercept = np.polyfit(x, y, 1)
    x_line = np.linspace(x.min() * 0.85, x.max() * 1.1, 100)
    y_line = slope * x_line + intercept
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(x_line, y_line, color="gray", linestyle="--", linewidth=1.2,
            label=f"OLS fit (diagnostic, n=5): y={slope:.1f}x+{intercept:.1f}, R²={r2:.2f}")

    # Manual offsets to avoid label collisions in the dense low-CV cluster
    label_offsets = {
        "PJM":       (-45, -14),
        "NYISO":     (10, 8),
        "Finland":   (10, 4),
        "Belgium":   (10, 4),
        "Singapore": (10, -14),
    }
    for xi, yi, reg in zip(x, y, regions):
        ax.scatter(xi, yi, s=140, color=REGION_COLORS.get(reg, "#333333"),
                  edgecolor="black", linewidth=0.8, zorder=5)
        ax.annotate(reg, (xi, yi), textcoords="offset points",
                   xytext=label_offsets.get(reg, (8, 6)),
                   fontsize=10, fontweight="bold")

    ax.set_xlabel("Coefficient of variation of regional CI  (std / mean)", fontsize=10)
    ax.set_ylabel("Within-region temporal-only saving (%)", fontsize=10)
    ax.set_title(
        "Figure F7: CI Variability vs. Within-Region Temporal Saving\n"
        "(diagnostic, n=5 regions — not a formal statistical test)",
        fontsize=10, fontweight="bold")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out = FIG_DIR / "cv_regression.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"  Saved {out}")
    plt.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Loading results …")
    df_sweep = load_sweep()
    df_bl    = load_baseline()
    df_sched_unc, df_sched_con = load_schedule()
    df_dec   = load_decomposition()
    df_cv    = load_cv_regression()
    print(f"  Sweep: {len(df_sweep)} rows  |  Baseline: {len(df_bl)} windows")

    print("\nGenerating figures …")
    if df_sched_unc is not None:
        fig_schedule(df_sched_unc, df_sched_con)
    else:
        print("  Skipping F0: no schedule_sample.parquet found")

    fig_sensitivity(df_sweep)
    fig_seasonal(df_bl)
    fig_heuristic(df_bl)

    if df_dec is not None:
        fig_decomposition(df_dec)
    else:
        print("  Skipping F6: no decomposition.csv found (run src/run_decomposition.py)")

    if df_cv is not None:
        fig_cv_regression(df_cv)
    else:
        print("  Skipping F7: no cv_regression.csv found (run src/run_cv_regression.py)")

    print(f"\nAll figures saved to {FIG_DIR}/")


if __name__ == "__main__":
    main()
