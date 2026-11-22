"""Table 6 and Supplementary S5/S9 one-at-a-time tests, written to analysis/output/sensitivity_tests.csv.

Usage (from the repository folder, after `python Gamma.py` so the base results exist):
    python analysis/table6_tests.py            # runs every test, two at a time (CSV only)
    python analysis/table6_tests.py --tables   # rebuild the CSV from finished runs

Each test copies Gamma.py and Data_inputs to analysis/table6_run/<test>/, changes one thing
(a constant in the copy of Gamma.py, an environment switch or a workbook column), runs the named
scenarios to the last year needed and compares with the base run in scenario_outputs/.
Before 22 November 2026 these tests were run by hand (CHANGELOG, 20 November 2026). The
validation sigma and weather-year rows are not rerun here and are kept from the existing CSV.
"""
import os
import re
import shutil
import subprocess
import sys

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUN = os.path.join(HERE, 'table6_run')
CSV = os.path.join(HERE, 'output', 'sensitivity_tests.csv')
EE, HT = 'EirGrid_Extended', 'Historical_Trend'

# name: (test, setting, {scenario: last year}, constants, env, workbook edits, rows)
# rows: (scenario, year, metric, note)
FOSSIL, FIRM = 'fossil share of TPE %', 'firm capacity GW'
TESTS = {
    'cop25': ('heat_pump_cop', 'HEAT_COP 2.5 (base 3.5)', {EE: 2050}, {'HEAT_COP': 2.5}, {}, {},
              [(EE, 2050, FOSSIL, 'Table 6')]),
    'cop39': ('heat_pump_cop', 'HEAT_COP 3.9', {EE: 2100, HT: 2100}, {'HEAT_COP': 3.9}, {}, {},
              [(EE, 2050, FOSSIL, 'Supplementary S5'), (EE, 2100, FOSSIL, 'Supplementary S5'),
               (HT, 2050, FOSSIL, 'Supplementary S5'), (HT, 2100, FOSSIL, 'Supplementary S5')]),
    'eff_hi': ('firm_efficiency', 'CCGT 60% OCGT 42% (base 55/38)', {EE: 2050},
               {'FIRM_CCGT_EFFICIENCY': 0.60, 'FIRM_PEAKER_EFFICIENCY': 0.42}, {}, {},
               [(EE, 2050, FOSSIL, 'Table 6')]),
    'eff_lo': ('firm_efficiency', 'CCGT 50% OCGT 34%', {EE: 2050},
               {'FIRM_CCGT_EFFICIENCY': 0.50, 'FIRM_PEAKER_EFFICIENCY': 0.34}, {}, {},
               [(EE, 2050, FOSSIL, 'Table 6')]),
    'eff_35': ('firm_efficiency', 'all firm units 35%', {EE: 2100, HT: 2100},
               {'FIRM_CCGT_EFFICIENCY': 0.35, 'FIRM_PEAKER_EFFICIENCY': 0.35}, {}, {},
               [(EE, 2050, FOSSIL, 'Supplementary S5'), (EE, 2100, FOSSIL, 'Supplementary S5'),
                (HT, 2050, FOSSIL, 'Supplementary S5'), (HT, 2100, FOSSIL, 'Supplementary S5')]),
    'offshore45': ('offshore_cf', 'GAMMA_OFFSHORE_CF 0.45 (base 0.40)', {EE: 2050}, {},
                   {'GAMMA_OFFSHORE_CF': '0.45'}, {}, [(EE, 2050, FOSSIL, 'Table 6')]),
    'shape': ('demand_shape', "GAMMA_FLAT_GROWTH=0 (growth on today's shape)", {EE: 2050, HT: 2050}, {},
              {'GAMMA_FLAT_GROWTH': '0'}, {},
              [(EE, 2050, FOSSIL, 'Table 6; S9.2'), (HT, 2050, FOSSIL, 'S9.2'),
               (EE, 2050, FIRM, 'Table 6; S9.2'), (HT, 2050, FIRM, 'S9.2')]),
    'network': ('published_network_path', 'zonal limits kept after 2035', {EE: 2050, HT: 2050}, {}, {},
                {EE: {'reinforcement_steps': 'NI:2032:950'},
                 HT: {'reinforcement_steps': 'NI:2032:950'}},
                [(EE, 2050, FOSSIL, 'Table 6; Section 7.3'), (HT, 2050, FOSSIL, 'Section 7.3')]),
    'slow_ops': ('slow_operating_rules', 'path historical_trend_slow_ops', {HT: 2035}, {}, {},
                 {HT: {'scenario_path': 'historical_trend_slow_ops'}}, 'max_diff'),
}


