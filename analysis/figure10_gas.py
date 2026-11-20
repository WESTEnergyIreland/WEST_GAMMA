"""Figure 10 of the Phase 1 paper: annual gas use against worst-day gas demand and supply, both pathways.

Usage: python analysis/figure10_gas.py <ic_run scenario_outputs> [end year]
Writes analysis/output/paper/Figure_10.pdf and .png.

The first argument is the scenario_outputs folder written by analysis/interconnector_sensitivity.py
(analysis/ic_run/scenario_outputs), which holds each pathway at 0%, 70% and 100% of interconnector
capacity for imports and exports.

Panel (a): annual gas use (TWh, gross calorific value), power and non-power together.
Panel (b): worst gas day of the year (GWh/d, GCV), worst of the thirteen weather years.
Solid line: central case, interconnectors at 70% of capacity. Shading: range between no
interconnector flows (upper edge, dashed) and 100% of capacity (lower edge, dotted).
Dashed red: supply from Moffat, Corrib and biomethane.
"""
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_figures_common import save, EE_LABEL, HT_LABEL

PATHWAYS = [('EirGrid_Extended', EE_LABEL, '#1f6fb4'),
            ('Historical_Trend', HT_LABEL, '#d9622b')]


def load(base, sc, a, end_year):
    f = pd.read_csv(os.path.join(base, f'IC_{sc}_{a}', 'forecast_results.csv'))
    f['gas_total_twh'] = f['Gas_Power_TWh_GCV'] + f['Gas_NonPower_TWh_GCV']
    f = f.set_index('Year')
    return f[f.index <= end_year]


def main(ic_dir, end_year=2075):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
    supply = None
    for sc, label, col in PATHWAYS:
        f0, f70, f100 = (load(ic_dir, sc, a, end_year) for a in (0, 70, 100))
        for ax, c in ((ax1, 'gas_total_twh'), (ax2, 'Gas_Worst_Day_GWh')):
            ax.fill_between(f0.index, f100[c], f0[c], color=col, alpha=0.13, lw=0)
            ax.plot(f0.index, f0[c], color=col, lw=0.9, ls='--')
            ax.plot(f100.index, f100[c], color=col, lw=0.9, ls=':')
            ax.plot(f70.index, f70[c], color=col, lw=2, label=f'{label}, interconnectors at 70%')
        supply = f70['Gas_Supply_GWh_per_Day']
    for ax in (ax1, ax2):
        ax.plot([], [], color='0.35', lw=0.9, ls='--', label='No interconnector flows')
        ax.plot([], [], color='0.35', lw=0.9, ls=':', label='Interconnectors at 100%')
    ax2.plot(supply.index, supply, color='#b2182b', lw=1.5, ls='--',
             label='Supply: Moffat, Corrib and biomethane')
    ax1.set_ylabel('(a) Annual gas use, TWh (GCV)')
    ax2.set_ylabel('(b) Worst gas day, GWh/d (GCV)')
    for ax in (ax1, ax2):
        ax.set_xlim(2026, end_year)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
    ax1.legend(fontsize=7, frameon=False, loc='lower left')
    ax2.legend(fontsize=7, frameon=False, loc='lower right')
    fig.tight_layout()
    save(fig, 10)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], int(a[1]) if len(a) > 1 else 2075)
