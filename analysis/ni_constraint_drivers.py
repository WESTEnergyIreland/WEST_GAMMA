"""What drives Northern Ireland wind constraint? Moyle imports and transmission outages.

Data (Data_inputs/ and Data_inputs/ni_drivers/):
  system_dd_hourly_ni.csv                  hourly NI wind availability and constraint, 2021-2026 (EirGrid/SONI DD-HH)
  sem_demand_wind_solar_master.csv         15-minute NI demand
  ni_drivers/neso_demanddata_2024.csv      NESO historic demand data 2024, MOYLE_FLOW (+ = into GB)
  ni_drivers/soni_system_data_qtr_hourly_2026.xlsx   SONI 2026: Moyle I/C (+ = into NI), N-S flow
  ni_drivers/soni_transmission_outage_plan_202{4,5,6}.xlsx   SONI planned transmission outages
  ni_drivers/committed_outage_programme_2026.xlsx   SONI/EirGrid generator outage programme 2026

Method
1. Moyle: hourly NI constraint share against Moyle flow, within bands of NI wind availability
   (so windy hours are compared with windy hours), and a linear regression of constrained MW on
   wind availability, NI demand, Moyle import and month. 2024 (NESO) and 2026 (SONI) only.
2. Outages: for each day, whether a 275 kV transmission outage is planned. Expected constraint is
   taken from days with no 275 kV outage in the same wind-availability band and year; the excess on
   outage days is the outage-associated constraint. The plans are planned dates, not as-run, and
   outages overlap, so this is an association, not proof of cause.

Run: python analysis/ni_constraint_drivers.py   Outputs: analysis/output/ni_*.csv and .png
"""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DI = os.path.join(ROOT, 'Data_inputs')
ND = os.path.join(DI, 'ni_drivers')
OUT = os.path.join(HERE, 'output')
os.makedirs(OUT, exist_ok=True)
pd.set_option('display.width', 170)

# ---------- hourly NI constraint and demand ----------
dd = pd.read_csv(os.path.join(DI, 'system_dd_hourly_ni.csv'), parse_dates=['datetime'])
dd = dd.rename(columns={'datetime': 't', 'av_mwh': 'avail', 'constraint_mwh': 'con'})[['t', 'avail', 'con']]
m = pd.read_csv(os.path.join(DI, 'sem_demand_wind_solar_master.csv'), usecols=['datetime_utc', 'ni_demand'])
m['t'] = pd.to_datetime(m['datetime_utc'], format='%d/%m/%Y %H:%M').dt.floor('h')
dem = m.groupby('t')['ni_demand'].mean()
# DD-HH files are in local time per hour ending; master is UTC. Hour alignment within one hour is
# adequate for daily and banded comparisons used here.
dd['demand'] = dd['t'].map(dem)
dd['year'] = dd['t'].dt.year

# ---------- Moyle flows (MW into NI) ----------
neso = pd.read_csv(os.path.join(ND, 'neso_demanddata_2024.csv'))
neso['t'] = (pd.to_datetime(neso['SETTLEMENT_DATE'], format='%d-%b-%Y')
             + pd.to_timedelta((neso['SETTLEMENT_PERIOD'] - 1) * 30, unit='m'))
moyle24 = (-neso.set_index('t')['MOYLE_FLOW']).resample('h').mean()          # + = into NI
soni = pd.read_excel(os.path.join(ND, 'soni_system_data_qtr_hourly_2026.xlsx'), sheet_name='System Data')
soni = soni.dropna(subset=['DateTime']).set_index('DateTime')
moyle26 = soni['Moyle I/C'].resample('h').mean()
ns26 = soni['Inter-Jurisdictional Flow'].resample('h').mean()
moyle = pd.concat([moyle24, moyle26])
dd['moyle_import'] = dd['t'].map(moyle)
dd['ns_flow'] = dd['t'].map(ns26)
# 2026 demand is not in the master file; use SONI's NI demand for 2026
ni_dem26 = soni['NI Demand'].resample('h').mean()
dd.loc[dd['year'] == 2026, 'demand'] = dd.loc[dd['year'] == 2026, 't'].map(ni_dem26)

