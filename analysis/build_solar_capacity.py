"""Solar installed capacity history and observed capacity factor, from the SONI/EirGrid
System and Renewable Data Summary Report (project lists with dates).

Fleet definition: the solar that reports availability in the dispatch-down records, so that
capacity and availability match. IE: transmission-connected (MEC, energisation date) plus
distribution-connected (MEC, energisation date). NI: controllable projects with a connection date.
Excluded: NI uncontrollable and 'other small scale' solar, and rooftop/microgeneration.

Writes:
  Data_inputs/solar_capacity_monthly.csv   month-end MW, IE / NI / all-island
  analysis/output/solar_cf_observed.csv    yearly available energy, mean capacity and CF
Run: python analysis/build_solar_capacity.py
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DI = os.path.join(ROOT, 'Data_inputs')
SRC = os.path.join(DI, 'ni_drivers', 'soni_system_and_renewable_data_summary.xlsx')
OUT = os.path.join(HERE, 'output')
os.makedirs(OUT, exist_ok=True)

ie = pd.read_excel(SRC, sheet_name='IE Connected Renewables', header=None).iloc[4:]
ni = pd.read_excel(SRC, sheet_name='NI Connected Wind & Solar', header=None).iloc[3:]
# Column positions in the report (side-by-side tables): IE TSO solar 31 name, 34 MEC, 40 energisation;
# IE DSO solar 44 project, 46 MEC, 51 energisation; NI solar 13 name, 14 installed, 18 date, 23 controllable.
tso = pd.DataFrame({'name': ie[31], 'mw': pd.to_numeric(ie[34], errors='coerce'),
                    'date': pd.to_datetime(ie[40], errors='coerce')}).dropna(subset=['name', 'mw', 'date'])
dso = pd.DataFrame({'name': ie[44], 'mw': pd.to_numeric(ie[46], errors='coerce'),
                    'date': pd.to_datetime(ie[51], errors='coerce')}).dropna(subset=['name', 'mw', 'date'])
nis = pd.DataFrame({'name': ni[13], 'mw': pd.to_numeric(ni[14], errors='coerce'),
                    'date': pd.to_datetime(ni[18], errors='coerce'), 'ctrl': ni[23]})
nis = nis[(nis['ctrl'].astype(str).str.strip() == 'Controllable')].dropna(subset=['mw', 'date'])

months = pd.date_range('2014-01-31', '2026-12-31', freq='ME')
cap = pd.DataFrame({'month_end': months})
cap['IE_MW'] = [tso.loc[tso['date'] <= m, 'mw'].sum() + dso.loc[dso['date'] <= m, 'mw'].sum() for m in months]
cap['NI_MW'] = [nis.loc[nis['date'] <= m, 'mw'].sum() for m in months]
cap['Total_MW'] = cap['IE_MW'] + cap['NI_MW']
cap.round(1).to_csv(os.path.join(DI, 'solar_capacity_monthly.csv'), index=False)

rows = []
for reg, fname in (('IE', 'system_dd_hourly_ie_solar.csv'), ('NI', 'system_dd_hourly_ni_solar.csv')):
    d = pd.read_csv(os.path.join(DI, fname), parse_dates=['datetime'])
    d['year'] = d['datetime'].dt.year
    d['month_end'] = d['datetime'] + pd.offsets.MonthEnd(0)
    d['month_end'] = d['month_end'].dt.normalize()
    d = d.merge(cap[['month_end', f'{reg}_MW']], on='month_end', how='left')
    for y, g in d.groupby('year'):
        if g['av_mwh'].sum() <= 0 or g[f'{reg}_MW'].mean() <= 0:
            continue
        rows.append({'region': reg, 'year': y, 'hours': len(g), 'full_year': len(g) >= 8760,
                     'available_GWh': round(g['av_mwh'].sum() / 1e3, 1),
                     'mean_capacity_MW': round(g[f'{reg}_MW'].mean(), 1),
                     'cf_%': round(100 * g['av_mwh'].sum() / g[f'{reg}_MW'].sum(), 2)})
cf = pd.DataFrame(rows)
cf.to_csv(os.path.join(OUT, 'solar_cf_observed.csv'), index=False)
full = cf[cf['full_year'] & cf['year'].isin([2024, 2025])]
pooled = 100 * (full['available_GWh'].sum() * 1e3) / (full['mean_capacity_MW'] * full['hours']).sum()
print(cap[cap['month_end'].dt.month == 12].tail(8).to_string(index=False))
print(cf.to_string(index=False))
print(f"Pooled all-island solar CF, full years 2024-2025: {pooled:.1f}% (MEC basis)")
