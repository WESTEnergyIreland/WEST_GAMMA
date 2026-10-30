"""Grid reinforcement study: headroom growth, interconnector exports and marginal returns.

Three questions, all on EirGrid_Extended to 2050 (and one Historical_Trend run):
1. Headroom growth: Ireland's zonal headroom grows at a uniform 0, 1, 2, 4 or 7.3% a year from
   2026 (headroom_curve = reinforcement_pct; NI at 0.93% a year plus the North-South step).
   7.3% a year gives the 89% growth by 2035 that EirGrid's GSS-1 results imply.
2. Exports: each of those runs again with interconnector flows in the dispatch
   (GAMMA_IC_DISPATCH=1; exports at 50% of capacity, imports at 70%, the group's 24 Oct values).
3. Marginal returns: wind, solar and battery build x1.0, x1.5 and x2.0 at 0% and 7.3% headroom
   growth. The marginal yield is the extra wind + solar energy delivered per extra GW installed.
Plus Historical_Trend with 0% headroom growth (the recorded effective limit did not grow
2021-2025; analysis/headroom_history.py) against its current 0.5% a year.

Usage:
    python analysis/grid_reinforcement_study.py            # build, run (two runs in parallel), tabulate
    python analysis/grid_reinforcement_study.py --tables   # tabulate finished runs
Outputs: analysis/output/grid_reinforcement/
"""
import os
import shutil
import subprocess
import sys

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'output', 'grid_reinforcement')
RUN_DIRS = {'off': os.path.join(HERE, 'grid_run_ic_off'), 'on': os.path.join(HERE, 'grid_run_ic_on')}
RATES = (0.0, 1.0, 2.0, 4.0, 7.3)
BUILD = (1.0, 1.5, 2.0)
BUILD_RATES = (0.0, 7.3)
YEARS = (2035, 2050)
BUILD_COLS = ('build_rate_wind_ie', 'build_rate_wind_ni', 'build_rate_wind_offshore',
              'build_rate_solar_ie', 'build_rate_solar_ni',
              'storage_power_build_rate_mw', 'storage_energy_build_rate_mwh')


def tag(x):
    return str(x).replace('.', 'p')


def runs(ic):
    """(name, base scenario, IE headroom %/yr, build factor)."""
    out = [(f'G_r{tag(r)}', 'EirGrid_Extended', r, 1.0) for r in RATES]
    if ic == 'off':
        out += [(f'G_r{tag(r)}_b{tag(b)}', 'EirGrid_Extended', r, b)
                for r in BUILD_RATES for b in BUILD if b != 1.0]
        out += [('H_r0', 'Historical_Trend', 0.0, 1.0), ('H_r0p5', 'Historical_Trend', 0.5, 1.0)]
    return out


def build(ic):
    d = RUN_DIRS[ic]
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    shutil.copy(os.path.join(REPO, 'Gamma.py'), d)
    shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(d, 'Data_inputs'))
    path = os.path.join(d, 'Data_inputs', 'scenariosXLSX.xlsx')
    wb = openpyxl.load_workbook(path)
    ws = wb['Scenarios']
    col = {c.value: i + 1 for i, c in enumerate(ws[1])}
    src = {ws.cell(r, 1).value: [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
           for r in range(3, ws.max_row + 1)}
    ws.delete_rows(3, ws.max_row)
    for i, (name, base, rate, factor) in enumerate(runs(ic)):
        r = 3 + i
        for c, v in enumerate(src[base], 1):
            if isinstance(v, str) and v.startswith('='):
                v = f'=C{r}+D{r}+E{r}'
            ws.cell(r, c).value = v
        ws.cell(r, col['scenario']).value = name
        ws.cell(r, col['target_year']).value = 2050
        ws.cell(r, col['headroom_curve']).value = 'reinforcement_pct'
        ws.cell(r, col['ie_reinforcement_pct']).value = rate
        ws.cell(r, col['ni_reinforcement_pct']).value = 0.93
        for f in BUILD_COLS:
            ws.cell(r, col[f]).value = float(ws.cell(r, col[f]).value or 0) * factor
        ws.cell(r, col['description']).value = (f'Grid study: {base}, IE headroom {rate}%/yr, build x{factor}, '
                                                f'interconnector dispatch {ic}')
    wb.save(path)


def run_all():
    procs = []
    for ic, d in RUN_DIRS.items():
        env = dict(os.environ, GAMMA_IC_DISPATCH='1' if ic == 'on' else '0', GAMMA_CHARTS='0', MPLBACKEND='Agg')
        log = open(os.path.join(d, 'run_stdout.txt'), 'w')
        procs.append(subprocess.Popen([sys.executable, 'Gamma.py'], cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT))
    for p in procs:
        if p.wait() != 0:
            raise SystemExit('A Gamma run failed: see run_stdout.txt in the run folders.')


def collect():
    rows = []
    for ic, d in RUN_DIRS.items():
        o = os.path.join(d, 'scenario_outputs')
        a = pd.read_csv(os.path.join(o, 'all_scenarios_by_year.csv')).groupby(['Scenario', 'Year']).last()
        for name, base, rate, factor in runs(ic):
            t = pd.read_csv(os.path.join(o, name, 'summary_total.csv')).set_index('Year')
            for y in YEARS:
                r = a.loc[(name, y)]
                rows.append({'run': name, 'base': base, 'ic_dispatch': ic, 'ie_headroom_pct_yr': rate,
                             'build_x': factor, 'year': y, **{k: t.loc[y, k] for k in t.columns if k != 'Year'},
                             **{k: r[k] for k in ('Wind_Cap_GW', 'Solar_Cap_GW', 'Overall_Fossil_Fuel_Pct',
                                                  'Firm_Capacity_Required_GW')}})
    return pd.DataFrame(rows)


if __name__ == '__main__':
    if '--tables' not in sys.argv:
        for ic in RUN_DIRS:
            build(ic)
        run_all()
    os.makedirs(OUT, exist_ok=True)
    df = collect()
    df.to_csv(os.path.join(OUT, 'grid_reinforcement_results.csv'), index=False)
    print(df.to_string())
