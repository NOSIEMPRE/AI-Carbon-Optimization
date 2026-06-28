"""
Regenerate the exploratory-analysis figures used in Section 3 of the thesis,
using the shared publication style (figstyle) so they match the result figures
and the poster.

Figures (saved to data/figures/eda/):
  eda_ci_boxplot.png         CI distribution by region
  eda_diurnal.png            average CI by hour of day
  eda_ci_cfe_regression.png  CI vs CFE per region (2x3 panels)

Usage:  python src/plot_eda.py
"""
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from figstyle import apply_style, REGION_COLORS

apply_style()

RAW = Path(__file__).parent.parent / "data" / "raw"
OUT = Path(__file__).parent.parent / "data" / "figures" / "eda"
OUT.mkdir(parents=True, exist_ok=True)

# (display name, ElectricityMaps zone code)
REGIONS = [
    ("PJM",       "US-MIDA-PJM"),
    ("NYISO",     "US-NY-NYIS"),
    ("Finland",   "FI"),
    ("Belgium",   "BE"),
    ("Singapore", "SG"),
]


def _load(zone):
    ci = pd.read_parquet(RAW / f"{zone}_ci.parquet")
    rf = pd.read_parquet(RAW / f"{zone}_rf.parquet")
    return ci.merge(rf[["datetime", "cfe_fraction"]], on="datetime").dropna()


def fig_boxplot(data):
    fig, ax = plt.subplots(figsize=(9, 5))
    names  = [n for n, _ in REGIONS]
    series = [data[n]["carbon_intensity"].values for n in names]
    bp = ax.boxplot(series, labels=names, patch_artist=True, widths=0.6,
                    showfliers=False, medianprops=dict(color="black", linewidth=1.3))
    for patch, n in zip(bp["boxes"], names):
        patch.set_facecolor(REGION_COLORS[n]); patch.set_alpha(0.85)
        patch.set_edgecolor("black"); patch.set_linewidth(0.8)
    for w in bp["whiskers"]: w.set_color("0.4")
    for c in bp["caps"]:     c.set_color("0.4")
    ax.set_ylabel("Carbon intensity (gCO$_2$eq/kWh)")
    ax.set_xlabel("Region")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(OUT / "eda_ci_boxplot.png")
    plt.close(fig)
    print("saved eda_ci_boxplot.png")


