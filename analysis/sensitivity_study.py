"""Sensitivity study: scale scenario inputs, run Gamma, tabulate 2050 and 2100 results.

Usage (from the repository folder, after activating the virtual environment):
    python analysis/sensitivity_study.py            # runs every variant (about 20 minutes with charts)
    python analysis/sensitivity_study.py --tables   # rebuild tables and charts from finished runs

How it works:
1. Copies Gamma.py and Data_inputs to analysis/sensitivity_run/ (the real inputs are not touched).
2. Writes a scenario workbook there holding the base scenario plus one row per variant.
3. Runs Gamma.py in that folder.
4. Writes analysis/output/sensitivity_results.csv, sensitivity_tables.md and a fossil-share chart
   per family; Gamma's own monthly GWh overview chart for each run stays in
   analysis/sensitivity_run/scenario_outputs/<run>/.

Edit BASE, FAMILIES and FACTORS below to change the study.
"""
import os
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TAG = os.environ.get('GAMMA_RESIDUAL_BASIS', 'available')
RUN_DIR = os.path.join(HERE, 'sensitivity_run' + ('' if TAG == 'available' else '_' + TAG))
OUT = os.path.join(HERE, 'output', 'sensitivity' + ('' if TAG == 'available' else '_' + TAG))

BASE = 'EirGrid_Extended'                 # scenario row the variants are copied from
FACTORS = (1.5, 2.0, 2.5)                 # +50%, +100%, +150%
FAMILIES = {
    # family name: (label, input columns multiplied by the factor)
    'heat_transport': ('Heat and transport electrification pace',
                       ('heat_demand_growth_twh_per_year', 'transport_demand_growth_twh_per_year')),
    'build': ('Wind, solar and battery build rate',
              ('build_rate_wind_ie', 'build_rate_wind_ni', 'build_rate_wind_offshore',
               'build_rate_solar_ie', 'build_rate_solar_ni',
               'storage_power_build_rate_mw', 'storage_energy_build_rate_mwh')),
}
YEARS = (2050, 2100)


def run_name(family, factor):
    return f"S_{family}_x{str(factor).replace('.', 'p')}"


def build_workbook():
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    shutil.copy(os.path.join(REPO, 'Gamma.py'), RUN_DIR)
    shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(RUN_DIR, 'Data_inputs'))
    path = os.path.join(RUN_DIR, 'Data_inputs', 'scenariosXLSX.xlsx')
    wb = openpyxl.load_workbook(path)
    ws = wb['Scenarios']
    hdr = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(hdr)}
    src = next(r for r in range(3, ws.max_row + 1) if ws.cell(r, 1).value == BASE)
    base = [ws.cell(src, c).value for c in range(1, ws.max_column + 1)]
    ws.delete_rows(3, ws.max_row)
    rows = [('base', 1.0)] + [(f, k) for f in FAMILIES for k in FACTORS]
    for i, (family, factor) in enumerate(rows):
        r = 3 + i
        for c, v in enumerate(base, 1):
            if isinstance(v, str) and v.startswith('='):
                v = f'=C{r}+D{r}+E{r}'          # total demand growth = background + heat + transport
            ws.cell(r, c).value = v
        if family == 'base':
            ws.cell(r, col['scenario']).value = 'S_base'
            continue
        ws.cell(r, col['scenario']).value = run_name(family, factor)
        for field in FAMILIES[family][1]:
            ws.cell(r, col[field]).value = float(ws.cell(r, col[field]).value) * factor
        ws.cell(r, col['description']).value = f"Sensitivity: {BASE} with {FAMILIES[family][0].lower()} x{factor}"
    wb.save(path)


def run_gamma():
    subprocess.run([sys.executable, 'Gamma.py'], cwd=RUN_DIR, check=True)


def collect():
    o = os.path.join(RUN_DIR, 'scenario_outputs')
    a = pd.read_csv(os.path.join(o, 'all_scenarios_by_year.csv')).groupby(['Scenario', 'Year']).last()
    rows = []
    runs = [('base', 1.0, 'S_base')] + [(f, k, run_name(f, k)) for f in FAMILIES for k in FACTORS]
    for family, factor, sc in runs:
        w = pd.read_csv(os.path.join(o, sc, 'summary_wind.csv')).set_index('Year')
        s = pd.read_csv(os.path.join(o, sc, 'summary_solar.csv')).set_index('Year')
        t = pd.read_csv(os.path.join(o, sc, 'summary_total.csv')).set_index('Year')
        for y in YEARS:
            r = a.loc[(sc, y)]
            rows.append({
                'family': family, 'change': 'base' if family == 'base' else f'+{round((factor - 1) * 100)}%',
                'run': sc, 'year': y,
                'demand_TWh': round(t.loc[y, 'Demand_TWh'], 1),
                'wind_GW': round(r['Wind_Cap_GW'], 1), 'solar_GW': round(r['Solar_Cap_GW'], 1),
                'fossil_pct': round(r['Overall_Fossil_Fuel_Pct'], 1),
                'renewable_pct': round(r['Overall_Renewables_Pct'], 1),
                'constraint_pct': round(t.loc[y, 'Constraint_%'], 1),
                'curtailment_pct': round(t.loc[y, 'Curtailment_%'], 1),
                'wind_cf_pct': round(r['Wind_Fleet_CF_%_SEM'], 1),
                'solar_cf_pct': round(r['Solar_CF_%'], 1),
                'firm_GW': round(r['Firm_Capacity_Required_GW'], 1),
            })
    return pd.DataFrame(rows), a


def write_outputs(df, a):
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, 'sensitivity_results.csv'), index=False)
    cols = ['change', 'demand_TWh', 'wind_GW', 'solar_GW', 'fossil_pct', 'renewable_pct', 'constraint_pct',
            'curtailment_pct', 'wind_cf_pct', 'solar_cf_pct', 'firm_GW']
    md = []
    for family, (label, _) in FAMILIES.items():
        for y in YEARS:
            sub = df[((df.family == family) | (df.family == 'base')) & (df.year == y)][cols]
            md.append(f'### {label}, {y}\n\n' + sub.to_markdown(index=False) + '\n')
        fig, ax = plt.subplots(figsize=(7, 3.6))
        for sc, lab in [('S_base', 'base')] + [(run_name(family, k), f'+{round((k - 1) * 100)}%') for k in FACTORS]:
            x = a.loc[sc]['Overall_Fossil_Fuel_Pct']
            ax.plot(x.index, x.values, lw=1.8, label=lab)
        ax.axhline(10, color='#444', lw=0.9, ls='-.')
        ax.set_ylim(0, 100); ax.set_xlim(2026, 2100); ax.set_ylabel('Fossil, % of primary energy')
        ax.set_title(label, loc='left', fontsize=10, fontweight='bold')
        ax.spines[['top', 'right']].set_visible(False); ax.grid(axis='y', color='#e6e6e6')
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout(); fig.savefig(os.path.join(OUT, f'sensitivity_{family}_fossil.png'), dpi=600)
        plt.close(fig)
    with open(os.path.join(OUT, 'sensitivity_tables.md'), 'w') as f:
        f.write('\n'.join(md))
    print('\n'.join(md))


if __name__ == '__main__':
    if '--tables' not in sys.argv:
        build_workbook()
        run_gamma()
    write_outputs(*collect())
