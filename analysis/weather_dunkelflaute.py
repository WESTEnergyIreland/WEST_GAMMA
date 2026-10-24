"""Weather years in the WEST_GAMMA model: wind resource by year, dunkelflaute events and the
storage an all-renewable system would need to ride through them.

Inputs (Data_inputs/): sem_demand_wind_solar_master.csv (15-minute SEM demand, wind and solar
availability) and Input - capacity, constraints, curtailment.xlsx (installed wind by year).

Outputs (analysis/output/): weather_years.csv, dunkelflaute_events.csv, storage_requirement.csv,
and three charts. Run: python analysis/weather_dunkelflaute.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'output')
os.makedirs(OUT, exist_ok=True)

# Model weather years: complete years with installed capacity in the input workbook.
WEATHER_YEARS = list(range(2019, 2026))
DT = 0.25
# Dunkelflaute: run of days whose daily mean wind capacity factor is below this threshold.
DF_THRESHOLD_CF = 0.10
DF_MIN_DAYS = 2
STORAGE_ROUND_TRIP = 0.80          # applied as sqrt on charge and on discharge

# DNV UK and Ireland Wind Index for Ireland (annual mean wind speed, % of 1996-to-previous-year
# average). Published values only; 2019 and 2020 Irish values are not in DNV's text.
DNV_IRELAND_INDEX = {2021: 93.6, 2022: 97.9, 2023: 99.2, 2024: 99.1, 2025: 97.2}

d = pd.read_csv(os.path.join(ROOT, 'Data_inputs', 'sem_demand_wind_solar_master.csv'))
d['t'] = pd.to_datetime(d['date'], format='%d/%m/%Y %H:%M')
d['year'] = d['t'].dt.year
cap = pd.read_excel(os.path.join(ROOT, 'Data_inputs', 'Input - capacity, constraints, curtailment.xlsx'),
                    sheet_name='CapacityByYear', header=None, usecols=[0, 3], names=['year', 'mw'])
cap = cap[pd.to_numeric(cap['year'], errors='coerce').notna()].drop_duplicates('year', keep='first')
cap = dict(zip(cap['year'].astype(int), cap['mw'].astype(float)))
d = d[d['year'].isin(WEATHER_YEARS)].copy()
# Year-end capacity is used as the fleet for the year; mid-year growth makes early-year CF
# slightly high. The 2019-2025 fleet grew 1.1 GW, so the bias is small.
d['wind_cf'] = d['sem_wind_availability'] / d['year'].map(cap)
d['demand'] = d['sem_demand']

# ---------- 1. Wind resource by year ----------
yr = d.groupby('year').agg(wind_cf=('wind_cf', 'mean'), demand_twh=('demand', lambda x: x.sum() * DT / 1e6),
                           peak_demand_mw=('demand', 'max'))
winter = d[d['t'].dt.month.isin([12, 1, 2])].groupby('year')['wind_cf'].mean()
yr['winter_wind_cf'] = winter
yr['wind_cf_vs_mean_pct'] = 100 * (yr['wind_cf'] / yr['wind_cf'].mean() - 1)
yr['dnv_ireland_wind_index_pct'] = pd.Series(DNV_IRELAND_INDEX)
yr.round(4).to_csv(os.path.join(OUT, 'weather_years.csv'))

# ---------- 2. Dunkelflaute events ----------
day = d.set_index('t').resample('D').agg({'wind_cf': 'mean', 'demand': 'mean'}).dropna()
low = day['wind_cf'] < DF_THRESHOLD_CF
events, start = [], None
for t, flag in low.items():
    if flag and start is None:
        start = t
    if (not flag) and start is not None:
        events.append((start, prev))
        start = None
    prev = t
if start is not None:
    events.append((start, prev))
rows = []
for a, b in events:
    n = (b - a).days + 1
    if n < DF_MIN_DAYS:
        continue
    seg = d[(d['t'] >= a) & (d['t'] < b + pd.Timedelta(days=1))]
    rows.append({'start': a.date(), 'end': b.date(), 'days': n,
                 'mean_wind_cf_pct': round(100 * seg['wind_cf'].mean(), 1),
                 'min_hourly_wind_cf_pct': round(100 * seg['wind_cf'].min(), 1),
                 'mean_demand_mw': round(seg['demand'].mean()),
                 'peak_demand_mw': round(seg['demand'].max())})
ev = pd.DataFrame(rows).sort_values(['days', 'mean_wind_cf_pct'], ascending=[False, True])
# Energy each event would take from storage in an all-wind system whose annual wind energy is
# 1.0x or 1.5x demand (wind scaled on the 2019-2025 average CF), in days of average demand.
mean_cf = d['wind_cf'].mean()
avg_day_mwh = d['demand'].mean() * 24
for k in (1.0, 1.5):
    deficits = []
    for _, e in ev.iterrows():
        seg = d[(d['t'] >= pd.Timestamp(e['start'])) & (d['t'] < pd.Timestamp(e['end']) + pd.Timedelta(days=1))]
        supply = seg['wind_cf'] / mean_cf * seg['demand'].mean() * k
        deficits.append(np.maximum(0, seg['demand'] - supply).sum() * DT / avg_day_mwh)
    ev[f'storage_days_wind_x{k:g}'] = np.round(deficits, 1)
ev['season'] = np.where(pd.to_datetime(ev['start']).dt.month.isin([10, 11, 12, 1, 2, 3]), 'winter (Oct-Mar)', 'summer (Apr-Sep)')
ev.to_csv(os.path.join(OUT, 'dunkelflaute_events.csv'), index=False)

# Longest window (1 to 14 days) of lowest mean wind CF, across all weather years
roll = {}
for n in (1, 2, 3, 5, 7, 10, 14):
    r = day['wind_cf'].rolling(n).mean()
    roll[n] = (r.min(), r.idxmin())

# ---------- 3. Storage for an all-renewable system ----------
# Wind (and optionally solar) is scaled so that available energy over 2019-2025 equals total
# demand x oversize. No interconnectors, no firm plant, no network constraint or SNSP limit.
# Storage needed = the deepest cumulative shortfall, charging only from surplus.
def storage_needed(supply, demand, rte=STORAGE_ROUND_TRIP):
    eta = np.sqrt(rte)
    level, worst, used = 0.0, 0.0, []
    net = (supply - demand) * DT          # MWh per interval
    for x in net:
        level = min(0.0, level + (x * eta if x > 0 else x / eta))
        worst = min(worst, level)
    return -worst                          # MWh below full

solar_shape = d['sem_solar_availability'].fillna(0.0)
has_solar = d.groupby('year')['sem_solar_availability'].sum() > 0
solar_years = [y for y in WEATHER_YEARS if has_solar.get(y, False)]
avg_daily_mwh = d['demand'].sum() * DT / (len(d) * DT / 24)
store = []
for label, solar_share, years in (('wind only', 0.0, WEATHER_YEARS),
                                  ('wind 80% / solar 20%', 0.2, solar_years)):
    sub = d[d['year'].isin(years)]
    w = sub['wind_cf'].values
    s = solar_shape.loc[sub.index].values
    dem = sub['demand'].values
    for oversize in (1.0, 1.25, 1.5, 2.0):
        target = dem.sum() * oversize
        supply = w / w.sum() * target * (1 - solar_share)
        if solar_share > 0:
            supply = supply + s / s.sum() * target * solar_share
        need = storage_needed(supply, dem)
        store.append({'mix': label, 'weather_years': f"{years[0]}-{years[-1]}", 'oversize': oversize,
                      'storage_TWh': round(need / 1e6, 2),
                      'storage_days_of_avg_demand': round(need / avg_daily_mwh, 1),
                      'wind_GW_equivalent': round(target * (1 - solar_share) / (sub['wind_cf'].sum()) / 1000, 1)})
st = pd.DataFrame(store)
st.to_csv(os.path.join(OUT, 'storage_requirement.csv'), index=False)

# ---------- Charts ----------
fig, ax = plt.subplots(figsize=(8, 4))
x = np.arange(len(yr))
ax.bar(x - 0.2, 100 * yr['wind_cf'], 0.4, label='Annual wind CF (availability)', color='#3b6ea5')
ax.bar(x + 0.2, 100 * yr['winter_wind_cf'], 0.4, label='Winter (DJF) wind CF', color='#9bb8d8')
ax.set_xticks(x, yr.index)
ax.set_ylabel('Capacity factor, %')
ax2 = ax.twinx()
idx = yr['dnv_ireland_wind_index_pct']
ax2.plot(x, idx, 'o-', color='#c0392b', label='DNV Ireland wind index (% of long-term)')
ax2.axhline(100, color='#c0392b', lw=0.8, ls='--')
ax2.set_ylim(85, 110)
ax2.set_ylabel('DNV wind speed index, %')
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=8, loc='lower left')
ax.set_title('Model weather years: wind resource')
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'weather_years.png'), dpi=150)

fig, ax = plt.subplots(figsize=(9, 3.5))
ax.plot(day.index, 100 * day['wind_cf'], lw=0.6, color='#3b6ea5')
ax.axhline(100 * DF_THRESHOLD_CF, color='#c0392b', lw=0.8, ls='--', label=f'{100*DF_THRESHOLD_CF:.0f}% threshold')
for _, e in ev.iterrows():
    ax.axvspan(pd.Timestamp(e['start']), pd.Timestamp(e['end']) + pd.Timedelta(days=1), color='#c0392b', alpha=0.25)
ax.set_ylabel('Daily mean wind CF, %'); ax.legend(fontsize=8)
ax.set_title(f'Daily wind capacity factor 2019-2025; shaded: {DF_MIN_DAYS}+ days below {100*DF_THRESHOLD_CF:.0f}%')
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'dunkelflaute_timeline.png'), dpi=150)

fig, ax = plt.subplots(figsize=(6, 4))
for mix, g in st.groupby('mix'):
    ax.plot(g['oversize'], g['storage_days_of_avg_demand'], 'o-', label=mix)
ax.set_xlabel('Renewable energy / demand (oversize)'); ax.set_ylabel('Storage, days of average demand')
ax.set_title('Storage for an all-renewable, islanded system'); ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'storage_requirement.png'), dpi=150)

pd.set_option('display.width', 160)
print(yr.round(3).to_string())
print(f"\nDunkelflaute events: {len(ev)} runs of {DF_MIN_DAYS}+ days below {100*DF_THRESHOLD_CF:.0f}% "
      f"({(ev['season'].str.startswith('winter')).sum()} in Oct-Mar)")
print(ev.groupby('season')['days'].describe().round(1).to_string())
print('\nLongest events:'); print(ev.head(8).to_string(index=False))
print('\nWinter (Oct-Mar) events, by storage needed:')
print(ev[ev['season'].str.startswith('winter')].sort_values('storage_days_wind_x1', ascending=False).head(10).to_string(index=False))
jan = d[(d['t'] >= '2025-01-06') & (d['t'] < '2025-01-13')].set_index('t').resample('D').agg({'wind_cf': 'mean', 'demand': ['mean', 'max']})
print('\nJanuary 2025 cold spell (daily):'); print(jan.round(3).to_string())
print('\nLowest n-day mean wind CF:')
for n, (v, t) in roll.items():
    print(f"  {n:>2} days: {100*v:.1f}% ending {t.date()}")
print('\nStorage requirement:'); print(st.to_string(index=False))
print(f"\nAverage daily demand {avg_daily_mwh/1000:.1f} GWh")
