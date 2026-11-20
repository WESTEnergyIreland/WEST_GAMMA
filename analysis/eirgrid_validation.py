"""Compare Gamma's validation runs with EirGrid's published ECP-GSS-1 constraint study (Ireland).

Run after Gamma.py. Reads Data_inputs/eirgrid_ecp_gss1_results_ie.csv and the forecast results of
the validation scenarios, and writes analysis/output/eirgrid_validation.csv and .png.

Like for like: EirGrid models the whole SEM and publishes Ireland results. Gamma also runs the
whole SEM; its Ireland figures are Ireland's constraint (wind + solar) plus the system-wide
curtailment, which applies to Ireland and Northern Ireland alike. EirGrid's 'surplus' (output
above demand, storage and exports) is part of Gamma's curtailment. Gamma also reports its surplus
separately (Surplus_% in summary_system.csv), so the table gives EirGrid's three-way split too:
surplus, operational curtailment and constraint.
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISHED = os.path.join(BASE, 'Data_inputs', 'eirgrid_ecp_gss1_results_ie.csv')
RESULTS = os.path.join(BASE, 'scenario_outputs')
OUT = os.path.join(BASE, 'analysis', 'output')


def gamma_ireland(scenario, year):
    f = os.path.join(RESULTS, scenario, 'forecast_results.csv')
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f)
    r = d.loc[d['Year'] == year]
    if r.empty:
        return None
    r = r.iloc[0]
    s = pd.read_csv(os.path.join(RESULTS, scenario, 'summary_system.csv')).set_index('Year').loc[year]
    curtailment = s['SNSP_Curtailment_%'] + s['MinGen_Curtailment_%']
    surplus = s['Surplus_%'] if 'Surplus_%' in s.index else float('nan')
    return {'gamma_constraint_pct': r['Con_WS_IE_%'], 'gamma_curtailment_pct': curtailment,
            'gamma_total_pct': r['Con_WS_IE_%'] + curtailment,
            'gamma_surplus_pct': surplus, 'gamma_operational_curtailment_pct': curtailment - surplus,
            'gamma_surplus_before_constraint_pct': s.get('Surplus_Before_Constraint_%', float('nan'))}


def main():
    pub = pd.read_csv(PUBLISHED, comment='#')
    pub = pub[pub['gamma_scenario'].notna()]
    rows = []
    for _, p in pub.iterrows():
        g = gamma_ireland(p['gamma_scenario'], int(p['year']))
        if g is None:
            print(f"   no Gamma result for {p['gamma_scenario']} {p['year']}; run Gamma.py first")
            continue
        rows.append({'case': p['case'], 'year': int(p['year']), 'portfolio': p['description'],
                     'eirgrid_constraint_pct': p['constraint_pct'],
                     'eirgrid_curtailment_pct': p['surplus_pct'] + p['curtailment_pct'],
                     'eirgrid_total_pct': p['total_pct'],
                     'eirgrid_surplus_pct': p['surplus_pct'],
                     'eirgrid_operational_curtailment_pct': p['curtailment_pct'],
                     **{k: round(v, 1) for k, v in g.items()}})
    if not rows:
        sys.exit("No matching Gamma results.")
    t = pd.DataFrame(rows)
    t['total_difference_pts'] = (t['gamma_total_pct'] - t['eirgrid_total_pct']).round(1)
    os.makedirs(OUT, exist_ok=True)
    t.to_csv(os.path.join(OUT, 'eirgrid_validation.csv'), index=False)
    print(t.to_string(index=False))

    # Paper Figure 6: EirGrid and Gamma side by side for each case. The 40% headroom-cover case
    # was dropped from the paper on 20 November 2026 (it was fitted before the residual was removed
    # and before equation S2 was corrected).
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels = [f"{r.year}\n{r.portfolio}" for r in t.itertuples()]
    x = range(len(t))
    w = 0.38
    for i, (who, colour) in enumerate((('eirgrid', '#9aa3ad'), ('gamma', '#2a78d6'))):
        name = 'EirGrid' if who == 'eirgrid' else 'Gamma'
        xs = [v + (i - 0.5) * w for v in x]
        ax.bar(xs, t[f'{who}_constraint_pct'], w * 0.92, color=colour, label=f"{name}: constraint")
        ax.bar(xs, t[f'{who}_curtailment_pct'], w * 0.92, bottom=t[f'{who}_constraint_pct'], color=colour,
               alpha=0.45, label=f"{name}: curtailment and surplus")
        for xi, tot in zip(xs, t[f'{who}_total_pct']):
            ax.text(xi, tot + 0.5, f"{tot:.1f}", ha='center', fontsize=7.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel('% of available wind and solar (Ireland)', fontsize=8.5)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(fontsize=7, frameon=False, ncol=2, loc="upper left")
    ax.set_ylim(0, max(t['eirgrid_total_pct'].max(), t['gamma_total_pct'].max()) * 1.35)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'eirgrid_validation.png'), dpi=200)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from paper_figures_common import save
    save(fig, 6)
    print(f"saved {os.path.join(OUT, 'eirgrid_validation.csv')} and .png")


if __name__ == '__main__':
    main()
