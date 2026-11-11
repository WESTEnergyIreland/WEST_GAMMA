"""How well do the hourly records identify the spread sigma of the effective network limit?

Usage (from the repository folder): python analysis/sigma_identification.py [n_boot]

1. Profile: for each jurisdiction, on the 2024-2026 hourly records, fix sigma on a grid, solve the
   limit H that matches constrained energy exactly (eq. S2.1), and report the hourly RMSE.
2. Block bootstrap: resample calendar months with replacement (n_boot times, default 100), refit
   sigma and H, and report the 5th, 50th and 95th percentiles. Months keep the serial correlation
   of hourly errors, which an hourly bootstrap would ignore.
Writes analysis/output/sigma_profile.csv and sigma_bootstrap.csv.
The 90% interval is then used to rerun the EirGrid validation cases with GAMMA_SIGMA_IE / GAMMA_SIGMA_NI.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import brentq

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)
import Gamma as G  # noqa: E402

OUT = os.path.join(REPO, 'analysis', 'output')
YEARS = [2024, 2025, 2026]
GRID = [0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5]


def wind_plus_solar(reg):
    """Hourly records as Gamma fits them: wind plus solar where the solar file exists."""
    w = G.load_dd_hourly(G.DD_FILES[reg])
    sp = G.SOLAR_DD_FILES[reg]
    if not os.path.exists(sp):
        sp = os.path.join('Data_inputs', sp)
    if not os.path.exists(sp):
        return w
    sol = G.load_dd_hourly(sp).set_index('datetime')[['avail_mw', 'cons_mw']]
    c = w.set_index('datetime').join(sol, rsuffix='_solar', how='left').fillna(0.0)
    c['avail_mw'] += c['avail_mw_solar']
    c['cons_mw'] += c['cons_mw_solar']
    return c.reset_index()[['datetime', 'year', 'avail_mw', 'cons_mw']]


def main(n_boot=100):
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(20261108)
    prof, boot = [], []
    for reg in ('IE', 'NI'):
        dd = wind_plus_solar(reg)
        dd = dd[dd['year'].isin(YEARS)].copy()
        x, c = dd['avail_mw'].values, dd['cons_mw'].values
        for s in GRID:
            h = float(np.exp(brentq(lambda l: G.expected_constraint_mw(x, np.exp(l), s).sum() - c.sum(),
                                    0.0, np.log(x.max() * 100))))
            rmse = float(np.sqrt(np.mean((G.expected_constraint_mw(x, h, s) - c) ** 2)))
            prof.append({'region': reg, 'sigma': s, 'H_mw': round(h), 'rmse_mw': round(rmse, 2)})
        fit = G.fit_constraint_model(dd, YEARS)
        dd['ym'] = dd['year'] * 100 + pd.to_datetime(dd['datetime']).dt.month
        months = dd['ym'].unique()
        groups = {m: g for m, g in dd.groupby('ym')}
        for b in range(n_boot):
            pick = rng.choice(months, size=len(months), replace=True)
            sample = pd.concat([groups[m] for m in pick], ignore_index=True)
            sample['year'] = YEARS[0]
            p = G.fit_constraint_model(sample, [YEARS[0]])
            boot.append({'region': reg, 'rep': b, 'sigma': p['sigma'], 'H_mw': p['limit_mw']})
        b = pd.DataFrame([r for r in boot if r['region'] == reg])
        print(f"{reg}: fitted sigma {fit['sigma']:.2f}, H {fit['limit_mw']:.0f} MW; bootstrap sigma "
              f"5/50/95% = {b['sigma'].quantile(.05):.2f} / {b['sigma'].median():.2f} / {b['sigma'].quantile(.95):.2f}")
    pd.DataFrame(prof).to_csv(os.path.join(OUT, 'sigma_profile.csv'), index=False)
    pd.DataFrame(boot).to_csv(os.path.join(OUT, 'sigma_bootstrap.csv'), index=False)
    print(pd.DataFrame(prof).pivot(index='sigma', columns='region', values='rmse_mw').to_string())


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
