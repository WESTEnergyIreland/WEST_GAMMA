"""Robustness study: does the 2050 fossil share depend on the dispatch-down assumptions?

Runs EirGrid_Extended and Historical_Trend to 2050 with one assumption changed at a time and
tabulates the fossil share of primary energy, dispatch down and fossil firm generation.

Usage (from the repository folder, after activating the virtual environment):
    python analysis/robustness_study.py              # runs every case (about 30 minutes)
    python analysis/robustness_study.py kappa_0      # runs the named cases only
    python analysis/robustness_study.py --tables     # rebuild the tables from finished runs

How it works:
1. Copies Gamma.py and Data_inputs to analysis/robustness_run/ (the real inputs are not touched).
2. For each case, edits the two scenario rows in the copied workbook and sets any overrides as
   environment variables (GAMMA_RESIDUAL_SCALE, GAMMA_MUON_MW_PER_UNIT, GAMMA_SIGMA_IE/NI,
   GAMMA_FIRM_CCGT_EFF, GAMMA_FIRM_PEAKER_EFF, GAMMA_HEAT_COP).
3. Runs Gamma.py in that folder for each scenario, without charts.
4. Writes analysis/output/robustness/robustness_results.csv and robustness_table.md.

Cases marked 'dispatch down' test the parts of the model that set constraint and curtailment.
Cases marked 'driver' are for contrast: they change assumptions outside the dispatch-down model.
Edit CASES below to change the study.
"""
import os
import shutil
import subprocess
import sys

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUN_DIR = os.path.join(HERE, 'robustness_run')
OUT = os.path.join(HERE, 'output', 'robustness')
SCENARIOS = ('EirGrid_Extended', 'Historical_Trend')
TARGET_YEAR = 2050
REPORT_YEARS = (2035, 2050)
ZONES = ('NW', 'W', 'MID', 'NE', 'SW', 'SE', 'NI')

NO_LIMITS = '; '.join(f'{z}:2027:1000000' for z in ZONES)
FROZEN = {'headroom_curve': 'reinforcement_pct', 'ie_reinforcement_pct': 0, 'ni_reinforcement_pct': 0,
          'reinforcement_steps': None}

# case name: (group, label, workbook changes for both scenario rows, environment overrides)
CASES = {
    'base': ('base', 'Base (as in the paper)', {}, {}),
    'kappa_0': ('dispatch down', 'Residual curtailment set to zero (wind and solar)', {},
                {'GAMMA_RESIDUAL_SCALE': '0'}),
    'kappa_x2': ('dispatch down', 'Residual curtailment doubled', {}, {'GAMMA_RESIDUAL_SCALE': '2'}),
    'pmin_400': ('dispatch down', '400 MW per minimum unit (residual recalibrated)', {},
                 {'GAMMA_MUON_MW_PER_UNIT': '400'}),
    'no_limits_from_2027': ('dispatch down', 'No zonal network limits from 2027',
                            {'reinforcement_steps': NO_LIMITS}, {}),
    'published_path_kept': ('dispatch down', 'Network limits kept after 2035',
                            {'reinforcement_steps': 'NI:2032:950'}, {}),
    'network_frozen': ('dispatch down', 'Network frozen at 2026 headroom', FROZEN, {}),
    'frozen_sigma_low': ('dispatch down', 'Network frozen, sigma low (IE 0.8, NI 1.2)', FROZEN,
                         {'GAMMA_SIGMA_IE': '0.8', 'GAMMA_SIGMA_NI': '1.2'}),
    'frozen_sigma_high': ('dispatch down', 'Network frozen, sigma high (IE 2.0, NI 2.5)', FROZEN,
                          {'GAMMA_SIGMA_IE': '2.0', 'GAMMA_SIGMA_NI': '2.5'}),
    'eff_high': ('driver', 'Firm efficiencies 60% and 42%', {},
                 {'GAMMA_FIRM_CCGT_EFF': '0.60', 'GAMMA_FIRM_PEAKER_EFF': '0.42'}),
    'eff_low': ('driver', 'Firm efficiencies 50% and 34%', {},
                {'GAMMA_FIRM_CCGT_EFF': '0.50', 'GAMMA_FIRM_PEAKER_EFF': '0.34'}),
    'heat_cop_2p5': ('driver', 'Heat COP 2.5', {}, {'GAMMA_HEAT_COP': '2.5'}),
}
COLUMNS = {
    'Overall_Fossil_Fuel_Pct': 'fossil_share_pct',
    'Total_Loss_%': 'dispatch_down_pct',
    'Constraint_%': 'constraint_pct',
    'Curtailment_%': 'curtailment_pct',
    'Fossil_Firm_Generation_TWh': 'fossil_firm_twh',
    'Firm_Capacity_Required_GW': 'firm_capacity_gw',
}


def prepare_run_dir():
    if os.path.exists(RUN_DIR):
        shutil.rmtree(RUN_DIR)
    os.makedirs(RUN_DIR)
    shutil.copy(os.path.join(REPO, 'Gamma.py'), RUN_DIR)
    shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(RUN_DIR, 'Data_inputs'))


