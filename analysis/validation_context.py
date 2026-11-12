"""Context for the two validation exercises in the Phase 1 paper.

1. Persistence benchmark for the rolling one-year-ahead constraint hindcast (paper Table 3): the
   model's error set beside the error from assuming each year's constraint share equals the year
   before. Also the hourly fit of the constraint curve on its fit years.
2. Weather-year spread of the EirGrid ECP-GSS-1 comparison (paper Table 4): the 2030 and 2035
   offshore cases run on each complete weather year, with the share of each total that is the
   residual curtailment carried from 2026.

Usage (from the repository folder, after activating the virtual environment):
    python analysis/validation_context.py              # both parts (about 5 minutes)
    python analysis/validation_context.py --hindcast   # part 1 only (seconds)

Part 2 copies Gamma.py and Data_inputs to analysis/validation_context_run/ (the real inputs are
not touched). Writes analysis/output/validation_context/: persistence_benchmark.csv,
hourly_fit.csv, weather_spread.csv and validation_context.md.
"""
import os
import shutil
import subprocess
import sys

import numpy as np
import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from Gamma import (CONSTRAINT_FIT_YEARS, DD_FILES, SOLAR_DD_FILES, expected_constraint_mw,  # noqa: E402
                   fit_constraint_model, load_dd_hourly)

RUN_DIR = os.path.join(HERE, 'validation_context_run')
OUT = os.path.join(HERE, 'output', 'validation_context')
DATA = os.path.join(REPO, 'Data_inputs')
SCENARIO = 'EirGrid_Validation_2030_2035'
EIRGRID_TOTAL = {2030: 26.8, 2035: 28.5}      # ECP-GSS-1, Ireland, % of available energy (paper Table 4)
EIRGRID_WEATHER_YEAR = 2020
WEATHER_YEARS = list(range(2014, 2026))       # complete recorded years


def wind_plus_solar(reg):
    """Hourly available output and constraint, wind plus solar, as Gamma fits them."""
    w = load_dd_hourly(os.path.join(DATA, DD_FILES[reg])).set_index('datetime')
    s = load_dd_hourly(os.path.join(DATA, SOLAR_DD_FILES[reg])).set_index('datetime')[['avail_mw', 'cons_mw']]
    c = w.join(s, rsuffix='_solar', how='left').fillna({'avail_mw_solar': 0.0, 'cons_mw_solar': 0.0})
    c['avail_mw'] += c['avail_mw_solar']
    c['cons_mw'] += c['cons_mw_solar']
    return c.reset_index()[['datetime', 'year', 'avail_mw', 'cons_mw']]


def hindcast():
    dd = {r: wind_plus_solar(r) for r in ('IE', 'NI')}
    rows = []
    years = sorted(set(dd['IE']['year']))[1:]
    for y in years:
        row, tot = {'year': y}, {'actual': 0.0, 'model': 0.0, 'persistence': 0.0}
        for r in ('IE', 'NI'):
            prev, this = dd[r][dd[r]['year'] == y - 1], dd[r][dd[r]['year'] == y]
            p = fit_constraint_model(dd[r], [y - 1])
            model = expected_constraint_mw(this['avail_mw'].values, p['limit_mw'], p['sigma']).sum()
            actual = this['cons_mw'].sum()
            persistence = prev['cons_mw'].sum() / prev['avail_mw'].sum() * this['avail_mw'].sum()
            row[f'{r}_actual_gwh'] = actual / 1000
            row[f'{r}_model_err_pct'] = 100 * (model / actual - 1)
            row[f'{r}_persistence_err_pct'] = 100 * (persistence / actual - 1)
            tot['actual'] += actual
            tot['model'] += model
            tot['persistence'] += persistence
        row['all_island_model_err_pct'] = 100 * (tot['model'] / tot['actual'] - 1)
        row['all_island_persistence_err_pct'] = 100 * (tot['persistence'] / tot['actual'] - 1)
        rows.append(row)
    bench = pd.DataFrame(rows).round(2)

    fit_rows = []
    for r in ('IE', 'NI'):
        f = dd[r][dd[r]['year'].isin(CONSTRAINT_FIT_YEARS[r])]
        x, c = f['avail_mw'].values, f['cons_mw'].values
        p = fit_constraint_model(dd[r], CONSTRAINT_FIT_YEARS[r])
        m = expected_constraint_mw(x, p['limit_mw'], p['sigma'])
        flat = c.sum() / x.sum() * x
        ss = ((c - c.mean()) ** 2).sum()
        fit_rows.append({'region': r, 'fit_years': '-'.join(str(v) for v in (CONSTRAINT_FIT_YEARS[r][0], CONSTRAINT_FIT_YEARS[r][-1])),
                         'median_limit_mw': round(p['limit_mw']), 'sigma': round(p['sigma'], 2),
                         'max_available_mw': round(x.max()), 'mean_constraint_mw': round(c.mean(), 1),
                         'rmse_mw': round(float(np.sqrt(np.mean((m - c) ** 2))), 1),
                         'r2': round(1 - ((m - c) ** 2).sum() / ss, 3),
                         'r2_flat_share': round(1 - ((flat - c) ** 2).sum() / ss, 3)})
    return bench, pd.DataFrame(fit_rows)


