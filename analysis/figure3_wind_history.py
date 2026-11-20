"""Figure 3 of the Phase 1 paper: wind and solar as a share of all-island demand, installed wind
and wind capacity factor, 2014-2026.

(a) Available wind, delivered wind and delivered wind plus solar as a share of all-island demand,
    from the TSOs' quarter-hourly system data (Data_inputs/sem_demand_wind_solar_master.csv).
    2026 covers January to September.
(b) Installed wind at year end (bars) and the wind capacity factor on the available and the
    delivered basis (lines), 2014-2025. Capacity factor = energy / (mean of installed capacity at
    the start and end of the year x hours in the year); 2014 uses its year-end capacity, because
    the 2013 value is not in the inputs.

Usage: python analysis/figure3_wind_history.py
"""
import os

import pandas as pd
import matplotlib.pyplot as plt

from paper_figures_common import REPO, BLUE, ORANGE, save

d = pd.read_csv(os.path.join(REPO, 'Data_inputs', 'sem_demand_wind_solar_master.csv'),
                usecols=['date', 'sem_demand', 'sem_wind_availability', 'sem_wind_generation',
                         'sem_solar_generation'])
d['year'] = pd.to_datetime(d['date'], format='%d/%m/%Y %H:%M').dt.year
g = d.groupby('year').agg(dem=('sem_demand', 'sum'), av=('sem_wind_availability', 'sum'),
                          gen=('sem_wind_generation', 'sum'), sol=('sem_solar_generation', 'sum'),
                          n=('sem_demand', 'size'))
for c in ('dem', 'av', 'gen', 'sol'):
    g[c] = g[c] * 0.25 / 1e6                       # MW in 15-minute intervals -> TWh
g['av_pct'] = 100 * g['av'] / g['dem']
g['gen_pct'] = 100 * g['gen'] / g['dem']
g['ws_pct'] = 100 * (g['gen'] + g['sol']) / g['dem']

cap = pd.read_excel(os.path.join(REPO, 'Data_inputs', 'Input - capacity, constraints, curtailment.xlsx'),
                    sheet_name='CapacityByYear')
cap = cap[pd.to_numeric(cap.iloc[:, 0], errors='coerce').between(2014, 2025)]
cap = cap.drop_duplicates(cap.columns[0]).set_index(cap.columns[0])['TOTAL (SEM, All-island) GW'] / 1000.0
cap.index = cap.index.astype(int)
mean_cap = ((cap + cap.shift(1)) / 2).fillna(cap)
hours = g['n'] * 0.25
cf_av = 100 * g['av'] * 1000 / (mean_cap * hours)
cf_del = 100 * g['gen'] * 1000 / (mean_cap * hours)

fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.4))
yrs = g.index
a.plot(yrs, g['av_pct'], color=BLUE, ls='--', marker='o', ms=4, lw=1.8, label='Available wind')
a.plot(yrs, g['gen_pct'], color=ORANGE, marker='o', ms=4, lw=1.8, label='Delivered wind')
sol = g['sol'] > 0
a.plot(yrs[sol], g.loc[sol, 'ws_pct'], color='#2e9e4f', marker='o', ms=4, lw=1.8,
       label='Delivered wind + solar')
a.set_ylabel('% of all-island demand')
a.set_title('(a) Share of demand', loc='left', fontsize=11)
a.spines[['top', 'right']].set_visible(False)
a.legend(frameon=False, ncol=3, loc='upper center', bbox_to_anchor=(0.5, -0.1))

cy = cap.index
b.bar(cy, cap.values, color='#9aa0a6', width=0.7, label='Installed wind, year end (GW)')
b.set_ylabel('GW'); b.set_ylim(0, 8)
b2 = b.twinx()
b2.plot(cy, cf_av.loc[cy], color=BLUE, ls='--', marker='o', ms=4, lw=1.8, label='Capacity factor, available')
b2.plot(cy, cf_del.loc[cy], color=ORANGE, marker='o', ms=4, lw=1.8, label='Capacity factor, delivered')
b2.set_ylabel('Capacity factor (%)'); b2.set_ylim(0, 40)
b.set_title('(b) Installed wind and capacity factor', loc='left', fontsize=11)
b.spines[['top']].set_visible(False); b2.spines[['top']].set_visible(False)
h1, l1 = b.get_legend_handles_labels(); h2, l2 = b2.get_legend_handles_labels()
b.legend(h1 + h2, l1 + l2, frameon=False, ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.1))
fig.tight_layout()
save(fig, 3)
print(pd.DataFrame({'available_%_demand': g['av_pct'], 'delivered_%_demand': g['gen_pct'],
                    'wind+solar_%_demand': g['ws_pct'], 'cf_available': cf_av, 'cf_delivered': cf_del,
                    'installed_GW': cap}).round(2).to_string())
