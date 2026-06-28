"""
Shared publication-quality figure style for the thesis (and poster reuse).

Encodes a single source of truth for:
  - a colorblind-safe palette (SciencePlots base colors),
  - canonical region and method color maps used across every figure,
  - matplotlib rcParams for a clean, serif, publication look.

Import and call apply_style() at the top of any plotting script so that all
figures share one visual identity, which lets the thesis figures be reused
directly in the A0 poster without restyling.

Palette source: garrettj403/SciencePlots base 'science' style
(blue 0C5DA5, green 00B945, orange FF9500, red FF2C00, violet 845B97, gray).
"""
from cycler import cycler
import matplotlib.pyplot as plt

# ── Canonical palette ────────────────────────────────────────────────────────
PALETTE = ["#0C5DA5", "#00B945", "#FF9500", "#FF2C00", "#845B97", "#474747", "#9E9E9E"]

# Region colors: intuitive mapping (cleanest = green, highest-carbon = red),
# consistent in every region-coloured figure (boxplot, diurnal, regression,
# regional share, CV regression, schedule).
REGION_COLORS = {
    "PJM":       "#FF2C00",  # red    — high carbon
    "NYISO":     "#FF9500",  # orange — medium-high
    "Finland":   "#00B945",  # green  — cleanest
    "Belgium":   "#0C5DA5",  # blue   — medium
    "Singapore": "#845B97",  # violet — high, flat (control)
}

# Method colors: consistent across the scheduler-comparison figures.
METHOD_COLORS = {
    "Oracle":  "#00B945",  # green — perfect-foresight ceiling
    "LP":      "#0C5DA5",  # blue  — this thesis
    "Greedy":  "#FF9500",  # orange — carbon-aware heuristic
    "Uniform": "#9E9E9E",  # gray   — no-optimization baseline
    "FCFS":    "#FF2C00",  # red    — worse than doing nothing
}


def apply_style():
    """Apply the shared publication style to matplotlib's global rcParams."""
    plt.rcParams.update({
        # Resolution and export
        "figure.dpi":        150,
        "savefig.dpi":       300,
        "savefig.bbox":      "tight",
        "savefig.pad_inches": 0.05,
        # Serif typography to match the Times-set thesis body
        "font.family":       "serif",
        "font.serif":        ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset":  "dejavuserif",
        "font.size":         11,
        "axes.titlesize":    12,
        "axes.titleweight":  "bold",
        "axes.labelsize":    11,
        "xtick.labelsize":   10,
        "ytick.labelsize":   10,
        "legend.fontsize":   10,
        "legend.frameon":    False,
        # Clean, thin axes; drop top/right spines (Nature/seaborn despine look)
        "axes.linewidth":    0.8,
        "lines.linewidth":   1.8,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.axisbelow":    True,
        # Light dashed grid
        "axes.grid":         True,
        "grid.alpha":        0.3,
        "grid.linestyle":    "--",
        "grid.linewidth":    0.5,
        "xtick.direction":   "out",
        "ytick.direction":   "out",
        # Default color cycle
        "axes.prop_cycle":   cycler(color=PALETTE),
    })