def weather_spread():
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    shutil.copy(os.path.join(REPO, 'Gamma.py'), RUN_DIR)
    shutil.copytree(DATA, os.path.join(RUN_DIR, 'Data_inputs'))
    book = os.path.join(RUN_DIR, 'Data_inputs', 'scenariosXLSX.xlsx')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GAMMA_')}
    env['GAMMA_CHARTS'] = '0'
    rows = []
    for wy in WEATHER_YEARS:
        shutil.copy(os.path.join(DATA, 'scenariosXLSX.xlsx'), book)
        wb = openpyxl.load_workbook(book)
        ws = wb['Scenarios']
        col = {c.value: i + 1 for i, c in enumerate(ws[1])}
        for r in range(3, ws.max_row + 1):
            if ws.cell(r, col['scenario']).value == SCENARIO:
                ws.cell(r, col['weather_years']).value = wy
        wb.save(book)
        print(f">> {SCENARIO} on weather year {wy}", flush=True)
        log = subprocess.run([sys.executable, 'Gamma.py', SCENARIO], cwd=RUN_DIR, env=env, capture_output=True, text=True)
        if log.returncode != 0:
            raise RuntimeError(f"Gamma failed for weather year {wy}:\n{log.stdout[-800:]}\n{log.stderr[-800:]}")
        o = os.path.join(RUN_DIR, 'scenario_outputs', SCENARIO)
        f = pd.read_csv(os.path.join(o, 'forecast_results.csv')).set_index('Year')
        s = pd.read_csv(os.path.join(o, 'summary_system.csv')).set_index('Year')
        for y in EIRGRID_TOTAL:
            # Ireland total as analysis/eirgrid_validation.py: IE constraint plus system-wide curtailment.
            curt = s.loc[y, 'SNSP_Curtailment_%'] + s.loc[y, 'MinGen_Curtailment_%'] + s.loc[y, 'Other_incl_RoCoF_%']
            rows.append({'weather_year': wy, 'case_year': y, 'gamma_constraint_pct': round(f.loc[y, 'Con_WS_IE_%'], 2),
                         'gamma_curtailment_pct': round(curt, 2),
                         'of_which_residual_pts': round(s.loc[y, 'Other_incl_RoCoF_%'], 2),
                         'gamma_total_pct': round(f.loc[y, 'Con_WS_IE_%'] + curt, 2),
                         'eirgrid_total_pct': EIRGRID_TOTAL[y]})
    return pd.DataFrame(rows)


