"""Interconnector sensitivity: 0%, 70% and 100% of interconnector capacity usable for both
imports and exports, on EirGrid_Extended and Historical_Trend, to 2075.

Usage (from the repository folder):
    python analysis/interconnector_sensitivity.py            # runs the six cases (CSV only)
    python analysis/interconnector_sensitivity.py --tables   # rebuild the table from finished runs

How it works:
1. Copies Gamma.py and Data_inputs to analysis/ic_run/ (the real inputs are not touched).
2. Writes a scenario workbook there with one row per pathway and availability, target year 2075.
3. Runs Gamma.py there with GAMMA_IC_DISPATCH=1, so interconnector flows enter the 15-minute
   dispatch. The 0% case has no flows and must reproduce the main run's dispatch; the script
   checks this against scenario_outputs/ if a main run is present. Its fossil share is higher
   than the main run's, because these runs count the imports in the dispatch (none at 0%) and
   the main runs count a fixed 4% of primary energy as imported electricity.
4. Writes analysis/output/interconnector_sensitivity.csv and .md.

Interconnector capacity is Gamma's: 1,450 MW existing, Celtic 700 MW from April 2028 and
MaresConnect 750 MW from 2031 (2,900 MW from 2031). It does not grow with the build.
0% and 100% are bounds, not forecasts. 100% assumes Great Britain and France can take every
surplus MW and supply every deficit MW up to the link ratings in every interval.
"""
import os
import shutil
import subprocess
import sys

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUN_DIR = os.path.join(HERE, 'ic_run')
OUT = os.path.join(HERE, 'output')

BASES = ('EirGrid_Extended', 'Historical_Trend')
AVAILABILITY = (0.0, 0.7, 1.0)
TARGET_YEAR = 2075
YEARS = (2026, 2035, 2050, 2075)


def run_name(base, a):
    return f"IC_{base}_{round(a * 100)}"


def build_workbook():
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    shutil.copy(os.path.join(REPO, 'Gamma.py'), RUN_DIR)
    shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(RUN_DIR, 'Data_inputs'))
    path = os.path.join(RUN_DIR, 'Data_inputs', 'scenariosXLSX.xlsx')
    wb = openpyxl.load_workbook(path)
    ws = wb['Scenarios']
    col = {c.value: i + 1 for i, c in enumerate(ws[1])}
    rows = {ws.cell(r, 1).value: [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            for r in range(3, ws.max_row + 1)}
    ws.delete_rows(3, ws.max_row)
    r = 3
    for base in BASES:
        for a in AVAILABILITY:
            for c, v in enumerate(rows[base], 1):
                if isinstance(v, str) and v.startswith('='):
                    v = f'=C{r}+D{r}+E{r}'          # total demand growth = background + heat + transport
                ws.cell(r, c).value = v
            ws.cell(r, col['scenario']).value = run_name(base, a)
            ws.cell(r, col['description']).value = (
                f"Interconnector sensitivity: {base}, {round(a * 100)}% of capacity for imports and exports")
            ws.cell(r, col['ic_export_availability']).value = a
            ws.cell(r, col['ic_import_availability']).value = a
            ws.cell(r, col['target_year']).value = TARGET_YEAR
            ws.cell(r, col['run']).value = 'yes'
            r += 1
    wb.save(path)


def run_gamma():
    env = dict(os.environ, GAMMA_IC_DISPATCH='1', GAMMA_CHARTS='0')
    subprocess.run([sys.executable, 'Gamma.py'], cwd=RUN_DIR, check=True, env=env)


def first_short_year(f):
    short = f[f['Gas_Days_Short_per_Year'] > 0]
    return int(short['Year'].iloc[0]) if len(short) else f'none by {TARGET_YEAR}'


def collect():
    o = os.path.join(RUN_DIR, 'scenario_outputs')
    out = []
    for base in BASES:
        for a in AVAILABILITY:
            f = pd.read_csv(os.path.join(o, run_name(base, a), 'forecast_results.csv'))
            t = pd.read_csv(os.path.join(o, run_name(base, a), 'summary_total.csv')).set_index('Year')
            first = first_short_year(f)
            f = f.set_index('Year')
            for y in YEARS:
                r = f.loc[y]
                fossil = r['Total_Fossil_Energy_TWh'] - r['Fossil_Electricity_Consumed_TWh'] + r['Firm_Gas_Burnt_TWh']
                out.append({
                    'pathway': base, 'ic_availability_pct': round(a * 100), 'year': y,
                    'ic_capacity_GW': r['Interconnector_Capacity_GW'],
                    'import_TWh': round(r['Import_TWh'], 1), 'export_TWh': round(r['Export_TWh'], 1),
                    'export_wind_solar_TWh': round(r['Export_Wind_Solar_TWh'], 1),
                    'dispatch_down_pct': round(t.loc[y, 'Constraint_%'] + t.loc[y, 'Curtailment_%'], 1),
                    'firm_generation_TWh': round(r['Fossil_Firm_Generation_TWh'], 1),
                    'fossil_primary_TWh': round(fossil, 1),
                    'fossil_share_primary_pct': round(r['Primary_Fossil_Share_Pct'], 1),
                    'import_share_primary_pct': round(r['Primary_Imported_Electricity_Share_Pct'], 1),
                    'gas_annual_TWh_GCV': round(r['Gas_Power_TWh_GCV'] + r['Gas_NonPower_TWh_GCV'], 1),
                    'gas_worst_day_GWh': round(r['Gas_Worst_Day_GWh'], 0),
                    'gas_worst_day_power_GWh': round(r['Gas_Worst_Day_Power_GWh'], 0)
                    if 'Gas_Worst_Day_Power_GWh' in r else None,
                    'gas_supply_GWh_per_day': round(r['Gas_Supply_GWh_per_Day'], 0),
                    'gas_days_short': round(r['Gas_Days_Short_per_Year'], 1),
                    'first_gas_shortfall_year': first,
                })
    return pd.DataFrame(out)


def check_against_main(df):
    """The 0% case has no flows, so it must equal the main run where one is present."""
    msgs = []
    for base in BASES:
        p = os.path.join(REPO, 'scenario_outputs', base, 'forecast_results.csv')
        if not os.path.exists(p):
            msgs.append(f'{base}: no main run in scenario_outputs/, 0% case not checked')
            continue
        m = pd.read_csv(p).set_index('Year')
        z = pd.read_csv(os.path.join(RUN_DIR, 'scenario_outputs', run_name(base, 0.0),
                                     'forecast_results.csv')).set_index('Year')
        for c in ('Primary_Fossil_TWh', 'Gas_Worst_Day_GWh', 'Fossil_Firm_Generation_TWh'):
            d = (m.loc[z.index, c] - z[c]).abs().max()
            msgs.append(f'{base}: 0% case against main run, max difference in {c} = {d:.4f}')
    return msgs


if __name__ == '__main__':
    if '--tables' not in sys.argv:
        build_workbook()
        run_gamma()
    df = collect()
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, 'interconnector_sensitivity.csv'), index=False)
    with open(os.path.join(OUT, 'interconnector_sensitivity.md'), 'w') as fh:
        fh.write(df.to_markdown(index=False) + '\n\n' + '\n'.join(check_against_main(df)) + '\n')
    print(df.to_string(index=False))
    print('\n'.join(check_against_main(df)))
