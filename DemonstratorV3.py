"""
================================================================================
IRELAND (SEM) - ADVANCED WIND CAPACITY w/ LOSS MODELING DEMO
(CONSTRAINT + CURTAILMENT MODEL, WITH USER INPUTS FOR SNSP AND BUILD RATES IN SCENARIOS.CSV)
================================================================================

PURPOSE & METHODOLOGY:
A demonstrator for future energy modelers utilising TIM / TIMES frameworks. 
Demonstrates why static or linear loss assumptions fail when modeling large-scale 
offshore or onshore wind build-outs: 
Model incorporating decarbonisation/electrification demand scaling (+1.87TWh/yr, required rate for a 2050 target)

CAPACITY TIMING & COD RAMP ENGINE:
- 2026 Baseline anchored at exact current fleet capacity for the SEM (6.51 GW).
- New build capacity ramps linearly during construction/commissioning so that
  the first full annual build increment is completely online by end-2027, and maintains a user-input build rate. 
- Full 15-minute weather granularity and seasonal profile preserved across all forecast years.

DISPATCH ENGINE:
- Usable wind is summed directly from the 15-minute dispatch (constraint, then SNSP), and
  capacity factor is reported from it. Monthly charts are summed from the same intervals.

CONSTRAINT MODEL (FITTED NETWORK LIMIT):
- Constraint is modelled interval by interval as available wind above an effective
  network limit L. The limit varies from hour to hour (lognormal spread sigma), which
  stands in for local constraints, outages and system conditions:
      expected constraint(x) = E[max(0, x - L*eta)],  eta ~ lognormal(median 1, sigma)
- L and sigma are fitted so modelled constraint energy matches the records exactly, with
  sigma chosen to fit the hourly pattern best (no separate calibration factor).
- Ireland (IE) and Northern Ireland (NI) are modelled separately, each with its own L, sigma
  fitted to its own hourly records ('system_dd_hourly_ie.csv' and
  'system_dd_hourly_ni.csv', built from the EirGrid/SONI DD-HH workbooks by
  build_all_island_dd.py). The all-island 15-minute availability is split between them by
  today's availability share for the existing fleet and a user-input share for new build.
  Each region's constraint is reported separately and the two are added for the all-island
  result. NI is fitted on 2024-2025 by default, after its constraint rate jumped from 2023.
- Each region's limit grows by its own user-input reinforcement rate (0% = no reinforcement,
  the upper bound for constraints) plus optional one-off steps (REINFORCEMENT_STEPS_MW).
- Every forecast year, with the regional split, is saved to forecast_results.csv.
- Constraint is applied first in every interval; SNSP curtailment is then applied to
  the wind that is left, in both the annual loop and the daily charts.

HINDCAST VALIDATION:
- Rolling one-year-ahead hindcast: each year is predicted from a fit on the year(s) before
  it, using that year's actual hourly availability. The typical all-island error is reported
  and applied as a +/- band on the forecast constraint (GridCon_Low_% / GridCon_High_%).

SCENARIOS:
- If scenarios.csv exists, each row is run without prompts (build rate, SNSP limit, IE/NI
  reinforcement, new-build split) and results are written per scenario, plus a summary.
  The error for each test year is reported.

GRAPHICAL OUTPUT ENGINE (7 CHARTS):
1. Historical & Near-Term Forecast Chart (Jan 2019 - Dec 2030) - Full Weather Granularity
2. Long-Term Forecast Stacked Overview Chart (Jan 2045 - Dec 2050) - Full Weather (6 year loop of weather)
3. Absolute Peak Wind Storm Day Dispatch Profile (2048) - Max Wind Generation Showcaser
4. Typical Low-Average Wind Day Dispatch Profile (2048) 
5. Dunkelflaute Extreme Low Wind Day Dispatch Profile (2048) 
6. Average Wind Day Dispatch Profile (2033)
7. Grand Master Overview (Jan 2019 - Dec 2050) - Full 32-Year Monthly GWh Timeline with Saturation Plateau
================================================================================
"""

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.special import ndtr
from scipy.optimize import brentq, minimize_scalar

# =============================================================================
# CONSTRAINT MODEL SETTINGS
# =============================================================================
REGIONS = ['IE', 'NI']
REGION_NAMES = {'IE': 'Republic of Ireland', 'NI': 'Northern Ireland'}
DD_FILES = {'IE': "system_dd_hourly_ie.csv", 'NI': "system_dd_hourly_ni.csv"}
CONSTRAINT_COLUMN = "constraint_mwh"      # or "trans_constr_mwh" for transmission constraints only
CONSTRAINT_FIT_YEARS = {'IE': [2024, 2025, 2026], 'NI': [2024, 2025, 2026]}
HINDCAST_LOOKBACK_YEARS = 1
MIN_HOURS_FOR_FIT = 24 * 60
REINFORCEMENT_STEPS_MW = {'IE': {}, 'NI': {}}
HISTORICAL_SNSP_PCT = 75.0                
FORECAST_RESULTS_CSV = "forecast_results.csv"
SCENARIO_FILE = "scenarios.csv"
SCENARIO_OUTPUT_DIR = "scenario_outputs"
SCENARIO_SUMMARY_CSV = "scenario_summary.csv"
SCENARIO_CHARTS = True                    
DEFAULT_BUILD_RATE_GW = 1.87 / (8760 * 0.40 / 1000.0)   # ~0.534 GW/yr
DEFAULT_SNSP_PCT = 75.0


def ask_float(prompt, default):
    """Prompt for a number; Enter or invalid input gives the default."""
    raw = input(f"{prompt} [Press Enter for default {default:g}]: ").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"Invalid input. Falling back to default {default:g}.")
        return default


def load_dd_hourly(path, constraint_col=CONSTRAINT_COLUMN):
    """Hourly available wind and constraint, converted to average MW."""
    df = pd.read_csv(path, parse_dates=['datetime'])
    df = df[df['hh_count'] > 0].copy()
    to_mw = 2.0 / df['hh_count']
    df['avail_mw'] = df['av_mwh'] * to_mw
    df['cons_mw'] = df[constraint_col] * to_mw
    df['year'] = df['datetime'].dt.year
    return df[['datetime', 'year', 'avail_mw', 'cons_mw']]


def expected_constraint_mw(avail_mw, limit_mw, sigma, calib=1.0):
    """Expected constrained MW in an interval with available wind avail_mw."""
    x = np.maximum(np.asarray(avail_mw, dtype=float), 1e-6)
    d1 = (np.log(limit_mw / x) + 0.5 * sigma ** 2) / sigma
    d2 = d1 - sigma
    raw = x * ndtr(-d2) - limit_mw * np.exp(0.5 * sigma ** 2) * ndtr(-d1)
    return np.clip(calib * raw, 0.0, x)