def summary(path):
    return pd.read_csv(os.path.join(path, 'scenario_outputs', 'scenario_summary.csv'))


def value(df, scenario, year, metric):
    r = df[(df['Scenario'] == scenario) & (df['Year'] == year)].iloc[0]
    return float(r['Primary_Fossil_Share_Pct'] if metric == FOSSIL else r['Firm_Capacity_Required_GW'])


def build(name):
    test, setting, scen, consts, env, edits, rows = TESTS[name]
    d = os.path.join(RUN, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    src = open(os.path.join(REPO, 'Gamma.py')).read()
    for k, v in consts.items():
        src, n = re.subn(rf'^{k} = .*$', f'{k} = {v}', src, flags=re.M)
        if n != 1:
            sys.exit(f'constant {k} not found once in Gamma.py')
    open(os.path.join(d, 'Gamma.py'), 'w').write(src)
    shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(d, 'Data_inputs'))
    p = os.path.join(d, 'Data_inputs', 'scenariosXLSX.xlsx')
    wb = openpyxl.load_workbook(p)
    ws = wb['Scenarios']
    hdr = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(hdr)}
    for r in range(3, ws.max_row + 1):
        sc = ws.cell(r, 1).value
        ws.cell(r, col['run']).value = 'yes' if sc in scen else 'no'
        if sc in scen:
            ws.cell(r, col['target_year']).value = scen[sc]
            for k, v in edits.get(sc, {}).items():
                ws.cell(r, col[k]).value = v
    wb.save(p)
    return d, env


def run_all():
    names = list(TESTS)
    procs = []
    for name in names:
        d, env = build(name)
        e = dict(os.environ, GAMMA_CHARTS='0', **env)
        log = open(os.path.join(d, 'run.out'), 'w')
        procs.append((name, subprocess.Popen([sys.executable, 'Gamma.py'], cwd=d, env=e,
                                             stdout=log, stderr=subprocess.STDOUT)))
        while sum(p.poll() is None for _, p in procs) >= 2:
            procs[[p.poll() is None for _, p in procs].index(True)][1].wait()
    for name, p in procs:
        if p.wait() != 0:
            print(f'{name} failed; see {os.path.join(RUN, name, "run.out")}')


def tables():
    base = summary(REPO)
    out = []
    for name, (test, setting, scen, consts, env, edits, rows) in TESTS.items():
        d = os.path.join(RUN, name)
        if not os.path.exists(os.path.join(d, 'scenario_outputs', 'scenario_summary.csv')):
            print(f'no results for {name}')
            continue
        t = summary(d)
        if rows == 'max_diff':
            sc = list(scen)[0]
            yrs = lambda df: df[(df['Scenario'] == sc) & (df['Year'].between(2026, scen[sc]))].set_index('Year')
            b, x = yrs(base), yrs(t)
            sysf = lambda root: pd.read_csv(os.path.join(root, 'scenario_outputs', sc, 'summary_system.csv'))
            b['dd'] = sysf(REPO).set_index('Year')['Total_Dispatch_Down_%']
            x['dd'] = sysf(d).set_index('Year')['Total_Dispatch_Down_%']
            # Dispatch down: wind and solar, % of available wind and solar energy.
            for metric, c, note in (('dispatch down % (max abs difference)', 'dd', 'Table 6; S5'),
                                    ('fossil share of TPE % (max abs difference)', 'Primary_Fossil_Share_Pct', 'S5')):
                out.append({'test': test, 'setting': setting, 'scenario': sc, 'year': scen[sc],
                            'metric': metric, 'base': '', 'test_value': '',
                            'difference': round(float((x[c] - b[c]).abs().max()), 2), 'run_dir_note': note})
            continue
        for sc, yr, metric, note in rows:
            b, v = value(base, sc, yr, metric), value(t, sc, yr, metric)
            out.append({'test': test, 'setting': setting, 'scenario': sc, 'year': yr, 'metric': metric,
                        'base': f'{b:.2f}', 'test_value': f'{v:.2f}', 'difference': f'{v - b:.2f}',
                        'run_dir_note': note})
    kept = pd.read_csv(CSV, dtype=str)
    kept = kept[kept['test'].isin(['validation_sigma', 'validation_weather'])]
    res = pd.concat([pd.DataFrame(out).astype(str), kept], ignore_index=True)
    res.to_csv(CSV, index=False)
    print(res.to_string(index=False))


if __name__ == '__main__':
    if '--tables' not in sys.argv:
        run_all()
    tables()