def write_report(bench, fit, spread):
    os.makedirs(OUT, exist_ok=True)
    bench.to_csv(os.path.join(OUT, 'persistence_benchmark.csv'), index=False)
    fit.to_csv(os.path.join(OUT, 'hourly_fit.csv'), index=False)
    mae = bench.filter(like='err_pct').abs().mean()
    lines = ["# Context for the validation exercises", "",
             "Written by `analysis/validation_context.py`.", "",
             "## 1. One-year-ahead constraint hindcast against persistence", "",
             "Error in constraint energy, %. Persistence applies the previous year's constraint share to the "
             "year's available output. The last year covers the months on record.", "",
             "| Year | IE model | IE persistence | NI model | NI persistence | All-island model | All-island persistence |",
             "|---|---|---|---|---|---|---|"]
    for _, r in bench.iterrows():
        lines.append(f"| {int(r['year'])} | {r['IE_model_err_pct']:+.1f} | {r['IE_persistence_err_pct']:+.1f} | "
                     f"{r['NI_model_err_pct']:+.1f} | {r['NI_persistence_err_pct']:+.1f} | "
                     f"{r['all_island_model_err_pct']:+.1f} | {r['all_island_persistence_err_pct']:+.1f} |")
    lines.append(f"| Mean absolute error | {mae['IE_model_err_pct']:.1f} | {mae['IE_persistence_err_pct']:.1f} | "
                 f"{mae['NI_model_err_pct']:.1f} | {mae['NI_persistence_err_pct']:.1f} | "
                 f"{mae['all_island_model_err_pct']:.1f} | {mae['all_island_persistence_err_pct']:.1f} |")
    lines += ["", "Hourly fit of the constraint curve on its fit years:", "",
              "| Region | Fit years | Median limit (MW) | sigma | Highest available output (MW) | RMSE (MW) | "
              "Mean constraint (MW) | R2 | R2 of a flat share |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in fit.iterrows():
        lines.append(f"| {r['region']} | {r['fit_years']} | {r['median_limit_mw']:,} | {r['sigma']} | "
                     f"{r['max_available_mw']:,} | {r['rmse_mw']} | {r['mean_constraint_mw']} | {r['r2']} | {r['r2_flat_share']} |")
    if spread is not None:
        spread.to_csv(os.path.join(OUT, 'weather_spread.csv'), index=False)
        lines += ["", "## 2. EirGrid ECP-GSS-1 offshore cases by weather year", "",
                  f"`{SCENARIO}` run on each complete weather year. Ireland, % of available wind and solar. "
                  f"EirGrid's study uses {EIRGRID_WEATHER_YEAR} weather.", "",
                  "| Weather year | 2030 total | of which residual | 2035 total | of which residual |", "|---|---|---|---|---|"]
        p = spread.pivot(index='weather_year', columns='case_year', values=['gamma_total_pct', 'of_which_residual_pts'])
        for wy, r in p.iterrows():
            lines.append(f"| {wy} | {r[('gamma_total_pct', 2030)]:.1f} | {r[('of_which_residual_pts', 2030)]:.1f} | "
                         f"{r[('gamma_total_pct', 2035)]:.1f} | {r[('of_which_residual_pts', 2035)]:.1f} |")
        t = p['gamma_total_pct']
        lines += [f"| Mean (standard deviation) | {t[2030].mean():.1f} ({t[2030].std():.1f}) | | "
                  f"{t[2035].mean():.1f} ({t[2035].std():.1f}) | |",
                  f"| Range | {t[2030].min():.1f} to {t[2030].max():.1f} | | {t[2035].min():.1f} to {t[2035].max():.1f} | |",
                  f"| EirGrid ({EIRGRID_WEATHER_YEAR} weather) | {EIRGRID_TOTAL[2030]} | | {EIRGRID_TOTAL[2035]} | |"]
    with open(os.path.join(OUT, 'validation_context.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    bench_df, fit_df = hindcast()
    spread_df = None if '--hindcast' in sys.argv[1:] else weather_spread()
    write_report(bench_df, fit_df, spread_df)