def fig_diurnal(data):
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for n, _ in REGIONS:
        d = data[n].copy()
        d["hour"] = pd.to_datetime(d["datetime"], utc=True).dt.hour
        hourly = d.groupby("hour")["carbon_intensity"].mean()
        rng = hourly.max() - hourly.min()
        ax.plot(hourly.index, hourly.values, marker="o", markersize=3,
                color=REGION_COLORS[n], label=f"{n} (range {rng:.0f})")
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Mean carbon intensity (gCO$_2$eq/kWh)")
    ax.set_xticks(range(0, 24, 2))
    # single vertical column legend -> narrower, more room for the plot
    ax.legend(ncol=1, loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.tight_layout()
    fig.savefig(OUT / "eda_diurnal.png")
    plt.close(fig)
    print("saved eda_diurnal.png")


def fig_regression(data):
    rng = np.random.default_rng(0)
    fig = plt.figure(figsize=(12.5, 7.6))
    # 2x6 grid: top row holds 3 panels, bottom row holds 2 panels centered,
    # which avoids the unbalanced empty slot of a plain 2x3 layout.
    gs = fig.add_gridspec(2, 6, hspace=0.42, wspace=0.9)
    slots = [gs[0, 0:2], gs[0, 2:4], gs[0, 4:6], gs[1, 1:3], gs[1, 3:5]]
    for slot, (n, _) in zip(slots, REGIONS):
        ax = fig.add_subplot(slot)
        d = data[n]
        x = d["cfe_fraction"].values * 100.0
        y = d["carbon_intensity"].values.astype(float)
        b1, b0 = np.polyfit(x, y, 1)
        yhat = b1 * x + b0
        r2 = 1.0 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)
        idx = rng.choice(len(x), size=min(2500, len(x)), replace=False)
        ax.scatter(x[idx], y[idx], s=6, color=REGION_COLORS[n], alpha=0.25,
                   edgecolors="none", rasterized=True)
        xs = np.linspace(x.min(), x.max(), 100)
        ax.plot(xs, b1 * xs + b0, color="black", linewidth=1.6)
        ax.set_title(n, color=REGION_COLORS[n])
        ax.text(0.05, 0.08, f"$R^2={r2:.3f}$", transform=ax.transAxes,
                fontsize=10.5, va="bottom", ha="left",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.7", alpha=0.85))
        ax.set_xlabel("Carbon-free energy fraction (%)")
        ax.set_ylabel("CI (gCO$_2$eq/kWh)")
    fig.savefig(OUT / "eda_ci_cfe_regression.png")
    plt.close(fig)
    print("saved eda_ci_cfe_regression.png")


def fig_correlation(data):
    """5x5 Pearson correlation of hourly CI across regions (spatial decorrelation)."""
    names = [n for n, _ in REGIONS]
    M = pd.DataFrame({n: data[n].set_index("datetime")["carbon_intensity"] for n in names}).dropna()
    C = M.corr().values
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    im = ax.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    ax.set_xticks(range(len(names))); ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    for i in range(len(names)):
        for j in range(len(names)):
            v = C[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color="white" if abs(v) > 0.55 else "black", fontsize=10)
    ax.grid(False)
    cbar = fig.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label("Pearson correlation of hourly CI", fontsize=10)
    ax.set_title("Cross-region carbon-intensity correlation")
    fig.tight_layout()
    fig.savefig(OUT / "eda_ci_correlation.png")
    plt.close(fig)
    print("saved eda_ci_correlation.png")


def fig_cfe_composition(data):
    """Stacked mean shares: renewable vs nuclear vs fossil/other, per region."""
    names = [n for n, _ in REGIONS]
    ren, nuc, fos = [], [], []
    for n, z in REGIONS:
        rf = pd.read_parquet(RAW / f"{z}_rf.parquet")
        r = rf["renewable_fraction"].mean() * 100
        u = rf["nuclear_fraction"].mean() * 100
        ren.append(r); nuc.append(u); fos.append(max(0.0, 100 - r - u))
    ren, nuc, fos = np.array(ren), np.array(nuc), np.array(fos)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    x = np.arange(len(names))
    ax.bar(x, ren, label="Renewable (wind/solar/hydro)", color="#00B945", alpha=0.9)
    ax.bar(x, nuc, bottom=ren, label="Nuclear", color="#845B97", alpha=0.9)
    ax.bar(x, fos, bottom=ren + nuc, label="Fossil / other", color="#9E9E9E", alpha=0.9)
    for i in range(len(names)):
        if ren[i] > 4:  ax.text(i, ren[i]/2, f"{ren[i]:.0f}", ha="center", va="center", color="white", fontsize=9)
        if nuc[i] > 4:  ax.text(i, ren[i]+nuc[i]/2, f"{nuc[i]:.0f}", ha="center", va="center", color="white", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel("Share of consumed electricity (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Carbon-free supply composition by region")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=3)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(OUT / "eda_cfe_composition.png")
    plt.close(fig)
    print("saved eda_cfe_composition.png")


def fig_monthly(data):
    """Mean CI by calendar month, per region (seasonal structure)."""
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for n, _ in REGIONS:
        d = data[n].copy()
        d["month"] = pd.to_datetime(d["datetime"], utc=True).dt.month
        m = d.groupby("month")["carbon_intensity"].mean()
        ax.plot(m.index, m.values, marker="o", markersize=4,
                color=REGION_COLORS[n], label=n)
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean carbon intensity (gCO$_2$eq/kWh)")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"])
    # single vertical column legend outside the axes -> narrower, more room for the plot
    ax.legend(ncol=1, loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.tight_layout()
    fig.savefig(OUT / "eda_monthly.png")
    plt.close(fig)
    print("saved eda_monthly.png")


def fig_distribution(data):
    """Kernel-density estimate of hourly CI per region (distribution shape)."""
    from scipy.stats import gaussian_kde
    fig, ax = plt.subplots(figsize=(9, 5))
    for n, _ in REGIONS:
        y = data[n]["carbon_intensity"].values.astype(float)
        kde = gaussian_kde(y)
        xs = np.linspace(y.min(), y.max(), 400)
        ax.plot(xs, kde(xs), color=REGION_COLORS[n], label=n, linewidth=2)
        ax.fill_between(xs, kde(xs), color=REGION_COLORS[n], alpha=0.10)
    ax.set_xlabel("Carbon intensity (gCO$_2$eq/kWh)")
    ax.set_ylabel("Density")
    ax.set_title("Distribution of hourly carbon intensity by region")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "eda_distribution.png")
    plt.close(fig)
    print("saved eda_distribution.png")


def main():
    data = {n: _load(z) for n, z in REGIONS}
    fig_boxplot(data)
    fig_diurnal(data)
    fig_regression(data)
    fig_correlation(data)
    fig_cfe_composition(data)
    fig_monthly(data)
    fig_distribution(data)


if __name__ == "__main__":
    main()