def band_table(df, label):
    df = df.dropna(subset=['moyle_import', 'avail']).copy()
    df = df[df['avail'] > 0]
    df['wind_band'] = pd.qcut(df['avail'], 4, labels=['low wind', 'mid-low', 'mid-high', 'high wind'])
    df['moyle_band'] = pd.cut(df['moyle_import'], [-1e9, 0, 200, 400, 1e9],
                              labels=['exporting', 'import 0-200', 'import 200-400', 'import >400'])
    g = df.groupby(['wind_band', 'moyle_band'], observed=True).agg(hours=('con', 'size'), con=('con', 'sum'),
                                                                   avail=('avail', 'sum'))
    g['constraint_%'] = 100 * g['con'] / g['avail']
    t = g['constraint_%'].unstack().round(1)
    h = g['hours'].unstack()
    t.to_csv(os.path.join(OUT, f'ni_constraint_by_moyle_{label}.csv'))
    return t, h, df

def regress(df, label):
    df = df.dropna(subset=['moyle_import', 'avail', 'demand']).copy()
    df = df[df['avail'] > 0]
    X = pd.DataFrame({'const': 1.0, 'wind_avail_MW': df['avail'], 'ni_demand_MW': df['demand'],
                      'moyle_import_MW': df['moyle_import']})
    X = pd.concat([X, pd.get_dummies(df['t'].dt.month, prefix='m', drop_first=True, dtype=float)], axis=1)
    X = X.loc[:, (X != 0).any(axis=0)]
    y = df['con'].values
    beta, *_ = np.linalg.lstsq(X.values, y, rcond=None)
    resid = y - X.values @ beta
    # Newey-West-free: hourly residuals are autocorrelated, so use daily-block standard errors
    days = df['t'].dt.date.values
    XtX_inv = np.linalg.inv(X.values.T @ X.values)
    meat = np.zeros_like(XtX_inv)
    for d in np.unique(days):
        idx = days == d
        s = X.values[idx].T @ resid[idx]
        meat += np.outer(s, s)
    se = np.sqrt(np.diag(XtX_inv @ meat @ XtX_inv))
    res = pd.DataFrame({'coef': beta, 'se_day_clustered': se}, index=X.columns).iloc[:4]
    res['r2'] = 1 - resid.var() / y.var()
    # Counterfactual: same hours with Moyle import capped at 0 (no imports), prediction clipped at
    # 0 and at availability. Linear and not causal: an upper-end indication only.
    Xc = X.copy()
    Xc['moyle_import_MW'] = np.minimum(Xc['moyle_import_MW'], 0.0)
    pred = np.clip(X.values @ beta, 0, df['avail'].values)
    pred_c = np.clip(Xc.values @ beta, 0, df['avail'].values)
    res['cf_constraint_%_model'] = 100 * pred.sum() / df['avail'].sum()
    res['cf_constraint_%_no_import'] = 100 * pred_c.sum() / df['avail'].sum()
    res['actual_constraint_%'] = 100 * y.sum() / df['avail'].sum()
    res.to_csv(os.path.join(OUT, f'ni_constraint_regression_{label}.csv'))
    return res, df

print('=' * 90)
print('1. MOYLE IMPORTS AND NI WIND CONSTRAINT')
moyle_results = {}
for yr, label in ((2024, '2024'), (2026, '2026_jan_jul')):
    sub = dd[dd['year'] == yr]
    t, h, used = band_table(sub, label)
    res, _ = regress(sub, label)
    moyle_results[label] = (t, res, used)
    share_import = (used['moyle_import'] > 0).mean()
    print(f"\n{label}: {len(used)} hours with wind; Moyle importing into NI {100*share_import:.0f}% of hours, "
          f"mean flow {used['moyle_import'].mean():.0f} MW into NI")
    print('Constraint % of available NI wind, by wind band (rows) and Moyle flow (columns):')
    print(t.to_string())
    print('Hours in each cell:'); print(h.to_string())
    print('Regression of constrained MW (hourly), month dummies included, day-clustered SE:')
    print(res.round(3).to_string())
if 'ns_flow' in dd:
    s26 = dd[(dd['year'] == 2026) & dd['ns_flow'].notna() & (dd['avail'] > 0)]
    c = np.corrcoef(s26['ns_flow'], s26['con'])[0, 1] if len(s26) else np.nan
    print(f"\n2026 North-South flow vs NI constrained MW: correlation {c:.2f} (sign convention per SONI file)")

