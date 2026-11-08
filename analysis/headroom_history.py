"""Recorded network headroom by year: has the effective limit grown?

For each year with records, finds the headroom that reproduces that year's recorded constraint,
with sigma held at its 2024-2026 value (1.17 IE, 1.89 NI; refitted 8 Nov 2026 after the closed-form correction) so that years are comparable:
- IE and NI as a whole, from their hourly wind + solar records;
- each IE zone, from the IE hourly availability split by today's zone MW (the only split on
  record, as in Gamma's zonal backcast) and the zone's recorded annual constraint %.

H is an effective limit. It rises with reinforcement and falls when capacity connects behind
existing bottlenecks, so its trend is the net of both. The zone split by today's MW means a zone
whose share of capacity grew shows a falling H even if its network did not change.

Usage: python analysis/headroom_history.py   (writes analysis/output/headroom_history.csv)
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
import Gamma as G  # noqa: E402

SIGMA = {'IE': 1.17, 'NI': 1.89}


def hourly(reg):
    w = G.load_dd_hourly(os.path.join(REPO, 'Data_inputs', G.DD_FILES[reg])).set_index('datetime')
    s = G.load_dd_hourly(os.path.join(REPO, 'Data_inputs', G.SOLAR_DD_FILES[reg])).set_index('datetime')
    c = w.join(s[['avail_mw', 'cons_mw']], rsuffix='_s', how='left').fillna(0.0)
    c['avail_mw'] += c['avail_mw_s']
    c['cons_mw'] += c['cons_mw_s']
    return c.reset_index()[['year', 'avail_mw', 'cons_mw']]


def cagr(series):
    s = series.dropna()
    if len(s) < 2 or s.iloc[0] <= 0:
        return np.nan
    yrs = s.index[-1] - s.index[0]
    return 100 * ((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1)


def slope_pct(series):
    """Least-squares trend of ln H, % a year (less sensitive to one odd year than end to end)."""
    s = series.dropna()
    if len(s) < 3:
        return np.nan
    b = np.polyfit(s.index.values, np.log(s.values), 1)[0]
    return 100 * (np.exp(b) - 1)


def main():
    rows = []
    dd = {r: hourly(r) for r in ('IE', 'NI')}
    for reg, df in dd.items():
        for y, g in df.groupby('year'):
            if len(g) < 8000:          # skip part years
                continue
            pct = 100 * g['cons_mw'].sum() / g['avail_mw'].sum()
            h = G.calibrate_headroom(g['avail_mw'].values, pct, SIGMA[reg])
            rows.append({'area': reg, 'year': y, 'constraint_pct': pct,
                         'avail_mean_mw': g['avail_mw'].mean(), 'headroom_mw': h})

    hist, caps = G.load_zonal_history(os.path.join(REPO, 'Data_inputs', G.ZONAL_HISTORY_FILE))
    ann = hist[(hist['month'] == 0) & (hist['kind'] == 'constraints')].pivot(index='zone', columns='year', values='pct')
    ie_cap = sum(caps[z] for z in G.IE_ZONES)
    for y in ann.columns:
        x_ie = dd['IE'].loc[dd['IE']['year'] == y, 'avail_mw'].values
        if len(x_ie) < 8000:
            continue
        for z in G.IE_ZONES:
            x = x_ie * caps[z] / ie_cap
            rows.append({'area': z, 'year': y, 'constraint_pct': ann.loc[z, y],
                         'avail_mean_mw': x.mean(),
                         'headroom_mw': G.calibrate_headroom(x, ann.loc[z, y], SIGMA['IE'])})

    out = pd.DataFrame(rows)
    os.makedirs(os.path.join(HERE, 'output'), exist_ok=True)
    out.round(2).to_csv(os.path.join(HERE, 'output', 'headroom_history.csv'), index=False)

    h = out.pivot(index='area', columns='year', values='headroom_mw')
    c = out.pivot(index='area', columns='year', values='constraint_pct')
    order = ['IE', 'NI'] + G.IE_ZONES
    tab = h.reindex(order).round(0)
    tab['end_to_end_%/yr'] = [cagr(h.loc[a]) for a in tab.index]
    tab['trend_%/yr'] = [slope_pct(h.loc[a]) for a in tab.index]
    print("Effective headroom (MW) that reproduces each year's recorded constraint, sigma held fixed")
    print(tab.round(1).to_string())
    print("\nRecorded constraint (% of available)")
    print(c.reindex(order).round(1).to_string())


if __name__ == '__main__':
    main()
