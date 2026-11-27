"""Draw Fig. 2 of the paper (mean and pooled MQM TQ, accurate count per condition) from results/scores.csv.

Run src/score.py first; this script only plots what it wrote, so the figure always matches Table VII.
Needs matplotlib (a local plotting dependency, deliberately not in requirements.txt: the web app does not use it).

Usage:  python src/plot_fig2.py [results/scores.csv] [results/fig2_mqm.png]
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LABELS = {
    "Zero-Shot": "Zero-Shot",
    "Full Context": "Full Context",
    "Ablation: No Social Hierarchy": "No Hierarchy",
    "Ablation: No Social Distance": "No Distance",
    "Ablation: No Communicative Intent": "No Intent",
    "Full Context + Check/Select": "Full Context\n+ Check/Select",
}
BASELINE, CONTEXT, SELECTED = "#8a8985", "#2a78d6", "#1d5aa3"
INK, MUTED, GRID = "#000000", "#5c5b58", "#e6e5e1"


def main(src, out):
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    names = [LABELS[r["condition"]] for r in rows]
    mean = [float(r["mean_mqm_tq"]) for r in rows]
    pooled = [float(r["pooled_mqm_tq"]) for r in rows]
    acc = [r["accurate"] for r in rows]
    colors = [BASELINE if r["condition"] == "Zero-Shot"
              else SELECTED if "Check/Select" in r["condition"] else CONTEXT for r in rows]

    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "font.size": 9})
    fig, ax = plt.subplots(figsize=(3.48, 2.51), dpi=300)
    y = list(range(len(rows)))[::-1]
    ax.barh(y, mean, height=0.55, color=colors, zorder=2)
    ax.scatter(pooled, y, marker="D", s=26, facecolor="white", edgecolor=INK, linewidth=1.0, zorder=3,
               clip_on=False)
    for yi, a in zip(y, acc):
        ax.text(1.06, yi, a, transform=ax.get_yaxis_transform(), va="center", ha="center", color=INK)
    ax.text(1.06, len(rows) - 0.45, "Accurate", transform=ax.get_yaxis_transform(), va="center",
            ha="center", color=MUTED, fontsize=8)

    ax.set_yticks(y, names, color=MUTED)
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel("MQM TQ (0–100)")
    ax.grid(axis="x", color=GRID, linewidth=0.6, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, length=3)

    handles = [Patch(color=CONTEXT, label="Mean sentence TQ"),
               Line2D([], [], marker="D", linestyle="none", markerfacecolor="white", markeredgecolor=INK,
                      markersize=5, label="Pooled TQ")]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.55, 1.0),
               handlelength=1.6, columnspacing=2.0)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=300)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "results" / "scores.csv",
         sys.argv[2] if len(sys.argv) > 2 else ROOT / "results" / "fig2_mqm.png")