# ---------- 2. Transmission outages ----------
print('\n' + '=' * 90)
print('2. PLANNED TRANSMISSION OUTAGES (SONI) AND NI WIND CONSTRAINT')

def parse_date(v):
    if isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, 'year'):
        return pd.Timestamp(v)
    if isinstance(v, str):
        s = re.sub(r'^[A-Za-z]{3}\s+', '', v.strip())
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                return pd.to_datetime(s, format=fmt)
            except ValueError:
                pass
    return pd.NaT

def parse_duration(v):
    s = str(v).strip().lower().replace('?', '')
    mm = re.match(r'([\d.]+)\s*(min|mins|d|day|days|w|wk|wks|week|weeks|m|mth|month|months)?', s)
    if not mm:
        return np.nan
    n, u = float(mm.group(1)), (mm.group(2) or 'd')
    if u.startswith('min'):
        return n / 1440
    if u.startswith('w'):
        return 7 * n
    if u in ('m', 'mth') or u.startswith('month'):
        return 30 * n
    return n

rows = []
for yr in (2024, 2025, 2026):
    x = pd.read_excel(os.path.join(ND, f'soni_transmission_outage_plan_{yr}.xlsx'), header=None)
    hdr = x.index[x.iloc[:, 0].astype(str).str.strip().str.upper() == 'SUB 1'][0]
    x = x.iloc[hdr + 1:, :8]
    x.columns = ['sub1', 'sub2', 'task', 'type', 'kv', 'duration', 'start', 'finish']
    for _, r in x.iterrows():
        # rows with a blank SUB 2 are shifted left by one cell in the source sheets
        vals = [r[c] for c in x.columns]
        if pd.isna(vals[0]):
            continue
        kv = pd.to_numeric(r['kv'], errors='coerce')
        if pd.isna(kv):                           # shifted row: sub2 missing
            vals = [vals[0], None] + vals[1:7]
        sub1, sub2, task, typ, kv, dur, st, fn = vals
        kv = pd.to_numeric(kv, errors='coerce')
        st, fn = parse_date(st), parse_date(fn)
        if pd.isna(fn) and pd.notna(st):
            days = parse_duration(dur)
            fn = st + pd.Timedelta(days=max(days, 1) if pd.notna(days) else 1)
        if pd.isna(st) or str(typ).strip().upper() == 'GEN':
            continue
        sub2 = '' if (sub2 is None or pd.isna(sub2)) else str(sub2).strip().upper()
        rows.append({'year': yr, 'sub1': str(sub1).strip().upper(), 'sub2': sub2,
                     'task': str(task).strip(), 'type': str(typ).strip().upper(), 'kv': kv,
                     'start': st.normalize(), 'finish': max(fn, st).normalize()})
out = pd.DataFrame(rows)
out = out[out['kv'].isin([110, 275])]
out.to_csv(os.path.join(OUT, 'ni_transmission_outages_parsed.csv'), index=False)
print(f"Parsed {len(out)} planned 110/275 kV outages (2024: {sum(out.year==2024)}, 2025: {sum(out.year==2025)}, "
      f"2026: {sum(out.year==2026)}); {sum(out.kv==275)} at 275 kV")

day = dd.set_index('t').resample('D').agg({'avail': 'sum', 'con': 'sum'})
day = day[day['avail'] > 0]
day['year'] = day.index.year
day = day[day['year'].isin([2024, 2025, 2026])]
# 275 kV circuit outages: a named circuit between two substations, up to 60 days. Station equipment
# work (busbars, panels, transformers) and long project windows are excluded; they rarely remove a
# circuit for the whole planned period.
out['days'] = (out['finish'] - out['start']).dt.days + 1
o275 = out[(out['kv'] == 275) & (out['sub2'] != '') & (out['days'] <= 60)]
print(f"275 kV circuit outages used: {len(o275)} (2024: {sum(o275.year==2024)}, 2025: {sum(o275.year==2025)}, "
      f"2026: {sum(o275.year==2026)})")
day['n275'] = [((o275['start'] <= d) & (o275['finish'] >= d)).sum() for d in day.index]
day['n110'] = [((out['kv'].eq(110)) & (out['start'] <= d) & (out['finish'] >= d)).sum() for d in day.index]
day['wind_band'] = day.groupby('year')['avail'].transform(lambda s: pd.qcut(s, 5, labels=False))
base = (day[day['n275'] == 0].groupby(['year', 'wind_band']).apply(lambda g: g['con'].sum() / g['avail'].sum())
        .rename('base_share'))