def fit_constraint_model(dd, years):
    """Fit limit L (MW) and spread sigma on the given years, with constrained energy matched exactly."""
    sub = dd[dd['year'].isin(years)]
    x, c = sub['avail_mw'].values, sub['cons_mw'].values
    target = c.sum()
    if target <= 0:
        return {'limit_mw': float(x.max() * 100), 'sigma': 0.8, 'calib': 1.0, 'years': list(years)}

    def limit_matching_energy(sigma):
        gap = lambda ln_l: expected_constraint_mw(x, np.exp(ln_l), sigma).sum() - target
        return float(np.exp(brentq(gap, np.log(1.0), np.log(max(x.max(), 1.0) * 100))))

    def hourly_err(sigma):
        return np.mean((expected_constraint_mw(x, limit_matching_energy(sigma), sigma) - c) ** 2)

    res = minimize_scalar(hourly_err, bounds=(0.2, 2.5), method='bounded', options={'xatol': 1e-3})
    sigma = float(res.x)
    return {'limit_mw': limit_matching_energy(sigma), 'sigma': sigma, 'calib': 1.0, 'years': list(years)}


def limit_for_year(params, year, reinforcement_rate, steps):
    """Effective network limit in a given year: compound reinforcement plus one-off steps."""
    ref_year = max(params['years'])
    growth = (1.0 + reinforcement_rate) ** max(0, year - ref_year)
    step_mw = sum(mw for yr, mw in steps.items() if yr <= year)
    return params['limit_mw'] * growth + step_mw