def write_workbook(changes):
    """Copy the real workbook into the run folder and edit the two scenario rows."""
    path = os.path.join(RUN_DIR, 'Data_inputs', 'scenariosXLSX.xlsx')
    shutil.copy(os.path.join(REPO, 'Data_inputs', 'scenariosXLSX.xlsx'), path)
    wb = openpyxl.load_workbook(path)
    ws = wb['Scenarios']
    col = {c.value: i + 1 for i, c in enumerate(ws[1])}
    found = set()
    for r in range(3, ws.max_row + 1):
        name = ws.cell(r, col['scenario']).value
        if name in SCENARIOS:
            found.add(name)
            ws.cell(r, col['target_year']).value = TARGET_YEAR
            for field, value in changes.items():
                ws.cell(r, col[field]).value = value
    missing = set(SCENARIOS) - found
    if missing:
        raise ValueError(f"Scenario rows not found in the workbook: {sorted(missing)}")
    wb.save(path)


def case_dir(case):
    return os.path.join(RUN_DIR, 'results', case)


def run_case(case):
    _, label, changes, overrides = CASES[case]
    write_workbook(changes)
    # Overrides from an earlier shell session must not leak into another case.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GAMMA_')}
    env.update(GAMMA_CHARTS='0', **overrides)
    os.makedirs(case_dir(case), exist_ok=True)
    for sc in SCENARIOS:
        print(f">> {case}: {sc} ({label})", flush=True)
        log = subprocess.run([sys.executable, 'Gamma.py', sc], cwd=RUN_DIR, env=env,
                             capture_output=True, text=True)
        if log.returncode != 0:
            raise RuntimeError(f"Gamma failed for {case}, {sc}:\n{log.stdout[-800:]}\n{log.stderr[-800:]}")
        shutil.copy(os.path.join(RUN_DIR, 'scenario_outputs', sc, 'summary_total.csv'),
                    os.path.join(case_dir(case), f'{sc}.csv'))


def collect():
    rows = []
    for case, (group, label, _, _) in CASES.items():
        for sc in SCENARIOS:
            path = os.path.join(case_dir(case), f'{sc}.csv')
            if not os.path.exists(path):
                continue
            t = pd.read_csv(path).set_index('Year')
            for y in REPORT_YEARS:
                rows.append({'case': case, 'group': group, 'label': label, 'scenario': sc, 'year': y,
                             **{new: round(float(t.loc[y, old]), 2) for old, new in COLUMNS.items()}})
    if not rows:
        raise SystemExit("No finished runs found in analysis/robustness_run/results/.")
    res = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    res.to_csv(os.path.join(OUT, 'robustness_results.csv'), index=False)

    r50 = res[res['year'] == TARGET_YEAR]
    lines = [f"# Robustness of the {TARGET_YEAR} results",
             "",
             "Written by `analysis/robustness_study.py`. One assumption is changed at a time; every other "
             "input is as in the scenario workbook. All thirteen weather years.",
             "",
             f"| Case | Group | Fossil share {TARGET_YEAR}, EirGrid_Extended (%) | Fossil share {TARGET_YEAR}, "
             f"Historical_Trend (%) | Dispatch down {TARGET_YEAR}, EirGrid_Extended (%) | Fossil firm generation "
             f"{TARGET_YEAR}, EirGrid_Extended (TWh) |",
             "|---|---|---|---|---|---|"]
    for case, (group, label, _, _) in CASES.items():
        e = r50[(r50['case'] == case) & (r50['scenario'] == 'EirGrid_Extended')]
        h = r50[(r50['case'] == case) & (r50['scenario'] == 'Historical_Trend')]
        if e.empty or h.empty:
            continue
        e, h = e.iloc[0], h.iloc[0]
        lines.append(f"| {label} | {group} | {e['fossil_share_pct']:.1f} | {h['fossil_share_pct']:.1f} | "
                     f"{e['dispatch_down_pct']:.1f} | {e['fossil_firm_twh']:.1f} |")
    dd = r50[r50['group'].isin(('base', 'dispatch down'))]
    lines.append("")
    for sc in SCENARIOS:
        g = dd[dd['scenario'] == sc]
        base = g[g['case'] == 'base']
        if base.empty:
            continue
        b = float(base['fossil_share_pct'].iloc[0])
        lines.append(f"{sc}: fossil share {TARGET_YEAR} is {b:.1f}% in the base case and "
                     f"{g['fossil_share_pct'].min():.1f}% to {g['fossil_share_pct'].max():.1f}% across the "
                     f"dispatch-down cases; fossil firm generation {g['fossil_firm_twh'].min():.1f} to "
                     f"{g['fossil_firm_twh'].max():.1f} TWh.")
        lines.append("")
    with open(os.path.join(OUT, 'robustness_table.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines).rstrip('\n') + '\n')
    print('\n'.join(lines))
    print(f">> Wrote {os.path.join(OUT, 'robustness_results.csv')} and robustness_table.md")


def main():
    args = sys.argv[1:]
    if '--tables' not in args:
        cases = args or list(CASES)
        unknown = [c for c in cases if c not in CASES]
        if unknown:
            raise SystemExit(f"Unknown case(s) {unknown}. Choose from: {', '.join(CASES)}")
        if not args or not os.path.exists(RUN_DIR):
            prepare_run_dir()
        else:
            # Named cases: refresh the code and inputs, keep the other cases' finished results.
            shutil.copy(os.path.join(REPO, 'Gamma.py'), RUN_DIR)
            shutil.rmtree(os.path.join(RUN_DIR, 'Data_inputs'))
            shutil.copytree(os.path.join(REPO, 'Data_inputs'), os.path.join(RUN_DIR, 'Data_inputs'))
        for case in cases:
            run_case(case)
    collect()


if __name__ == '__main__':
    main()
