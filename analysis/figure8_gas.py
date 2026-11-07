"""Paper figure: annual gas use against worst-day gas demand and supply, both pathways.

Usage: python analysis/figure8_gas.py <scenario_outputs> <scenario_outputs with interconnector
dispatch, or -> <out.png> [end year]

Panel (a): annual gas use (TWh, gross calorific value), power and non-power together; dotted: with
interconnector flows.
Panel (b): worst gas day of the year (GWh/d, GCV). Solid line: worst of the thirteen weather years;
shading (EirGrid's plan): range of each weather year's worst day; dotted: the same run with
interconnector imports and exports in the dispatch. Dashed red: Moffat, Corrib and biomethane.
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

PATHWAYS = [('EirGrid_Extended', "EirGrid's plan, extended", '#1f6fb4'),
            ('Historical_Trend', 'Recorded trend', '#d9622b')]


def load(base, sc):
    f = pd.read_csv(os.path.join(base, sc, 'forecast_results.csv'))
    f['gas_total_twh'] = f['Gas_Power_TWh_GCV'] + f['Gas_NonPower_TWh_GCV']
    return f.set_index('Year')


def weather_range(base, sc):
    g = pd.read_csv(os.path.join(base, sc, 'gas_daily_by_weather_year.csv'))
    w = g.groupby(['year', 'weather_year'])['total_gwh'].max().unstack()
    return w.min(axis=1), w.median(axis=1)


def main(main_dir, ic_dir, out, end_year=2075):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8), dpi=300)
    supply = None
    for sc, label, col in PATHWAYS:
        f = load(main_dir, sc)
        f = f[f.index <= end_year]
        ax1.plot(f.index, f['gas_total_twh'], color=col, lw=2, label=label)
        ax2.plot(f.index, f['Gas_Worst_Day_GWh'], color=col, lw=2, label=f'{label}, worst weather year')
        if sc == 'EirGrid_Extended':
            lo, med = weather_range(main_dir, sc)
            lo, med = lo[lo.index <= end_year], med[med.index <= end_year]
            ax2.fill_between(lo.index, lo, f['Gas_Worst_Day_GWh'].reindex(lo.index), color=col,
                             alpha=0.15, lw=0, label=f'{label}, range over weather years')
        if ic_dir and ic_dir != '-':
            fi = load(ic_dir, sc)
            fi = fi[fi.index <= end_year]
            ax2.plot(fi.index, fi['Gas_Worst_Day_GWh'], color=col, lw=1.2, ls=':',
                     label=f'{label}, with interconnector flows')
            ax1.plot(fi.index, fi['gas_total_twh'], color=col, lw=1.2, ls=':',
                     label=f'{label}, with interconnector flows')
        supply = f['Gas_Supply_GWh_per_Day']
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
    fig.savefig(out)
    print('wrote', out)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 2075)