def run_demonstrator():
    print("=" * 90)
    print("      IRELAND (SEM) - WIND CAPACITY & LOSS MODELING DEMONSTRATOR      ")
    print("      (Featuring Historical Hindcast Validation & 6-Chart Engine) ")
    print("=" * 90)

    # 1. Load Excel Historical Tables & CSV Data
    excel_file = "Input - capacity, constraints, curtailment.xlsx"
    csv_file = "sem_demand_wind_from_2019.csv"
    
    base_2026_curt = 4.9
    base_2026_cons = 10.0
    base_2026_cf = 23.0
    base_2026_wind_pct = 33.733919
    
    if os.path.exists(excel_file) and os.path.exists(csv_file):
        df_cap = pd.read_excel(excel_file, sheet_name='CapacityByYear')
        df_cons = pd.read_excel(excel_file, sheet_name='ConstraintsbyYear')
        df_curt = pd.read_excel(excel_file, sheet_name='RawCurtailmentbyYear')
        df_cf = pd.read_excel(excel_file, sheet_name='CapacityFactorbyYear')
        
        df_cap.columns = ['year', 'ROI_MW', 'NI_MW', 'Total_MW']
        df_cons.columns = ['year', 'Constraint_Pct', 'col2', 'notes']
        df_curt.columns = ['year', 'Curtailment_Pct', 'col2', 'notes']
        df_cf.columns = ['year', 'Capacity_Factor_Pct', 'col2', 'notes']
        
        hist_df = df_cap[['year', 'Total_MW']].copy()
        hist_df['Capacity_GW'] = hist_df['Total_MW'] / 1000.0
        hist_df['Constraint_Pct'] = df_cons['Constraint_Pct'].values
        hist_df['Curtailment_Pct'] = df_curt['Curtailment_Pct'].values
        hist_df['Capacity_Factor_Pct'] = df_cf['Capacity_Factor_Pct'].values
        
        match_2026 = hist_df[hist_df['year'] == 2026]
        if not match_2026.empty:
            base_2026_curt = float(match_2026['Curtailment_Pct'].values[0])
            base_2026_cons = float(match_2026['Constraint_Pct'].values[0])
            base_2026_cf = float(match_2026['Capacity_Factor_Pct'].values[0])
        
        df_15m = pd.read_csv(csv_file)
        df_15m['parsed_date'] = pd.to_datetime(df_15m['date'], format='%d/%m/%Y %H:%M', errors='coerce')
        df_15m['year'] = df_15m['parsed_date'].dt.year
        df_15m['month'] = df_15m['parsed_date'].dt.month
        df_15m['day'] = df_15m['parsed_date'].dt.day
        
        merged = pd.merge(df_15m, df_cap[['year', 'Total_MW']], on='year', how='inner')
        merged['installed_gw'] = merged['Total_MW'] / 1000.0
        merged['spec_avail_mw_per_gw'] = merged['sem_wind_availability'] / merged['installed_gw']
        
        def get_annualized_twr(sub_df):
            yr = sub_df['year'].iloc[0] if 'year' in sub_df.columns else sub_df.name
            days_present = 108 if yr == 2026 else 144
            annual_multiplier = 365.25 / days_present
            d_twh = (sub_df['sem_demand'].sum() / 4000000.0) * annual_multiplier
            g_twh = (sub_df['sem_wind_generation'].sum() / 4000000.0) * annual_multiplier
            return pd.Series({'Demand_TWh': d_twh, 'Gen_TWh': g_twh})

        hist_demand_wind = df_15m.groupby('year', group_keys=True).apply(get_annualized_twr).reset_index()
        master_hist = pd.merge(hist_df, hist_demand_wind, on='year', how='left')
        master_hist['Wind_Pct_Of_Demand'] = (master_hist['Gen_TWh'] / master_hist['Demand_TWh']) * 100.0
        
        m_2026 = master_hist[master_hist['year'] == 2026]
        if not m_2026.empty and not pd.isna(m_2026['Wind_Pct_Of_Demand'].values[0]):
            base_2026_wind_pct = float(m_2026['Wind_Pct_Of_Demand'].values[0])
        
        print("\n====================================================================")
        print(" 1. HISTORICAL ALL-ISLAND (SEM) FULL-YEAR ANNUALIZED (2019 - 2026)")
        print("====================================================================")
        print(master_hist[['year', 'Capacity_GW', 'Demand_TWh', 'Gen_TWh', 'Wind_Pct_Of_Demand', 'Constraint_Pct', 'Curtailment_Pct']].to_string(index=False))

    # -------------------------------------------------------------------------
    # 2. HISTORICAL HINDCAST VALIDATION & CALIBRATION ENGINE (2019 - 2026)
    # -------------------------------------------------------------------------
    print("\n====================================================================")
    print(" 2. CONSTRAINT MODEL: FIT & HINDCAST AGAINST HOURLY RECORDS")
    print("====================================================================")
    dd = {}
    for reg in REGIONS:
        if not os.path.exists(DD_FILES[reg]):
            raise FileNotFoundError(f"'{DD_FILES[reg]}' is needed to fit the {reg} constraint model "
                                    f"(run build_all_island_dd.py first).")
        dd[reg] = load_dd_hourly(DD_FILES[reg])
    full_years, fit_years_avail, months_in = {}, {}, {}
    for reg in REGIONS:
        counts = dd[reg].groupby('year').size()
        full_years[reg] = [int(y) for y, n in counts.items() if n >= 8700]
        fit_years_avail[reg] = [int(y) for y, n in counts.items() if n >= MIN_HOURS_FOR_FIT]
        for y, g in dd[reg].groupby('year'):
            months_in[(reg, int(y))] = g['datetime'].dt.month.nunique()

    def year_label(reg, y):
        m = months_in.get((reg, y), 12)
        return str(y) if m == 12 else f"{y} ({m} mo)"

    # Per-year fits, for transparency: how each region's effective limit has moved.
    for reg in REGIONS:
        per_year = []
        for y in fit_years_avail[reg]:
            p = fit_constraint_model(dd[reg], [y])
            g = dd[reg][dd[reg]['year'] == y]
            per_year.append({
                'Year': year_label(reg, y),
                'Limit_MW': round(p['limit_mw']),
                'Sigma': round(p['sigma'], 2),
                'Avail_TWh': round(g['avail_mw'].sum() / 1e6, 2),
                'Cons_GWh': round(g['cons_mw'].sum() / 1e3),
                'Cons_%': round(100 * g['cons_mw'].sum() / g['avail_mw'].sum(), 2),
            })
        print(f"{REGION_NAMES[reg]} ({reg}), fitted separately for each year:")
        print(pd.DataFrame(per_year).to_string(index=False))
        print()

    # Rolling one-year-ahead hindcast
    hind = {}
    for reg in REGIONS:
        yrs = sorted(fit_years_avail[reg])
        for i, y in enumerate(yrs):
            train = [t for t in yrs[:i] if t >= y - HINDCAST_LOOKBACK_YEARS]
            if len(train) < HINDCAST_LOOKBACK_YEARS:
                continue
            p_train = fit_constraint_model(dd[reg], train)
            g = dd[reg][dd[reg]['year'] == y]
            pred = expected_constraint_mw(g['avail_mw'].values, p_train['limit_mw'],
                                          p_train['sigma'], p_train['calib']).sum()
            hind[(reg, y)] = (g['cons_mw'].sum(), pred, g['avail_mw'].sum(), train)
    hindcast_band = 0.0
    if hind:
        hind_rows = []
        for y in sorted({y for _, y in hind}):
            for reg in REGIONS + ['All-island']:
                if reg == 'All-island':
                    parts = [hind[(r, y)] for r in REGIONS if (r, y) in hind]
                    if len(parts) < len(REGIONS):
                        continue
                    act, pred, av = (sum(v[i] for v in parts) for i in range(3))
                    train_lbl = ''
                elif (reg, y) in hind:
                    act, pred, av, train = hind[(reg, y)]
                    train_lbl = ','.join(str(t) for t in train)
                else:
                    continue
                hind_rows.append({
                    'Year': year_label('IE', y) if reg == 'All-island' else year_label(reg, y),
                    'Region': reg,
                    'Fit_on': train_lbl,
                    'Actual_GWh': round(act / 1e3),
                    'Predicted_GWh': round(pred / 1e3),
                    'Error_%': round(100 * (pred / act - 1), 1) if act > 0 else float('nan'),
                    'Actual_Cons_%': round(100 * act / av, 2),
                    'Predicted_Cons_%': round(100 * pred / av, 2),
                })
        hind_df = pd.DataFrame(hind_rows)
        print("Rolling one-year-ahead hindcast:")
        print(hind_df.to_string(index=False))
        print("\nHindcast error by region (mean absolute error; bias = average signed error):")
        for reg in REGIONS + ['All-island']:
            e = hind_df.loc[hind_df['Region'] == reg, 'Error_%'].dropna()
            if len(e):
                print(f"   {reg:<10} typical error ±{e.abs().mean():.1f}%, bias {e.mean():+.1f}% "
                      f"over {len(e)} years")
        e_ai = hind_df.loc[hind_df['Region'] == 'All-island', 'Error_%'].dropna()
        if len(e_ai) == 0:
            e_ai = hind_df['Error_%'].dropna()
        hindcast_band = float(e_ai.abs().mean()) / 100.0 if len(e_ai) else 0.0
        print(f">> Forecast constraint is reported with a ±{100 * hindcast_band:.0f}% band "
              "(GridCon_Low_% / GridCon_High_%), the typical one-year-ahead error.")

    cons_params = {}
    print()
    for reg in REGIONS:
        years = CONSTRAINT_FIT_YEARS.get(reg) or fit_years_avail[reg]
        years = [y for y in years if y in fit_years_avail[reg]] or fit_years_avail[reg]
        cons_params[reg] = fit_constraint_model(dd[reg], years)
        p = cons_params[reg]
        print(f"Forecast model {reg} fitted on {years}: L = {p['limit_mw']:.0f} MW, "
              f"sigma = {p['sigma']:.2f}")

    common_years = sorted(set(full_years['IE']) & set(full_years['NI']))
    share_year = common_years[-1]
    av_ie = dd['IE'].loc[dd['IE']['year'] == share_year, 'avail_mw'].sum()
    av_ni = dd['NI'].loc[dd['NI']['year'] == share_year, 'avail_mw'].sum()
    base_ie_share = float(av_ie / (av_ie + av_ni))
    print(f">> {share_year} availability split: IE {100 * base_ie_share:.1f}% / NI {100 * (1 - base_ie_share):.1f}%")

    ai_hourly = (dd['IE'].set_index('datetime')['avail_mw']
                 .add(dd['NI'].set_index('datetime')['avail_mw'], fill_value=0.0)
                 .rename('avail_mw').to_frame())
    avail_hourly_15m = (merged.set_index('parsed_date')['sem_wind_availability']
                        .resample('h').mean().dropna().rename('avail_15m'))
    overlap = ai_hourly.join(avail_hourly_15m, how='inner')
    if len(overlap) > 500 and overlap['avail_15m'].sum() > 0:
        avail_basis_ratio = float(overlap['avail_mw'].sum() / overlap['avail_15m'].sum())
        print(f">> Availability basis check over {len(overlap):,} shared hours: "
              f"IE + NI hourly / 15-min file = {avail_basis_ratio:.3f}")
        if not 0.9 <= avail_basis_ratio <= 1.1:
            print("   ! The two sources differ by more than 10%. They may cover different areas; "
                  "check DD_FILES and the 15-minute file.")
    else:
        avail_basis_ratio = 1.0
        print(">> Warning: too few shared hours to compare the two availability series; assuming the same basis.")

    def regional_constraint_mw(avail_mw, limits, ie_share):
        """Expected constrained MW in each region for all-island availability (15-min basis)."""
        scaled = np.asarray(avail_mw, dtype=float) * avail_basis_ratio
        shares = {'IE': ie_share, 'NI': 1.0 - ie_share}
        out = {}
        for reg in REGIONS:
            p = cons_params[reg]
            out[reg] = expected_constraint_mw(scaled * shares[reg], limits[reg],
                                              p['sigma'], p['calib']) / avail_basis_ratio
        return out

    def interactive_scenario():
        """Ask for the scenario inputs (used when there is no scenarios.csv)."""
        print("\n(No scenarios.csv found: running one scenario from prompts.)")
        return {
            'scenario': 'interactive',
            'build_rate_gw': ask_float("Enter annual wind build-out rate in GW/year", round(DEFAULT_BUILD_RATE_GW, 3)),
            'snsp_limit_pct': ask_float("Enter System Non-Synchronous Penetration (SNSP) Limit %", DEFAULT_SNSP_PCT),
            'ie_reinforcement_pct': ask_float("Enter IE network reinforcement rate (% change in its effective "
                                              "limit per year; 0 = none, negative = continued tightening)", 0.0),
            'ni_reinforcement_pct': ask_float("Enter NI network reinforcement rate (% change in its effective "
                                              "limit per year; 0 = none, negative = continued tightening)", 0.0),
            'new_build_ie_pct': ask_float(f"Enter share of NEW wind build located in IE/ROI (%) "
                                          f"(today's split is {100 * base_ie_share:.1f}%)", round(100 * base_ie_share, 1)),
        }

    def load_scenarios(path):
        """Read scenarios.csv; blank cells take the defaults."""
        table = pd.read_csv(path)
        table.columns = [c.strip().lower() for c in table.columns]
        defaults = {'build_rate_gw': DEFAULT_BUILD_RATE_GW, 'snsp_limit_pct': DEFAULT_SNSP_PCT,
                    'ie_reinforcement_pct': 0.0, 'ni_reinforcement_pct': 0.0,
                    'new_build_ie_pct': 100 * base_ie_share}
        scenarios = []
        for i, row in table.iterrows():
            name = str(row.get('scenario', '')).strip()
            if not name or name.lower() == 'nan':
                name = f"scenario_{i + 1}"
            sc = {'scenario': re.sub(r'[^A-Za-z0-9_.-]+', '_', name)}
            for key, default in defaults.items():
                val = row.get(key, np.nan)
                sc[key] = float(default) if pd.isna(val) or str(val).strip() == '' else float(val)
            sc['description'] = '' if pd.isna(row.get('description', np.nan)) else str(row.get('description'))
            scenarios.append(sc)
        return scenarios

    def run_scenario(sc, out_dir, make_charts=True):
        os.makedirs(out_dir, exist_ok=True)
        # 3. Decarbonisation Demand, Build Rate & SNSP User Prompts
        print("\n====================================================================")
        print(f" 3. SCENARIO '{sc['scenario']}': DEMAND, BUILD-RATE & SNSP CONFIGURATION")
        print("====================================================================")
        start_year = 2026
        final_year = 2050
        hzn = final_year - start_year
    
        base_demand_twh = 42.0
        annual_demand_growth_rate = 1.87
        tot_demand_2050 = base_demand_twh + (hzn * annual_demand_growth_rate)
    
        annual_build_rate_gw = float(sc['build_rate_gw'])
        snsp_limit_pct = float(sc['snsp_limit_pct'])
        snsp_limit_fraction = snsp_limit_pct / 100.0
        reinforcement_rate = {'IE': float(sc['ie_reinforcement_pct']) / 100.0,
                              'NI': float(sc['ni_reinforcement_pct']) / 100.0}
        new_build_ie_share = min(1.0, max(0.0, float(sc['new_build_ie_pct']) / 100.0))

        print(f"\n>> Baseline Demand (2026): {base_demand_twh:.2f} TWh")
        print(f">> Decarbonisation Demand Growth Rate: {annual_demand_growth_rate:.2f} TWh/year")
        print(f">> Projected Total Demand in {final_year}: {tot_demand_2050:.2f} TWh")
        print(f">> Selected Build-Out Rate: {annual_build_rate_gw*1000:.2f} MW/year ({annual_build_rate_gw:.3f} GW/year)")
        print(f">> COD Timing: New capacity ramps so first increment is fully online by END-2027")
        print(f">> Selected Forecast Operational SNSP Limit: {snsp_limit_pct:.1f}%")
        for reg in REGIONS:
            steps = REINFORCEMENT_STEPS_MW.get(reg, {})
            no_reinf = reinforcement_rate[reg] == 0 and not steps
            print(f">> {reg} Network Reinforcement: {100 * reinforcement_rate[reg]:.1f}%/yr on a "
                  f"{cons_params[reg]['limit_mw']:.0f} MW effective limit"
                  + (f", plus steps {steps}" if steps else "")
                  + (" (no reinforcement: upper bound)" if no_reinf else ""))
        print(f">> New build split: IE {100 * new_build_ie_share:.1f}% / NI {100 * (1 - new_build_ie_share):.1f}%")

        # 4. Weather-Loop Simulation & Loss Scaling Forecast
        print("\n====================================================================")
        print(" 4. WEATHER-LOOP SIMULATION & LOSS SCALING FORECAST (2026 - 2050)")
        print("====================================================================")
        base_capacity_gw = 6.51
    
        simulation_years = list(range(2026, 2051))
        sim_results = []
        complete_weather_years = [y for y in merged['year'].unique() if y < 2026]

        def capacity_for_year(year):
            """Installed capacity: 2026 baseline, then one full build increment per year from 2027."""
            return base_capacity_gw + max(0, year - start_year) * annual_build_rate_gw

        def region_limits(year):
            return {reg: limit_for_year(cons_params[reg], year, reinforcement_rate[reg],
                                        REINFORCEMENT_STEPS_MW.get(reg, {}))
                    for reg in REGIONS}

        def ie_share_for_capacity(cap_gw):
            """IE share of all-island availability: today's split for the existing fleet,
            the user's new-build split for capacity added after 2026."""
            added = max(0.0, cap_gw - base_capacity_gw)
            return (base_ie_share * base_capacity_gw + new_build_ie_share * added) / cap_gw

        def run_weather_years(cap_gw, demand_twh, limits, snsp_fraction):
            """Constraint (per region) then SNSP curtailment across all weather years, averaged."""
            ie_share = ie_share_for_capacity(cap_gw)
            rows = []
            for wy in complete_weather_years:
                df_wy = merged[merged['year'] == wy]
                avail = df_wy['spec_avail_mw_per_gw'].values * cap_gw
                hist_avg = df_wy['sem_demand'].mean()
                demand = df_wy['sem_demand'].values * ((demand_twh * 1e6 / 8760.0) / hist_avg if hist_avg > 0 else 1.0)

                reg_cons = regional_constraint_mw(avail, limits, ie_share)
                total_cons = sum(reg_cons.values())
                post_cons = np.maximum(0.0, avail - total_cons)
                excess = np.maximum(0.0, post_cons - demand * snsp_fraction)
                usable = post_cons - excess

                tot_av = avail.sum()
                if tot_av <= 0:
                    continue
                to_annual_twh = 0.25 / 1e6 * (365.25 / (len(avail) / 96.0))
                rows.append({
                    'avail_twh': tot_av * to_annual_twh,
                    'dispatch_twh': usable.sum() * to_annual_twh,
                    'curt_pct': 100 * excess.sum() / tot_av,
                    'cons_pct': 100 * total_cons.sum() / tot_av,
                    'IE_pts': 100 * reg_cons['IE'].sum() / tot_av,
                    'NI_pts': 100 * reg_cons['NI'].sum() / tot_av,
                    'IE_own_pct': 100 * reg_cons['IE'].sum() / (tot_av * ie_share) if ie_share > 0 else 0.0,
                    'NI_own_pct': 100 * reg_cons['NI'].sum() / (tot_av * (1 - ie_share)) if ie_share < 1 else 0.0,
                })
            out = pd.DataFrame(rows).mean().to_dict()
            out['ie_share'] = ie_share
            return out

        base_limits_2026 = region_limits(start_year)
        base_run = run_weather_years(base_capacity_gw, base_demand_twh, base_limits_2026, HISTORICAL_SNSP_PCT / 100.0)
        base_weather_oversupply_2026 = base_run['curt_pct']
        other_curt_pct = max(0.0, base_2026_curt - base_weather_oversupply_2026)
        print(f">> 2026 curtailment {base_2026_curt:.2f}% = modelled SNSP {base_weather_oversupply_2026:.2f}% "
              f"(at {HISTORICAL_SNSP_PCT:.0f}%) + other causes held fixed {other_curt_pct:.2f}%")
        base_model_cons_2026 = base_run['cons_pct']
        print(f">> Modelled 2026 constraint: {base_model_cons_2026:.2f}% of all-island available wind "
              f"(IE {base_run['IE_own_pct']:.2f}% of IE wind, NI {base_run['NI_own_pct']:.2f}% of NI wind); "
              f"spreadsheet 2026 figure: {base_2026_cons:.2f}%")

        for yr in simulation_years:
            years_elapsed = yr - start_year
            cap = capacity_for_year(yr)

            yr_demand = base_demand_twh + (years_elapsed * annual_demand_growth_rate)
            limits_yr = region_limits(yr)
            run = run_weather_years(cap, yr_demand, limits_yr, snsp_limit_fraction)

            avg_raw_curt_pct = other_curt_pct + run['curt_pct']
            sim_constraint_pct = run['cons_pct']
            total_loss_pct = min(100.0, avg_raw_curt_pct + sim_constraint_pct)

            implied_gen_twh = max(0.0, run['dispatch_twh'] - (other_curt_pct / 100.0) * run['avail_twh'])
            sim_cf = implied_gen_twh * 1000.0 / (cap * 8760.0)

            wind_pct_of_demand = (implied_gen_twh / yr_demand) * 100.0

            sim_results.append({
                'Year': yr,
                'Cap_GW': round(cap, 2),
                'Dem_TWh': round(yr_demand, 2),
                'RawCurt_%': round(avg_raw_curt_pct, 2),
                'GridCon_%': round(sim_constraint_pct, 2),
                'TotLoss_%': round(total_loss_pct, 2),
                'CF_%': round(sim_cf * 100, 2),
                'Wind_%': round(wind_pct_of_demand, 2),
                'IE_Share_%': round(100 * run['ie_share'], 1),
                'Limit_IE_MW': round(limits_yr['IE']),
                'Limit_NI_MW': round(limits_yr['NI']),
                'Con_IE_%': round(run['IE_own_pct'], 2),
                'Con_NI_%': round(run['NI_own_pct'], 2),
                'GridCon_IE_pts': round(run['IE_pts'], 2),
                'GridCon_NI_pts': round(run['NI_pts'], 2),
            })

        sim_df = pd.DataFrame(sim_results)
        sim_df['GridCon_Low_%'] = (sim_df['GridCon_%'] * (1 - hindcast_band)).round(2)
        sim_df['GridCon_High_%'] = (sim_df['GridCon_%'] * (1 + hindcast_band)).round(2)
        sim_df.insert(0, 'Scenario', sc['scenario'])
    
        key_years = [2026, 2027, 2028, 2030, 2033, 2036, 2039, 2042, 2045, 2048, 2049, 2050]
        key_df = sim_df[sim_df['Year'].isin(key_years)]
        main_cols = ['Year', 'Cap_GW', 'Dem_TWh', 'RawCurt_%', 'GridCon_%', 'GridCon_Low_%', 'GridCon_High_%',
                     'TotLoss_%', 'CF_%', 'Wind_%']
        region_cols = ['Year', 'IE_Share_%', 'Limit_IE_MW', 'Limit_NI_MW', 'Con_IE_%', 'Con_NI_%',
                       'GridCon_IE_pts', 'GridCon_NI_pts', 'GridCon_%']
        print("All-island results (GridCon_% = IE + NI constraint as a share of all-island available wind):")
        print(key_df[main_cols].to_string(index=False))
        print("\nConstraint by region (Con_IE_% / Con_NI_% are shares of each region's own available wind;")
        print("GridCon_IE_pts + GridCon_NI_pts = all-island GridCon_%):")
        print(key_df[region_cols].to_string(index=False))
        try:
            sim_df.to_csv(os.path.join(out_dir, FORECAST_RESULTS_CSV), index=False)
            print(f"\n>> Every year, with the regional split, saved to '{os.path.join(out_dir, FORECAST_RESULTS_CSV)}'")
        except OSError as e:
            print(f"\n>> Could not save '{FORECAST_RESULTS_CSV}': {e}")

        print("\n====================================================================")
        print(f" 2050 MODEL OUTCOME SUMMARY")
        print("====================================================================")
        row_2050 = sim_df[sim_df['Year'] == 2050].iloc[0]
        actual_cap_gw = row_2050['Cap_GW']
        actual_dem_twh = row_2050['Dem_TWh']
        actual_wind_pct = row_2050['Wind_%']
        actual_gen_twh = max(0.0, actual_dem_twh * (actual_wind_pct / 100.0))
    
        peak_demand_2050_gw = actual_dem_twh / (8760.0 * 0.68 / 1000.0)
        firm_thermal_required_gw = peak_demand_2050_gw * 0.90
    
        print(f">> Total Projected Demand (2050)      : {actual_dem_twh:.2f} TWh")
        print(f">> Usable Wind Generation (2050)      : {actual_gen_twh:.2f} TWh ({actual_wind_pct:.2f}% of demand)")
        print(f">> Installed Wind Capacity (2050)     : {actual_cap_gw:.2f} GW")
        print(f">> Required Firm Thermal Plant (2050) : {firm_thermal_required_gw:.2f} GW (Dunkelflaute Backup)")
        print(f">> Applied Build-Out Rate             : {annual_build_rate_gw*1000:.2f} MW/year ({annual_build_rate_gw:.3f} GW/year)")
        print(f">> Applied Forecast SNSP Limit       : {snsp_limit_pct:.1f}%")

        if not make_charts:
            return sim_df

        hist_weather_map = {fy: complete_weather_years[i % len(complete_weather_years)]
                            for i, fy in enumerate(range(start_year, final_year + 1))}

        def regional_setup(row):
            """Region limits and IE availability share for a year's results row."""
            limits = {'IE': float(row['Limit_IE_MW']), 'NI': float(row['Limit_NI_MW'])}
            return limits, float(row['IE_Share_%']) / 100.0

        plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')

        # -------------------------------------------------------------------------
        # GRAPH 1: HISTORICAL & NEAR-TERM FORECAST (JAN 2019 - DEC 2030)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 5. GENERATING GRAPH 1: HISTORICAL & NEAR-TERM FORECAST (2019 - 2030)")
        print("====================================================================")
    
        def monthly_series(years, historical=False):
            records = []
            for y in years:
                if historical:
                    df_y = merged[merged['year'] == y]
                    for m, g in df_y.groupby('month'):
                        hours = pd.Period(f"{y}-{m:02d}").days_in_month * 24.0
                        records.append({'year': y, 'month': m,
                                        'demand_gwh': g['sem_demand'].mean() * hours / 1000.0,
                                        'usable_wind_gwh': max(0.0, g['sem_wind_generation'].mean() * hours / 1000.0)})
                    continue
                row = sim_df[sim_df['Year'] == y].iloc[0]
                cap_y, dem_y = float(row['Cap_GW']), float(row['Dem_TWh'])
                limits_y, share_y = regional_setup(row)
                df_wy = merged[merged['year'] == hist_weather_map[y]]
                hist_avg = df_wy['sem_demand'].mean()
                scale = (dem_y * 1e6 / 8760.0) / hist_avg if hist_avg > 0 else 1.0
                for m, g in df_wy.groupby('month'):
                    hours = pd.Period(f"{y}-{m:02d}").days_in_month * 24.0
                    avail = g['spec_avail_mw_per_gw'].values * cap_y
                    demand = g['sem_demand'].values * scale
                    reg = regional_constraint_mw(avail, limits_y, share_y)
                    post_cons = np.maximum(0.0, avail - reg['IE'] - reg['NI'])
                    usable = np.minimum(post_cons, demand * snsp_limit_fraction)
                    usable = np.maximum(0.0, usable - (other_curt_pct / 100.0) * avail)
                    records.append({'year': y, 'month': m,
                                    'demand_gwh': demand.mean() * hours / 1000.0,
                                    'usable_wind_gwh': usable.mean() * hours / 1000.0})
            return records

        records_19_30 = monthly_series(range(2019, 2026), historical=True) + monthly_series(range(2026, 2031))
        df_g1 = pd.DataFrame(records_19_30)
        df_g1['date'] = pd.to_datetime(df_g1[['year', 'month']].assign(day=1))
        df_g1 = df_g1.sort_values('date').drop_duplicates(subset=['date'], keep='first')

        fig1, ax1 = plt.subplots(figsize=(12, 6.5), dpi=300)

        ax1.fill_between(df_g1['date'], 0, df_g1['usable_wind_gwh'], color='#90EE90', edgecolor='#2CA02C', linewidth=0.8, label='Wind Gen (GWh)', alpha=0.9)
        ax1.plot(df_g1['date'], df_g1['demand_gwh'], color='black', linewidth=2.2, label='Demand (GWh)')

        x_nums1 = mdates.date2num(df_g1['date'])
        z_d1 = np.polyfit(x_nums1, df_g1['demand_gwh'], 1)
        p_d1 = np.poly1d(z_d1)
        ax1.plot(df_g1['date'], p_d1(x_nums1), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        row_2030 = sim_df[sim_df['Year'] == 2030].iloc[0]
        wind_pct_2030 = float(row_2030['Wind_%'])

        ax1.plot([], [], ' ', label=f'2030 Wind % of Demand: {wind_pct_2030:.1f}%')

        ax1.set_title('Ireland (All-Island) Overview + Short term 2030 Forecast (Jan 2019 to Dec 2030)', fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax1.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax1.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax1.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax1.xaxis.set_major_locator(mdates.YearLocator(1))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax1.set_xlim(df_g1['date'].iloc[0], df_g1['date'].iloc[-1])

        ax1.legend(loc='lower left', frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=10)

        stats_text1 = (
            f"2026 Demand: {base_demand_twh:.2f} TWh\n"
            f"2026 Wind %: {base_2026_wind_pct:.1f}%\n"
            f"2030 Demand: {row_2030['Dem_TWh']:.2f} TWh\n"
            f"2030 Wind %: {wind_pct_2030:.1f}%\n"
            f"Build Rate: {annual_build_rate_gw*1000:.1f} MW/yr\n"
            f"SNSP Limit: {snsp_limit_pct:.1f}%"
        )
        ax1.text(0.81, 0.40, stats_text1, transform=ax1.transAxes, fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

        plt.tight_layout()
        g1_png = "XEnergy_Historical_2019_2030_Overview.png"
        plt.savefig(os.path.join(out_dir, g1_png))
        print(f">> Graph 1 saved as '{g1_png}'!")

        # -------------------------------------------------------------------------
        # GRAPH 2: LONG-TERM FORECAST STACKED OVERVIEW (JAN 2045 - DEC 2050)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 6. GENERATING GRAPH 2: LONG-TERM FORECAST (2045 - 2050)")
        print("====================================================================")
    
        df_monthly2 = pd.DataFrame(monthly_series(range(2045, 2051)))
        df_monthly2['date'] = pd.to_datetime(df_monthly2[['year', 'month']].assign(day=1))
        df_monthly2 = df_monthly2.sort_values('date')

        fig2, ax2 = plt.subplots(figsize=(12, 6.5), dpi=300)

        ax2.fill_between(df_monthly2['date'], 0, df_monthly2['usable_wind_gwh'], color='#90EE90', edgecolor='#2CA02C', linewidth=0.8, label='Wind Gen (GWh)', alpha=0.9)
        ax2.plot(df_monthly2['date'], df_monthly2['demand_gwh'], color='black', linewidth=2.2, label='Demand (GWh)')

        x_nums2 = mdates.date2num(df_monthly2['date'])
        z_d2 = np.polyfit(x_nums2, df_monthly2['demand_gwh'], 1)
        p_d2 = np.poly1d(z_d2)
        ax2.plot(df_monthly2['date'], p_d2(x_nums2), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        ax2.plot([], [], ' ', label=f'2050 Wind % of Demand: {actual_wind_pct:.1f}%')

        ax2.set_title('Ireland (All-Island) Energy Transition Forecast (Jan 2045 to Dec 2050)', fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax2.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax2.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax2.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax2.xaxis.set_major_locator(mdates.YearLocator(1))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax2.set_xlim(df_monthly2['date'].iloc[0], df_monthly2['date'].iloc[-1])

        ax2.legend(loc='lower left', frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=10)

        stats_text2 = (
            f"2050 Demand: {actual_dem_twh:.2f} TWh\n"
            f"2050 Usable Wind: {actual_gen_twh:.2f} TWh\n"
            f"2050 Wind %: {actual_wind_pct:.2f}%\n"
            f"2050 Firm Plant Req: {firm_thermal_required_gw:.2f} GW\n"
            f"Build Rate: {annual_build_rate_gw*1000:.1f} MW/yr\n"
            f"SNSP Limit: {snsp_limit_pct:.1f}%"
        )
        ax2.text(0.81, 0.40, stats_text2, transform=ax2.transAxes, fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

        plt.tight_layout()
        g2_png = "XEnergy_Forecast_2045_2050_Overview.png"
        plt.savefig(os.path.join(out_dir, g2_png))
        print(f">> Graph 2 saved as '{g2_png}'!")

        # -------------------------------------------------------------------------
        # HELPER FUNCTION FOR DAILY DISPATCH PROFILE CHARTS (GRAPHS 3, 4, 5, 6)
        # -------------------------------------------------------------------------
        def generate_daily_chart(target_year, month_num, day_num, output_filename, chart_title_suffix):
            row_yr = sim_df[sim_df['Year'] == target_year].iloc[0]
            cap_gw = float(row_yr['Cap_GW'])
            demand_twh = float(row_yr['Dem_TWh'])
            limits_yr, ie_share_yr = regional_setup(row_yr)

            wy = hist_weather_map.get(target_year, complete_weather_years[target_year % len(complete_weather_years)])
            df_wy = merged[merged['year'] == wy].copy()
        
            df_wy['scaled_avail_mw'] = df_wy['spec_avail_mw_per_gw'] * cap_gw
            expected_avg_mw = (demand_twh * 1000000.0) / 8760.0
            actual_hist_avg_mw = df_wy['sem_demand'].mean()
            mw_scale = expected_avg_mw / actual_hist_avg_mw if actual_hist_avg_mw > 0 else 1.0
            df_wy['scaled_demand_mw'] = df_wy['sem_demand'] * mw_scale
        
            df_day = df_wy[(df_wy['month'] == month_num) & (df_wy['day'] == day_num)].copy().sort_values('parsed_date')
            if len(df_day) == 0:
                print(f"Warning: Day {day_num} Month {month_num} not present in dataset!")
                return
            
            month_name = pd.to_datetime(f"2022-{month_num:02d}-{day_num:02d}").strftime('%B')
        
            time_hours = np.linspace(0, 24, len(df_day))
            d_mw = df_day['scaled_demand_mw'].values
            avail_w_mw = df_day['scaled_avail_mw'].values
            snsp_limit_mw = d_mw * snsp_limit_fraction
        
            reg_cons_mw = regional_constraint_mw(avail_w_mw, limits_yr, ie_share_yr)
            grid_constraint_mw = reg_cons_mw['IE'] + reg_cons_mw['NI']
            constrained_avail_mw = np.maximum(0, avail_w_mw - grid_constraint_mw)
            snsp_curtailed_mw = np.maximum(0, constrained_avail_mw - snsp_limit_mw)
            usable_w_mw = np.maximum(0, np.minimum(constrained_avail_mw, snsp_limit_mw))
            total_dispatch_down_mw = grid_constraint_mw + snsp_curtailed_mw
        
            fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)

            ax.plot(time_hours, avail_w_mw, color='#2CA02C', linewidth=2.0, linestyle='--', label='Available Wind Potential (MW)')
            ax.plot(time_hours, d_mw, color='black', linewidth=2.5, label='System Demand (MW)')
            ax.plot(time_hours, snsp_limit_mw, color='#D62728', linewidth=2.0, linestyle='-', label=f'SNSP Limit ({snsp_limit_pct:.1f}% of Demand)')

            ax.fill_between(time_hours, 0, usable_w_mw, color='#90EE90', alpha=0.85, label='Usable Dispatched Wind (MW)')
            ax.fill_between(time_hours, snsp_limit_mw, constrained_avail_mw, where=(constrained_avail_mw > snsp_limit_mw),
                            facecolor='none', edgecolor='#D62728', hatch='///', linewidth=0.8, label='SNSP Curtailment (MW)')
            ax.fill_between(time_hours, constrained_avail_mw, avail_w_mw, where=(avail_w_mw > constrained_avail_mw),
                            facecolor='none', edgecolor='#FF8C00', hatch='\\\\\\', linewidth=0.8, label='Grid Bottleneck Constraint (MW)')

            ax.set_title(f'Forecasted Daily Chart: - {chart_title_suffix} ,    {day_num} {month_name} {target_year}', fontsize=13, fontweight='bold', color='#000080', pad=15)
            ax.set_ylabel('Power Generation & Demand (MW)', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time of Day (Hours)', fontsize=11, fontweight='bold')
            ax.set_xticks(range(0, 25, 2))
            ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 25, 2)])
            ax.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

            ax.legend(loc='lower center', bbox_to_anchor=(0.5, 0.12), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=9.5, ncol=2)

            daily_avail_gwh = (avail_w_mw.sum() * 0.25) / 1000.0
            daily_dem_gwh = (d_mw.sum() * 0.25) / 1000.0
            daily_curt_gwh = (snsp_curtailed_mw.sum() * 0.25) / 1000.0
            daily_cons_gwh = (grid_constraint_mw.sum() * 0.25) / 1000.0
            daily_cons_ie_gwh = (reg_cons_mw['IE'].sum() * 0.25) / 1000.0
            daily_cons_ni_gwh = (reg_cons_mw['NI'].sum() * 0.25) / 1000.0
            daily_tot_dd_gwh = (total_dispatch_down_mw.sum() * 0.25) / 1000.0
            daily_dd_pct = (daily_tot_dd_gwh / daily_avail_gwh) * 100.0 if daily_avail_gwh > 0 else 0.0

            stats_text = (
                f"Simulated Date: {day_num} {month_name} {target_year}\n"
                f"Weather Reference: {wy}\n"
                f"Wind Fleet Installed Capacity: {cap_gw:.2f} GW\n"
                f"Network Limits: IE {limits_yr['IE']:.0f} / NI {limits_yr['NI']:.0f} MW\n"
                f"Daily Demand: {daily_dem_gwh:.1f} GWh\n"
                f"Available Wind: {daily_avail_gwh:.1f} GWh\n"
                f"Grid Constraint: {daily_cons_gwh:.1f} GWh (IE {daily_cons_ie_gwh:.1f}, NI {daily_cons_ni_gwh:.1f})\n"
                f"SNSP Curtailment: {daily_curt_gwh:.1f} GWh\n"
                f"Total Dispatch Down: {daily_tot_dd_gwh:.1f} GWh ({daily_dd_pct:.1f}%)\n"
                f"SNSP Limit: {snsp_limit_pct:.1f}%"
            )
            ax.text(0.02, 0.58, stats_text, transform=ax.transAxes, fontsize=9.5, fontweight='bold', color='#000080',
                     bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, output_filename))
            print(f">> Chart saved as '{output_filename}' for {day_num} {month_name} {target_year}!")

        # -------------------------------------------------------------------------
        # GENERATE DAILY DISPATCH PROFILES (GRAPHS 3, 4, 5, 6)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 7. GENERATING DAILY SHOWCASE PROFILES (2033 & 2048)")
        print("====================================================================")
        
        # 2048 Calculations (Storm, Typical Low, Dunkelflaute)
        wy_2048 = hist_weather_map[2048]
        df_wy_2048 = merged[merged['year'] == wy_2048].copy()
        df_wy_2048['scaled_avail_mw'] = df_wy_2048['spec_avail_mw_per_gw'] * float(sim_df[sim_df['Year'] == 2048]['Cap_GW'].values[0])
        daily_sums_2048 = df_wy_2048.groupby(['month', 'day'])['scaled_avail_mw'].sum().reset_index()
        daily_sums_2048 = daily_sums_2048.sort_values('scaled_avail_mw', ascending=True).reset_index(drop=True)
        
        dunkel_day = daily_sums_2048.iloc[0] # Absolute minimum wind availability
        low_avg_day = daily_sums_2048.iloc[int(len(daily_sums_2048) * 0.30)] # 30th percentile
        storm_day = daily_sums_2048.iloc[-1] # Absolute maximum wind availability
        
        # 2033 Calculations (Average)
        wy_2033 = hist_weather_map.get(2033, complete_weather_years[2033 % len(complete_weather_years)])
        df_wy_2033 = merged[merged['year'] == wy_2033].copy()
        df_wy_2033['scaled_avail_mw'] = df_wy_2033['spec_avail_mw_per_gw'] * float(sim_df[sim_df['Year'] == 2033]['Cap_GW'].values[0])
        daily_sums_2033 = df_wy_2033.groupby(['month', 'day'])['scaled_avail_mw'].sum().reset_index()
        daily_sums_2033 = daily_sums_2033.sort_values('scaled_avail_mw', ascending=True).reset_index(drop=True)
        
        avg_day_2033 = daily_sums_2033.iloc[int(len(daily_sums_2033) * 0.50)] # 50th percentile (Median average)
        
        # Generate Graph 3 (Storm 2048)
        generate_daily_chart(2048, int(storm_day['month']), int(storm_day['day']), "XEnergy_Daily_Absolute_Storm_2048.png", "Absolute Peak Wind Storm Event")
        
        # Generate Graph 4 (Typical Low 2048)
        generate_daily_chart(2048, int(low_avg_day['month']), int(low_avg_day['day']), "XEnergy_Daily_Typical_Low_Average_2048.png", "Typical Low-Average Wind Day")
        
        # Generate Graph 5 (Dunkelflaute 2048)
        generate_daily_chart(2048, int(dunkel_day['month']), int(dunkel_day['day']), "XEnergy_Daily_Dunkelflaute_2048.png", "Dunkelflaute Extreme Low Wind Event")
        
        # Generate Graph 6 (Average 2033)
        generate_daily_chart(2033, int(avg_day_2033['month']), int(avg_day_2033['day']), "XEnergy_Daily_Average_Wind_2033.png", "Average Wind Day")

        # -------------------------------------------------------------------------
        # GRAPH 7: GRAND MASTER OVERVIEW (JAN 2019 - DEC 2050)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 8. GENERATING GRAPH 7: GRAND MASTER OVERVIEW (2019 - 2050)")
        print("====================================================================")
    
        # Extract Maximum Wind % Attained and the Year it occurred for the stats box
        max_wind_row = sim_df.loc[sim_df['Wind_%'].idxmax()]
        max_wind_pct_val = max_wind_row['Wind_%']
        max_wind_year = int(max_wind_row['Year'])

        df_grand = pd.DataFrame(monthly_series(range(2019, 2026), historical=True)
                                + monthly_series(range(2026, 2051)))

        df_grand['date'] = pd.to_datetime(df_grand[['year', 'month']].assign(day=1))
        df_grand = df_grand.sort_values('date').drop_duplicates(subset=['date'], keep='first')

        fig6, ax6 = plt.subplots(figsize=(14, 7), dpi=300)

        ax6.fill_between(df_grand['date'], 0, df_grand['usable_wind_gwh'], color='#90EE90', edgecolor='#2CA02C', linewidth=0.8, label='Usable Wind Gen (GWh)', alpha=0.9)
        ax6.plot(df_grand['date'], df_grand['demand_gwh'], color='black', linewidth=2.0, label='System Demand (GWh)')

        x_nums6 = mdates.date2num(df_grand['date'])
        z_d6 = np.polyfit(x_nums6, df_grand['demand_gwh'], 1)
        p_d6 = np.poly1d(z_d6)
        ax6.plot(df_grand['date'], p_d6(x_nums6), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        ax6.set_title('Ireland (All-Island) Grand Energy Transition Timeline & Wind Penetration (Jan 2019 to Dec 2050)', fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax6.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax6.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax6.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax6.xaxis.set_major_locator(mdates.YearLocator(2))
        ax6.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax6.set_xlim(df_grand['date'].iloc[0], df_grand['date'].iloc[-1])

        ax6.legend(loc='lower center', bbox_to_anchor=(0.5, 0.03), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=10, ncol=3)

        # Added Max Wind % Attained (and the year) to the stats box
        stats_text6 = (
            f"2026 Demand: {base_demand_twh:.1f} TWh | Wind: {base_2026_wind_pct:.1f}%\n"
            f"2050 Demand: {actual_dem_twh:.1f} TWh | Wind: {actual_wind_pct:.1f}%\n"
            f"Max Wind Attained: {max_wind_pct_val:.1f}% (in {max_wind_year})\n"
            f"Build Rate: {annual_build_rate_gw*1000:.0f} MW/yr | SNSP: {snsp_limit_pct:.0f}%"
        )
        ax6.text(0.02, 0.78, stats_text6, transform=ax6.transAxes, fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

        plt.tight_layout()
        g6_png = "XEnergy_Grand_Overview_2019_2050.png"
        plt.savefig(os.path.join(out_dir, g6_png))
        print(f">> Grand Overview chart saved as '{g6_png}'!")
        plt.close('all')
        return sim_df

    if os.path.exists(SCENARIO_FILE):
        scenarios = load_scenarios(SCENARIO_FILE)
        print(f"\n>> Running {len(scenarios)} scenarios from '{SCENARIO_FILE}' "
              f"(charts {'on' if SCENARIO_CHARTS else 'off'})")
        summary_rows, all_results = [], []
        for sc in scenarios:
            out_dir = os.path.join(SCENARIO_OUTPUT_DIR, sc['scenario'])
            res = run_scenario(sc, out_dir, make_charts=SCENARIO_CHARTS)
            all_results.append(res)
            for yr in (2030, 2040, 2050):
                r = res[res['Year'] == yr]
                if r.empty:
                    continue
                r = r.iloc[0]
                summary_rows.append({
                    'Scenario': sc['scenario'], 'Description': sc['description'], 'Year': yr,
                    'Build_GW_per_yr': round(sc['build_rate_gw'], 3), 'SNSP_%': sc['snsp_limit_pct'],
                    'IE_Reinf_%_yr': sc['ie_reinforcement_pct'], 'NI_Reinf_%_yr': sc['ni_reinforcement_pct'],
                    'NewBuild_IE_%': round(sc['new_build_ie_pct'], 1),
                    'Cap_GW': r['Cap_GW'], 'Dem_TWh': r['Dem_TWh'],
                    'GridCon_%': r['GridCon_%'], 'GridCon_Low_%': r['GridCon_Low_%'],
                    'GridCon_High_%': r['GridCon_High_%'], 'Con_IE_%': r['Con_IE_%'],
                    'Con_NI_%': r['Con_NI_%'], 'RawCurt_%': r['RawCurt_%'], 'TotLoss_%': r['TotLoss_%'],
                    'CF_%': r['CF_%'], 'Wind_%': r['Wind_%'],
                })
        summary = pd.DataFrame(summary_rows)
        summary.to_csv(SCENARIO_SUMMARY_CSV, index=False)
        pd.concat(all_results, ignore_index=True).to_csv(
            os.path.join(SCENARIO_OUTPUT_DIR, "all_scenarios_by_year.csv"), index=False)
        print("\n====================================================================")
        print(" SCENARIO SUMMARY")
        print("====================================================================")
        print(summary[summary['Year'] == 2050][['Scenario', 'GridCon_%', 'GridCon_Low_%', 'GridCon_High_%',
                                                'Con_IE_%', 'Con_NI_%', 'RawCurt_%', 'Wind_%']].to_string(index=False))
        print(f"\n>> Summary (2030/2040/2050) saved to '{SCENARIO_SUMMARY_CSV}'; every year of every "
              f"scenario saved to '{os.path.join(SCENARIO_OUTPUT_DIR, 'all_scenarios_by_year.csv')}'")
    else:
        run_scenario(interactive_scenario(), ".", make_charts=True)

if __name__ == "__main__":
    run_demonstrator()