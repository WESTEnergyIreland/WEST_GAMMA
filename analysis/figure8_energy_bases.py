"""Figure 8 of the Phase 1 paper: primary energy, gross final energy and electricity-equivalent
energy against wind and solar consumed on the island, EE and HT, 2026 to the end year.

Reads energy_benchmarks_vs_renewables.csv, which Gamma.py writes for each scenario. Each measure
is calculated every year from that scenario's demand and electrification. Wind and solar include
what reaches demand through batteries (20 November 2026).

Usage: python analysis/figure8_energy_bases.py <outputs> [end year, default 2050]
Writes analysis/output/paper/Figure_8.pdf and .png.
"""
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_figures_common import save, EE, HT, EE_LABEL, HT_LABEL

out = sys.argv[1]
END = int(sys.argv[2]) if len(sys.argv) > 2 else 2050   # paper horizon (20 November 2026)
LINES = [('Primary_Energy_Modelled_TWh', 'Primary energy', '#08306b', '-'),
         ('Final_Energy_Modelled_TWh', 'Final energy', '#2171b5', '-'),
         ('Electricity_Equivalent_Modelled_TWh', 'Electricity equivalent', '#4fb3d9', '-'),
         ('Delivered_Wind_Solar_TWh', 'Wind and solar consumed (incl. via batteries)', '#1a9641', '--')]
fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
ymax = 0
for ax, (sc, label) in zip(axes, ((EE, EE_LABEL), (HT, HT_LABEL))):
    b = pd.read_csv(os.path.join(out, sc, 'energy_benchmarks_vs_renewables.csv')).set_index('Year')
    b = b[(b.index >= 2026) & (b.index <= END)]
    ymax = max(ymax, b[[c for c, *_ in LINES]].max().max())
    end = b.index.max()
    for col, name, colour, ls in LINES:
        ax.plot(b.index, b[col], color=colour, ls=ls, lw=2.6 if ls == '--' else 2.0, label=name)
        ax.text(end + 1, b.loc[end, col], f'{b.loc[end, col]:.0f}', color=colour, va='center',
                fontsize=10, fontweight='bold')
    gap = b.loc[end, 'Electricity_Equivalent_Modelled_TWh'] - b.loc[end, 'Delivered_Wind_Solar_TWh']
    xg = end - 4
    ax.annotate('', xy=(xg, b.loc[xg, 'Delivered_Wind_Solar_TWh']),
                xytext=(xg, b.loc[xg, 'Electricity_Equivalent_Modelled_TWh']),
                arrowprops=dict(arrowstyle='<->', color='0.25', lw=1.2))
    ax.text(xg + 1, b.loc[xg, 'Electricity_Equivalent_Modelled_TWh'] + 5, f'Gap {gap:.0f} TWh in {end}',
            ha='right', va='bottom', fontsize=9, color='0.25')
    ax.set_title(f'({"a" if sc == EE else "b"}) {label}', loc='left', fontweight='bold', fontsize=11)
    ax.set_xlim(2026, end)
    ax.grid(axis='y', color='0.9'); ax.spines[['top', 'right']].set_visible(False)
    print(sc, end, {c: round(b.loc[end, c], 1) for c, *_ in LINES}, 'gap', round(gap, 1))
axes[0].set_ylabel('TWh a year')
axes[0].set_ylim(0, ymax * 1.06)
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc='lower center', ncol=4, frameon=False, fontsize=10)
fig.tight_layout(rect=(0, 0.07, 0.97, 1))
save(fig, 8)