day = day.join(base, on=['year', 'wind_band'])
day['expected_con'] = day['avail'] * day['base_share']
summ = []
for yr, g in day.groupby('year'):
    od = g[g['n275'] > 0]
    summ.append({'year': yr, 'days': len(g), 'days_with_275kV_outage': len(od),
                 'constraint_%_outage_days': round(100 * od['con'].sum() / od['avail'].sum(), 1),
                 'constraint_%_other_days': round(100 * g.loc[g['n275'] == 0, 'con'].sum() / g.loc[g['n275'] == 0, 'avail'].sum(), 1),
                 'excess_GWh_on_outage_days': round((od['con'] - od['expected_con']).sum() / 1e3, 1),
                 'total_constraint_GWh': round(g['con'].sum() / 1e3, 1)})
summ = pd.DataFrame(summ)
summ['excess_share_of_year_%'] = (100 * summ['excess_GWh_on_outage_days'] / summ['total_constraint_GWh']).round(1)
summ.to_csv(os.path.join(OUT, 'ni_outage_summary.csv'), index=False)
print(summ.to_string(index=False))

# Per-outage association: excess constraint over each 275 kV outage window (shared days split evenly)
per = []
for _, r in o275.iterrows():
    w = day[(day.index >= r['start']) & (day.index <= r['finish'])]
    if not len(w):
        continue
    ex = ((w['con'] - w['expected_con']) / w['n275'].clip(lower=1)).sum() / 1e3
    per.append({'start': r['start'].date(), 'finish': r['finish'].date(), 'circuit': f"{r['sub1']} - {r['sub2']}".strip(' -'),
                'task': r['task'][:60], 'days': len(w), 'constraint_%_in_window': round(100 * w['con'].sum() / w['avail'].sum(), 1),
                'excess_GWh_share': round(ex, 1)})
per = pd.DataFrame(per).sort_values('excess_GWh_share', ascending=False)
per.to_csv(os.path.join(OUT, 'ni_outage_windows_ranked.csv'), index=False)
print('\n275 kV outage windows ranked by associated excess constraint (GWh, overlapping days shared):')
print(per.head(12).to_string(index=False))

# ---------- 3. Generator outages 2026 ----------
g = pd.read_excel(os.path.join(ND, 'committed_outage_programme_2026.xlsx'), sheet_name='SONI Outages', header=None)
g = g.iloc[4:, 1:8]
g.columns = ['station', 'unit', 'npr_mw', 'start', 'end', 'value', 'days']
g = g.dropna(subset=['station'])
g['days'] = pd.to_numeric(g['days'], errors='coerce')
long = g[(g['days'] >= 7) & (pd.to_numeric(g['npr_mw'], errors='coerce') >= 100)]
long.to_csv(os.path.join(OUT, 'ni_generator_outages_2026_long.csv'), index=False)
print('\nNI generator outages of 7+ days, units of 100 MW+, 2026 programme:')
print(long.to_string(index=False))

# ---------- Charts ----------
fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
for ax, (label, (t, res, used)) in zip(axes, moyle_results.items()):
    t.T.plot(kind='bar', ax=ax, width=0.8, colormap='Blues')
    ax.set_title(f'NI wind constraint by Moyle flow, {label.replace("_", " ")}')
    ax.set_xlabel('Moyle flow'); ax.set_ylabel('Constraint, % of available wind')
    ax.legend(title='NI wind availability', fontsize=7)
    ax.tick_params(axis='x', rotation=20)
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'ni_constraint_by_moyle.png'), dpi=150)

fig, ax = plt.subplots(figsize=(11, 3.5))
share = 100 * day['con'] / day['avail']
ax.plot(day.index, share.rolling(7, center=True).mean(), lw=1, color='#3b6ea5', label='NI constraint, 7-day mean')
for _, r in o275.iterrows():
    ax.axvspan(r['start'], r['finish'] + pd.Timedelta(days=1), color='#c0392b', alpha=0.06)
ax.set_ylabel('% of available wind'); ax.set_title('NI wind constraint and planned 275 kV outages (shaded)')
ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, 'ni_constraint_outages_timeline.png'), dpi=150)
