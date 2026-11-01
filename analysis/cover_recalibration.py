"""Re-fit headroom_pipeline_cover_pct against EirGrid ECP-GSS-1 on the current model.

The 40% cover was fitted on 28 October 2026, before residual curtailment moved to the delivered
basis (PRs #24, #25) and before Gamma reported surplus separately (PR #28). This study re-runs
EirGrid_Validation_2030_2035 (GSS-1 2030: 33% ECP + 2.6 GW offshore; 2035: 66% ECP + 4.7 GW
offshore; 2020 weather) at a range of cover values and compares Ireland's results with EirGrid's
on three bases:

1. constraint as Gamma removes it (network first, then system-wide limits): the basis of the
   original 40% fit;
2. total dispatch down (constraint plus curtailment plus surplus), which does not depend on the
   order in which the categories are removed;
3. constraint in EirGrid's order (surplus first): Gamma total minus surplus before constraint
   minus operational curtailment. Approximate, because Gamma's operational curtailment is
   computed after the network is applied.

Usage:
    python analysis/cover_recalibration.py            # build, run, tabulate
    python analysis/cover_recalibration.py --tables   # tabulate finished runs
Outputs: analysis/output/cover_recalibration/
"""
import os
import shutil
import subprocess
import sys

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUN_DIR = os.path.join(HERE, 'cover_run')
OUT = os.path.join(HERE, 'output', 'cover_recalibration')
BASE_SCENARIO = 'EirGrid_Validation_2030_2035'
COVERS = (0, 10, 20, 30, 40, 50, 60, 80)
# EirGrid GSS-1, Ireland, % of available controllable wind and solar (eirgrid_ecp_gss1_results_ie.csv)
EIRGRID = {2030: {'case': 'S4 33% ECP + 2.6 GW offshore', 'surplus': 18.7, 'curtailment': 2.4,
                  'constraint': 5.7, 'total': 26.8},
           2035: {'case': 'S8 66% ECP + 4.7 GW offshore', 'surplus': 21.5, 'curtailment': 0.9,
                  'constraint': 6.0, 'total': 28.5}}


def name(cover):
    return f'Cover_{cover:g}'


def build():
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    shutil.copy(os.path.join(REPO, 'Gamma.py'), RUN_DIR)
    shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(RUN_DIR, 'Data_inputs'))
    path = os.path.join(RUN_DIR, 'Data_inputs', 'scenariosXLSX.xlsx')
    wb = openpyxl.load_workbook(path)
    ws = wb['Scenarios']
    col = {c.value: i + 1 for i, c in enumerate(ws[1])}
    src = {ws.cell(r, 1).value: [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
           for r in range(3, ws.max_row + 1)}
    ws.delete_rows(3, ws.max_row)
    for i, cover in enumerate(COVERS):
        r = 3 + i
        for c, v in enumerate(src[BASE_SCENARIO], 1):
            if isinstance(v, str) and v.startswith('='):
                v = f'=C{r}+D{r}+E{r}'
            ws.cell(r, c).value = v
        ws.cell(r, col['scenario']).value = name(cover)
        ws.cell(r, col['headroom_pipeline_cover_pct']).value = cover
        ws.cell(r, col['description']).value = f'Cover recalibration: {BASE_SCENARIO} with {cover:g}% cover'
    wb.save(path)


def run():
    env = dict(os.environ, GAMMA_CHARTS='0', MPLBACKEND='Agg')
    with open(os.path.join(RUN_DIR, 'run_stdout.txt'), 'w') as log:
        if subprocess.call([sys.executable, 'Gamma.py'], cwd=RUN_DIR, env=env,
                           stdout=log, stderr=subprocess.STDOUT) != 0:
            raise SystemExit('Gamma run failed: see analysis/cover_run/run_stdout.txt')


def collect():
    rows = []
    o = os.path.join(RUN_DIR, 'scenario_outputs')
    for cover in COVERS:
        f = pd.read_csv(os.path.join(o, name(cover), 'forecast_results.csv')).set_index('Year')
        s = pd.read_csv(os.path.join(o, name(cover), 'summary_system.csv')).set_index('Year')
        for y, e in EIRGRID.items():
            con = f.loc[y, 'Con_WS_IE_%']
            curt = s.loc[y, 'SNSP_Curtailment_%'] + s.loc[y, 'MinGen_Curtailment_%'] + s.loc[y, 'Other_incl_RoCoF_%']
            total = con + curt
            surplus_before = s.loc[y, 'Surplus_Before_Constraint_%']
            op_curt = curt - s.loc[y, 'Surplus_%']
            con_eirgrid_order = total - surplus_before - op_curt
            rows.append({'cover_pct': cover, 'year': y, 'eirgrid_case': e['case'],
                         'gamma_constraint': round(con, 1), 'eirgrid_constraint': e['constraint'],
                         'gamma_total': round(total, 1), 'eirgrid_total': e['total'],
                         'gamma_constraint_eirgrid_order': round(con_eirgrid_order, 1),
                         'gamma_surplus_before_constraint': round(surplus_before, 1),
                         'eirgrid_surplus': e['surplus'],
                         'gamma_operational_curtailment': round(op_curt, 1),
                         'eirgrid_curtailment': e['curtailment']})
    return pd.DataFrame(rows)


def best_fit(df):
    """Cover value that minimises the summed squared error over 2030 and 2035, per basis."""
    out = []
    for basis, g, e in (('constraint, Gamma order', 'gamma_constraint', 'eirgrid_constraint'),
                        ('total dispatch down', 'gamma_total', 'eirgrid_total'),
                        ('constraint, EirGrid order', 'gamma_constraint_eirgrid_order', 'eirgrid_constraint')):
        err = df.assign(e2=(df[g] - df[e]) ** 2).groupby('cover_pct')['e2'].sum()
        best = err.idxmin()
        out.append({'basis': basis, 'best_cover_pct': best, 'rms_error_points': round((err[best] / 2) ** 0.5, 2)})
    return pd.DataFrame(out)


if __name__ == '__main__':
    if '--tables' not in sys.argv:
        build()
        run()
    os.makedirs(OUT, exist_ok=True)
    df = collect()
    fit = best_fit(df)
    df.to_csv(os.path.join(OUT, 'cover_recalibration.csv'), index=False)
    fit.to_csv(os.path.join(OUT, 'cover_best_fit.csv'), index=False)
    print(df.to_string(index=False))
    print(fit.to_string(index=False))
