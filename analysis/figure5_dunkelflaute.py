"""Figure 5 of the Phase 1 paper: fifteen-minute dispatch on a cold day of low wind and sun under
EirGrid Extended (EE), drawn in the same style as Figure 10(a) and with no title on the figure
(the caption carries the date, the fleet and the energy totals).

Usage: python analysis/figure5_dunkelflaute.py <outputs> [day year]
<outputs> holds EirGrid_Extended/ from a Gamma.py run with charts on and target_year 2050, so that
Gamma writes chart_Daily_Dunkelflaute_2048.csv. Writes analysis/output/paper/Figure_5.pdf and .png.
"""
import glob
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_figures_common import save
from figure10_showcase import daily_panel, legend_handles, C

out = sys.argv[1]
year = sys.argv[2] if len(sys.argv) > 2 else '2048'
files = sorted(glob.glob(os.path.join(out, 'EirGrid_Extended', f'chart_Daily_Dunkelflaute_{year}.csv')))
if not files:
    sys.exit(f'No chart_Daily_Dunkelflaute_{year}.csv: run Gamma.py with charts on, EE target_year 2050')
d = pd.read_csv(files[-1])
fig, ax = plt.subplots(figsize=(10, 4.6))
daily_panel(ax, files[-1], '')
ax.set_title('', loc='left')
ax.grid(axis='y', color='0.9')
ax.spines[['top', 'right']].set_visible(False)
handles = legend_handles() + [Line2D([], [], color='black', lw=1.8, label='Demand (incl. battery charging)'),
                              Line2D([], [], color=C['wind_e'], lw=1.4, ls='--', label='Available wind and solar')]
fig.legend(handles=handles, loc='lower center', ncol=3, frameon=False, fontsize=9)
fig.tight_layout(rect=(0, 0.17, 1, 1))
save(fig, 5)
e = d[['usable_wind_mw', 'usable_solar_mw', 'available_wind_solar_mw', 'demand_incl_charging_mw',
       'curtailment_oversupply_mw', 'grid_constraint_mw', 'battery_discharge_mw', 'battery_charge_mw']].sum() * 0.25 / 1000
r = d.iloc[0]
print(f"{int(r['day'])}/{int(r['month'])}/{int(r['year'])}: wind {r['wind_gw']:.2f} GW, solar {r['solar_gw']:.2f} GW, "
      f"batteries {r['battery_mw']/1000:.2f} GW / {r['battery_mwh']/1000:.2f} GWh")
print((e.round(1)).to_string())
