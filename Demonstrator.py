"""
================================================================================
IRELAND (SEM) - ADVANCED WIND + SOLAR + STORAGE CAPACITY w/ LOSS MODELING DEMO
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
  today's availability share for the existing fleet; new build is placed by the regional build rates.
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

BACKCAST:
- The forecast's own starting model (the L and sigma used for the forecast) is run backwards
  over every historical year, using that year's actual hourly availability, and compared with
  recorded constraint, with the limits held at their fitted values. This is the same for every
  scenario: future reinforcement rates describe the future and are not run backwards (unless
  BACKCAST_SCENARIO_TREND = True). Errors are reported per year as % of actual and as
  percentage points of constraint, and summarised for the years outside the fit.

SOLAR:
- Solar has its own IE and NI build rates (scenario inputs) from a 2026 capacity estimated from the solar
  dispatch-down records. Its 15-minute profile comes from the solar series in the 15-minute file,
  scaled by SOLAR_CAPACITY_FACTOR.
- Solar shares each region's network limit with wind (the limit is fitted to wind + solar
  constraint records), and SNSP counts wind and solar together. Constraint and SNSP curtailment
  are shared between them in proportion to their available output in each interval, so more
  solar raises wind losses and vice versa. Results are reported for wind, solar and both.

SCENARIOS:
- If scenarios.csv exists, each row is run without prompts (build rate, SNSP limit, IE/NI
  reinforcement, and Build rate_WIND_IE / _WIND_NI / _SOLAR_IE / _SOLAR_NI in GW/yr) and results are written per scenario, plus a summary.
  The error for each test year is reported.

GRAPHICAL OUTPUT ENGINE (8 CHARTS):
1. Historical & Near-Term Forecast Chart (Jan 2019 - Dec 2030) - Full Weather Granularity
2. Long-Term Forecast Stacked Overview Chart (Jan 2045 - Dec 2050) - Full Weather (6 year loop of weather)
3. Absolute Peak Wind Storm Day Dispatch Profile (2048) - Max Wind Generation Showcaser
4. Typical Low-Average Wind Day Dispatch Profile (2048) 
5. Dunkelflaute Extreme Low Wind Day Dispatch Profile (2048) 
6. Average Wind Day Dispatch Profile (2033)
7. Grand Master Overview (Jan 2019 - Dec 2050) - Full 32-Year Monthly GWh Timeline with Saturation Plateau
8. Constraint Backcast & Forecast by Region - actual, backcast from the forecast starting model, forecast
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
# Folders (relative to this script). Inputs are read from INPUT_DIR; if a file isn't there,
# the project folder is checked as a fallback. All outputs go under SCENARIO_OUTPUT_DIR.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = "Data_inputs"
INPUT_DIR_ALIASES = ("Data_inputs", "data_inputs")
SCENARIO_FILE = "scenarios.xlsx"
SCENARIO_SHEET = "Scenarios"
SCENARIO_OUTPUT_DIR = "scenario_outputs"
SCENARIO_SUMMARY_CSV = "scenario_summary.csv"   # written inside SCENARIO_OUTPUT_DIR
SCENARIO_CHARTS = True                    
DEFAULT_BUILD_RATE_GW = 1.87 / (8760 * 0.40 / 1000.0)   # ~0.534 GW/yr
DEFAULT_SNSP_PCT = 75.0
DEFAULT_DEMAND_RATE_TWH_PER_YEAR = 1.87
INTERVAL_HOURS = 0.25

# Minimum-generation floor
# Conventional units at 150 MW eacj. 7 minimum stable output gives a 1050 MW floor.
NUM_MIN_UNITS = 6
MIN_OUTPUT_PER_UNIT_MW = 250.0
MUON_FLOOR_MW = NUM_MIN_UNITS * MIN_OUTPUT_PER_UNIT_MW
DEFAULT_MUON_UNITS_IE = 4
DEFAULT_MUON_UNITS_NI = 3
MUON_MIN_GEN_PER_UNIT_MW = 150.0

# Standalone, non-hybrid battery defaults. Storage charges only from energy that
# remains operationally curtailed AFTER regional grid constraints are applied.
DEFAULT_STORAGE_POWER_BUILD_RATE_MW = 0.0
DEFAULT_STORAGE_ENERGY_BUILD_RATE_MWH = 0.0
DEFAULT_STORAGE_POWER_2026_MW = 0.0
DEFAULT_STORAGE_ENERGY_2026_MWH = 0.0
DEFAULT_STORAGE_CHARGE_EFFICIENCY = 0.95
DEFAULT_STORAGE_DISCHARGE_EFFICIENCY = 0.95
DEFAULT_STORAGE_INITIAL_SOC_PCT = 50.0
DEFAULT_PC_STORAGE_HYBRID = 5.0

# 15-minute demand / wind / solar series. The first file found is used.
DEMAND_WIND_FILES = ["sem_demand_wind_solar_master.csv", "sem_demand_wind_from_2019.csv"]
# The forecast scales this file's wind availability, so it must be all-island and on the same
# basis as the IE + NI dispatch-down files. If they differ by more than this, the run stops.
MAX_AVAILABILITY_MISMATCH = 0.25
# Backcast: False (default) runs the forecast's starting limits back over history with no trend,
# the same for every scenario. True also runs each scenario's reinforcement rate backwards, which
# only makes sense for scenarios that continue the historical trend.
BACKCAST_SCENARIO_TREND = False

# =============================================================================
# SOLAR SETTINGS
# =============================================================================
# Solar dispatch-down records (built by build_all_island_dd.py). If present, solar shares each
# region's network limit with wind: the limit is fitted to wind + solar together, and in every
# interval the constraint is shared between them in proportion to their available output.
SOLAR_DD_FILES = {'IE': "system_dd_hourly_ie_solar.csv", 'NI': "system_dd_hourly_ni_solar.csv"}
SOLAR_CAPACITY_FACTOR = 0.11              # average available output / installed capacity
SOLAR_CAPACITY_2026_GW = None             # None = estimate from the last 12 months of solar
                                          # availability records / (capacity factor x 8760 h)
SOLAR_CAPACITY_FALLBACK_GW = 2.0          # used only if there are no solar records
DEFAULT_SOLAR_BUILD_RATE_GW = 0.0         # GW/yr when a scenario leaves it blank          # 0.25 = stop if the ratio is outside 0.8-1.25


def input_path(name):
    """Find an input relative to the script, not the terminal working directory."""
    candidates = []
    for folder in INPUT_DIR_ALIASES:
        candidates.append(os.path.join(BASE_DIR, folder, name))
    candidates.append(os.path.join(BASE_DIR, name))
    candidates.append(name)
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    # Return the intended primary location so any error message is explicit.
    return os.path.join(BASE_DIR, INPUT_DIR, name)


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
    # Read inputs and write outputs next to this script, whatever the working directory is
    # (Spyder and other IDEs don't always start in the script's folder).
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    print("=" * 90)
    print("      IRELAND (SEM) - WIND, SOLAR & STORAGE DEMONSTRATOR V6      ")
    print("      (Featuring Historical Hindcast Validation & 6-Chart Engine) ")
    print("=" * 90)

    # 1. Load Excel Historical Tables & CSV Data
    if not os.path.isdir(INPUT_DIR):
        print(f">> ! Input folder '{INPUT_DIR}' not found; looking for inputs in the project folder.")
    excel_file = input_path("Input - capacity, constraints, curtailment.xlsx")
    csv_file = next((input_path(f) for f in DEMAND_WIND_FILES if os.path.exists(input_path(f))),
                    input_path(DEMAND_WIND_FILES[0]))
    print(f">> Capacity workbook: '{excel_file}'")
    print(f">> 15-minute demand/wind file: '{csv_file}'")
    if not (os.path.exists(excel_file) and os.path.exists(csv_file)):
        raise FileNotFoundError(f"Need '{excel_file}' and '{csv_file}' (put them in '{INPUT_DIR}').")
    os.makedirs(SCENARIO_OUTPUT_DIR, exist_ok=True)
    
    base_2026_curt = 4.9
    base_2026_cons = 10.0
    base_2026_cf = 23.0
    base_2026_wind_pct = 33.733919
    
    if os.path.exists(excel_file) and os.path.exists(csv_file):
        df_cap = pd.read_excel(excel_file, sheet_name='CapacityByYear')
        df_cons = pd.read_excel(excel_file, sheet_name='ConstraintsbyYear')
        df_curt = pd.read_excel(excel_file, sheet_name='RawCurtailmentbyYear')
        df_cf = pd.read_excel(excel_file, sheet_name='CapacityFactorbyYear')

        # CapacityByYear may contain two 2026 rows: the September/current fleet
        # and the forecast year-end/final fleet. Read the first four columns as
        # year, ROI, NI and all-island SEM total; an optional fifth column is the
        # status label (current/final). This avoids a many-to-many merge.
        cap_cols = ['year', 'ROI_MW', 'NI_MW', 'Total_MW']
        if df_cap.shape[1] < 4:
            raise ValueError("CapacityByYear must contain year, ROI MW, NI MW and total SEM MW.")
        rename_cap = {df_cap.columns[i]: cap_cols[i] for i in range(4)}
        if df_cap.shape[1] >= 5:
            rename_cap[df_cap.columns[4]] = 'capacity_status'
        df_cap = df_cap.rename(columns=rename_cap)
        if 'capacity_status' not in df_cap.columns:
            df_cap['capacity_status'] = ''
        df_cap['capacity_status'] = df_cap['capacity_status'].fillna('').astype(str).str.strip().str.lower()
        for col in cap_cols:
            df_cap[col] = pd.to_numeric(df_cap[col], errors='coerce')
        df_cap = df_cap.dropna(subset=['year', 'Total_MW']).copy()
        df_cap['year'] = df_cap['year'].astype(int)

        df_cons.columns = ['year', 'Constraint_Pct', 'col2', 'notes']
        df_curt.columns = ['year', 'Curtailment_Pct', 'col2', 'notes']
        df_cf.columns = ['year', 'Capacity_Factor_Pct', 'col2', 'notes']
        for frame in (df_cons, df_curt, df_cf):
            frame['year'] = pd.to_numeric(frame['year'], errors='coerce')

        def capacity_row_for_year(year, prefer_final=False):
            rows = df_cap.loc[df_cap['year'] == year].copy()
            if rows.empty:
                raise ValueError(f"No CapacityByYear row found for {year}.")
            if prefer_final:
                labelled = rows.loc[rows['capacity_status'].str.contains('final', case=False, na=False)]
                return (labelled.iloc[-1] if not labelled.empty else rows.iloc[-1])
            labelled = rows.loc[rows['capacity_status'].str.contains('current|actual', case=False, na=False)]
            return (labelled.iloc[0] if not labelled.empty else rows.iloc[0])

        # One historical/current capacity row per year for normalising actual data.
        historical_capacity_rows = [capacity_row_for_year(y, prefer_final=False)
                                    for y in sorted(df_cap['year'].unique())]
        df_cap_hist = pd.DataFrame(historical_capacity_rows).reset_index(drop=True)
        final_2026_capacity = capacity_row_for_year(2026, prefer_final=True)
        final_2026_wind_capacity_gw = float(final_2026_capacity['Total_MW']) / 1000.0

        hist_df = df_cap_hist[['year', 'Total_MW']].copy()
        hist_df['Capacity_GW'] = hist_df['Total_MW'] / 1000.0
        hist_df = hist_df.merge(df_cons[['year', 'Constraint_Pct']], on='year', how='left')
        hist_df = hist_df.merge(df_curt[['year', 'Curtailment_Pct']], on='year', how='left')
        hist_df = hist_df.merge(df_cf[['year', 'Capacity_Factor_Pct']], on='year', how='left')

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
        
        merged = pd.merge(df_15m, df_cap_hist[['year', 'Total_MW']], on='year', how='inner')
        merged['installed_gw'] = merged['Total_MW'] / 1000.0
        merged['spec_avail_mw_per_gw'] = merged['sem_wind_availability'] / merged['installed_gw']

        # Solar profile per GW installed. Historical solar capacity isn't in the inputs, so each
        # year's solar series is normalised to its own mean (its shape) and scaled by
        # SOLAR_CAPACITY_FACTOR. Availability is used where it looks complete, otherwise
        # generation. Years with no solar data use the average shape for that month and time of day.
        def solar_series(g):
            av = g['sem_solar_availability'] if 'sem_solar_availability' in g else None
            gen = g['sem_solar_generation'] if 'sem_solar_generation' in g else None
            av_sum = av.sum() if av is not None else 0.0
            gen_sum = gen.sum() if gen is not None else 0.0
            if av is not None and av_sum > 0 and av_sum >= 0.9 * gen_sum:
                return av.fillna(0.0)
            if gen is not None and gen_sum > 0:
                return gen.fillna(0.0)
            return None

        merged['solar_shape'] = np.nan
        for y, g in merged.groupby('year'):
            ser = solar_series(g)
            if ser is not None and ser.mean() > 0:
                merged.loc[g.index, 'solar_shape'] = (ser.clip(lower=0) / ser.mean()).values
        merged['tod'] = merged['parsed_date'].dt.hour * 4 + merged['parsed_date'].dt.minute // 15
        clim = merged.dropna(subset=['solar_shape']).groupby(['month', 'tod'])['solar_shape'].mean()
        solar_years = sorted(merged.dropna(subset=['solar_shape'])['year'].unique().tolist())
        if len(clim):
            fill = pd.Series(list(zip(merged['month'], merged['tod']))).map(clim).values
            merged['solar_shape'] = merged['solar_shape'].fillna(pd.Series(fill, index=merged.index))
        merged['solar_shape'] = merged['solar_shape'].fillna(0.0)
        merged['solar_avail_mw_per_gw'] = merged['solar_shape'] * 1000.0 * SOLAR_CAPACITY_FACTOR
        if solar_years:
            print(f">> Solar profile from the 15-minute file for {solar_years[0]}-{solar_years[-1]}; "
                  f"other weather years use the average shape by month and time of day.")
        else:
            print(">> ! No solar data in the 15-minute file: solar output will be zero.")
        
        def get_annualized_twr(sub_df):
            # Scale each year to a full year using the days actually present in the file
            # (full years in the master file; a sample of days in older files).
            days_present = max(1, sub_df['parsed_date'].dt.normalize().nunique())
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
        DD_FILES[reg] = input_path(DD_FILES[reg])
        if not os.path.exists(DD_FILES[reg]):
            raise FileNotFoundError(f"'{DD_FILES[reg]}' is needed to fit the {reg} constraint model "
                                    f"(run build_all_island_dd.py first).")
        dd[reg] = load_dd_hourly(DD_FILES[reg])

    # Solar records, if available. dd_w keeps wind alone (for the availability checks and the
    # regional split); dd becomes wind + solar, which is what each region's limit is fitted to.
    dd_w = {reg: dd[reg].copy() for reg in REGIONS}
    dd_s = {}
    for reg in REGIONS:
        sp = input_path(SOLAR_DD_FILES[reg])
        if os.path.exists(sp):
            dd_s[reg] = load_dd_hourly(sp)
    solar_in_fit = len(dd_s) == len(REGIONS)
    if solar_in_fit:
        for reg in REGIONS:
            w = dd_w[reg].set_index('datetime')
            sol = dd_s[reg].set_index('datetime')[['avail_mw', 'cons_mw']]
            comb = w.join(sol, rsuffix='_solar', how='left').fillna({'avail_mw_solar': 0.0, 'cons_mw_solar': 0.0})
            comb['avail_mw'] = comb['avail_mw'] + comb['avail_mw_solar']
            comb['cons_mw'] = comb['cons_mw'] + comb['cons_mw_solar']
            dd[reg] = comb.reset_index()[['datetime', 'year', 'avail_mw', 'cons_mw']]
        print(">> Network limits are fitted to wind + solar (solar records found); solar shares each "
              "region's limit with wind.")
    else:
        print(">> ! Solar dispatch-down files not found: limits are fitted to wind only. Solar still "
              "shares the limit in the forecast. Run build_all_island_dd.py to create them.")
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
        print(f"{REGION_NAMES[reg]} ({reg}), {'wind + solar' if solar_in_fit else 'wind'}, "
              f"fitted separately for each year:")
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

    def backcast(reinforcement=None):
        """Run the forecast's starting model back over every historical year.

        Each region uses its forecast L and sigma. With reinforcement rate g, the limit in an
        earlier year t is L_fit * (1 + g) ** (t - t_fit), i.e. the scenario's trend run in
        reverse; g = 0 holds the limit at its fitted value. Each year is predicted from its own
        actual hourly availability, so the only thing being tested is the limit.
        """
        reinforcement = reinforcement or {}
        rows, by_year = [], {}
        for reg in REGIONS:
            p = cons_params[reg]
            ref = max(p['years'])
            g = reinforcement.get(reg, 0.0)
            for y in sorted(fit_years_avail[reg]):
                hy = dd[reg][dd[reg]['year'] == y]
                limit = p['limit_mw'] * (1.0 + g) ** (y - ref)
                pred = expected_constraint_mw(hy['avail_mw'].values, limit, p['sigma']).sum()
                act, av = hy['cons_mw'].sum(), hy['avail_mw'].sum()
                by_year.setdefault(y, []).append((act, pred, av, y in p['years']))
                rows.append({'Year': y, 'Label': year_label(reg, y), 'Region': reg,
                             'In_fit': y in p['years'], 'Limit_MW': round(limit),
                             'Actual_GWh': act / 1e3, 'Predicted_GWh': pred / 1e3,
                             'Actual_Cons_%': 100 * act / av, 'Predicted_Cons_%': 100 * pred / av})
        for y, parts in by_year.items():
            if len(parts) < len(REGIONS):
                continue
            act, pred, av = (sum(v[i] for v in parts) for i in range(3))
            rows.append({'Year': y, 'Label': year_label('IE', y), 'Region': 'All-island',
                         'In_fit': all(v[3] for v in parts), 'Limit_MW': np.nan,
                         'Actual_GWh': act / 1e3, 'Predicted_GWh': pred / 1e3,
                         'Actual_Cons_%': 100 * act / av, 'Predicted_Cons_%': 100 * pred / av})
        df = pd.DataFrame(rows)
        df['Error_%'] = np.where(df['Actual_GWh'] > 0, 100 * (df['Predicted_GWh'] / df['Actual_GWh'] - 1), np.nan)
        # Percentage-point error is easier to read when actual constraint was small.
        df['Error_pts'] = df['Predicted_Cons_%'] - df['Actual_Cons_%']
        order = {r: i for i, r in enumerate(REGIONS + ['All-island'])}
        df = df.sort_values(['Year', 'Region'], key=lambda c: c.map(order) if c.name == 'Region' else c)
        return df.reset_index(drop=True)

    def backcast_error_summary(df):
        """Mean absolute and mean signed error, for out-of-fit years and for all years."""
        out = {}
        for reg in REGIONS + ['All-island']:
            sub = df[df['Region'] == reg]
            oos = sub.loc[~sub['In_fit'], 'Error_%'].dropna()
            oos_pts = sub.loc[~sub['In_fit'], 'Error_pts'].dropna()
            allv = sub['Error_%'].dropna()
            out[reg] = {'oos_mae': oos.abs().mean() if len(oos) else np.nan,
                        'oos_bias': oos.mean() if len(oos) else np.nan, 'oos_n': len(oos),
                        'oos_mae_pts': oos_pts.abs().mean() if len(oos_pts) else np.nan,
                        'oos_bias_pts': oos_pts.mean() if len(oos_pts) else np.nan,
                        'all_mae': allv.abs().mean() if len(allv) else np.nan}
        return out

    def print_backcast(df, title):
        show = df.copy()
        show['Fit'] = np.where(show['In_fit'], 'fit', '')
        show['Limit_MW'] = show['Limit_MW'].map(lambda v: '' if pd.isna(v) else f"{v:.0f}")
        for c in ['Actual_GWh', 'Predicted_GWh']:
            show[c] = show[c].round(0).astype(int)
        for c in ['Actual_Cons_%', 'Predicted_Cons_%', 'Error_%', 'Error_pts']:
            show[c] = show[c].round(1 if c == 'Error_%' else 2)
        print(title)
        print(show[['Label', 'Region', 'Fit', 'Limit_MW', 'Actual_GWh', 'Predicted_GWh', 'Error_%',
                    'Actual_Cons_%', 'Predicted_Cons_%', 'Error_pts']].rename(columns={'Label': 'Year'}).to_string(index=False))
        print("Backcast error over years outside the fit (fit years match only in total, by construction):")
        for reg, e in backcast_error_summary(df).items():
            if e['oos_n']:
                print(f"   {reg:<10} typical error ±{e['oos_mae']:.1f}% (±{e['oos_mae_pts']:.1f} pts), "
                      f"bias {e['oos_bias']:+.1f}% ({e['oos_bias_pts']:+.1f} pts) over {e['oos_n']} years")

    baseline_backcast = backcast()
    print()
    print_backcast(baseline_backcast, "Backcast with the forecast's starting limits held fixed (0% reinforcement):")
    print(">> A positive bias means the starting limits are tighter than the network was in those "
          "years, i.e. the network has tightened since; negative means it has loosened.")
    baseline_errors = backcast_error_summary(baseline_backcast)
    try:
        bc_path = os.path.join(SCENARIO_OUTPUT_DIR, "backcast_results.csv")
        baseline_backcast.round(3).to_csv(bc_path, index=False)
        print(f">> Saved to '{bc_path}'")
    except OSError as e:
        print(f">> Could not save backcast_results.csv: {e}")

    common_years = sorted(set(full_years['IE']) & set(full_years['NI']))
    share_year = common_years[-1]
    av_ie = dd_w['IE'].loc[dd_w['IE']['year'] == share_year, 'avail_mw'].sum()
    av_ni = dd_w['NI'].loc[dd_w['NI']['year'] == share_year, 'avail_mw'].sum()
    base_ie_share = float(av_ie / (av_ie + av_ni))
    print(f">> {share_year} wind availability split: IE {100 * base_ie_share:.1f}% / NI {100 * (1 - base_ie_share):.1f}%")

    # Solar: regional split and 2026 installed capacity, from the last 12 months of solar records.
    if dd_s:
        recent = {}
        for reg in REGIONS:
            if reg in dd_s:
                d_ = dd_s[reg].sort_values('datetime')
                d_ = d_[d_['datetime'] > d_['datetime'].max() - pd.Timedelta(days=365)]
                recent[reg] = d_['avail_mw'].mean()          # average MW over the last 12 months
            else:
                recent[reg] = 0.0
        tot = sum(recent.values())
        base_solar_ie_share = float(recent['IE'] / tot) if tot > 0 else 0.85
        est_solar_gw = tot / 1000.0 / SOLAR_CAPACITY_FACTOR
    else:
        base_solar_ie_share, est_solar_gw = 0.85, None
    if SOLAR_CAPACITY_2026_GW is not None:
        solar_capacity_2026_gw = float(SOLAR_CAPACITY_2026_GW)
        solar_cap_note = "set in SOLAR_CAPACITY_2026_GW"
    elif est_solar_gw:
        solar_capacity_2026_gw = est_solar_gw
        solar_cap_note = (f"estimated from the last 12 months of solar availability at a "
                          f"{100 * SOLAR_CAPACITY_FACTOR:.0f}% capacity factor")
    else:
        solar_capacity_2026_gw = SOLAR_CAPACITY_FALLBACK_GW
        solar_cap_note = "! no solar records, using SOLAR_CAPACITY_FALLBACK_GW; set SOLAR_CAPACITY_2026_GW"
    print(f">> Solar 2026: {solar_capacity_2026_gw:.2f} GW installed ({solar_cap_note}); "
          f"split IE {100 * base_solar_ie_share:.1f}% / NI {100 * (1 - base_solar_ie_share):.1f}%")

    ai_hourly = (dd_w['IE'].set_index('datetime')['avail_mw']
                 .add(dd_w['NI'].set_index('datetime')['avail_mw'], fill_value=0.0)
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
        if not (1 / (1 + MAX_AVAILABILITY_MISMATCH)) <= avail_basis_ratio <= (1 + MAX_AVAILABILITY_MISMATCH):
            raise ValueError(
                f"Wind availability in '{csv_file}' is {1 / avail_basis_ratio:.2f}x the IE + NI "
                f"dispatch-down availability for the same hours. The forecast scales this series, so "
                f"it must be all-island wind on the same basis. Check that sem_wind_availability "
                f"covers IE + NI (or raise MAX_AVAILABILITY_MISMATCH if the difference is intended).")
    else:
        avail_basis_ratio = 1.0
        print(">> Warning: too few shared hours to compare the two availability series; assuming the same basis.")

    def regional_constraint_mw(wind_mw, limits, ie_share, solar_mw=None, solar_ie_share=None):
        """Expected constrained MW in each region, split between wind and solar.

        Each region's wind (on the dispatch-down basis) and solar share one limit. The region's
        total expected constraint is shared between them in proportion to their available output.
        Returns {region: {'wind': MW, 'solar': MW}} on the 15-minute file's basis.
        """
        wind = np.asarray(wind_mw, dtype=float) * avail_basis_ratio
        solar = np.zeros_like(wind) if solar_mw is None else np.asarray(solar_mw, dtype=float)
        s_ie = base_solar_ie_share if solar_ie_share is None else solar_ie_share
        w_sh = {'IE': ie_share, 'NI': 1.0 - ie_share}
        s_sh = {'IE': s_ie, 'NI': 1.0 - s_ie}
        out = {}
        for reg in REGIONS:
            p = cons_params[reg]
            w_r, s_r = wind * w_sh[reg], solar * s_sh[reg]
            x = w_r + s_r
            total = expected_constraint_mw(x, limits[reg], p['sigma'], p['calib'])
            frac_w = np.divide(w_r, x, out=np.ones_like(x), where=x > 0)
            out[reg] = {'wind': total * frac_w / avail_basis_ratio, 'solar': total * (1.0 - frac_w)}
        return out

    def dispatch(wind, solar, demand, limits, ie_share, solar_ie_share, snsp_fraction,
                 storage_power_mw=0.0, storage_energy_mwh=0.0,
                 charge_efficiency=DEFAULT_STORAGE_CHARGE_EFFICIENCY,
                 discharge_efficiency=DEFAULT_STORAGE_DISCHARGE_EFFICIENCY,
                 initial_soc_pct=DEFAULT_STORAGE_INITIAL_SOC_PCT,
                 muon_floor_mw=MUON_FLOOR_MW):
        """Chronological 15-minute dispatch for wind, solar and non-hybrid storage.

        Order of operations:
        1. Apply regional network constraints to wind + solar.
        2. Apply the lower of the SNSP ceiling and the MUON/minimum-generation ceiling.
        3. Charge standalone storage only from the resulting operational curtailment.
        4. Discharge later to demand, while respecting the same non-synchronous ceiling.

        Storage never absorbs network-constrained energy. Constraint and operational
        curtailment are allocated between wind and solar in proportion to output.
        """
        wind = np.asarray(wind, dtype=float)
        solar = np.asarray(solar, dtype=float)
        demand = np.asarray(demand, dtype=float)
        reg = regional_constraint_mw(wind, limits, ie_share, solar, solar_ie_share)
        con_w = sum(reg[r]['wind'] for r in REGIONS)
        con_s = sum(reg[r]['solar'] for r in REGIONS)
        post_w = np.maximum(0.0, wind - con_w)
        post_s = np.maximum(0.0, solar - con_s)
        post = post_w + post_s

        snsp_ceiling = demand * snsp_fraction
        muon_ceiling = np.maximum(0.0, demand - muon_floor_mw)
        operational_limit = np.minimum(snsp_ceiling, muon_ceiling)
        potential_curt = np.maximum(0.0, post - operational_limit)
        direct_res = post - potential_curt

        n = len(post)
        charge_mw = np.zeros(n)
        discharge_mw = np.zeros(n)
        soc_mwh = np.zeros(n)
        remaining_curt = np.zeros(n)
        e_cap = max(0.0, float(storage_energy_mwh))
        p_cap = max(0.0, float(storage_power_mw))
        soc = e_cap * np.clip(float(initial_soc_pct) / 100.0, 0.0, 1.0)
        eta_c = np.clip(float(charge_efficiency), 1e-9, 1.0)
        eta_d = np.clip(float(discharge_efficiency), 1e-9, 1.0)

        for i in range(n):
            # Non-hybrid charging source is operational curtailment only.
            max_charge_from_space_mw = (e_cap - soc) / (INTERVAL_HOURS * eta_c) if e_cap > soc else 0.0
            ch = min(potential_curt[i], p_cap, max_charge_from_space_mw)
            charge_mw[i] = max(0.0, ch)
            soc += charge_mw[i] * INTERVAL_HOURS * eta_c
            remaining_curt[i] = potential_curt[i] - charge_mw[i]

            # Inverter discharge is also non-synchronous, so it cannot push total
            # non-synchronous output above the shared SNSP/MUON operational limit.
            demand_gap = max(0.0, demand[i] - direct_res[i])
            operational_headroom = max(0.0, operational_limit[i] - direct_res[i])
            max_discharge_from_soc_mw = soc * eta_d / INTERVAL_HOURS
            dis = min(demand_gap, operational_headroom, p_cap, max_discharge_from_soc_mw)
            discharge_mw[i] = max(0.0, dis)
            soc -= discharge_mw[i] * INTERVAL_HOURS / eta_d
            soc = min(e_cap, max(0.0, soc))
            soc_mwh[i] = soc

        frac_w = np.divide(post_w, post, out=np.ones_like(post), where=post > 0)
        curt_w = remaining_curt * frac_w
        curt_s = remaining_curt * (1.0 - frac_w)
        usable_w = post_w - potential_curt * frac_w
        usable_s = post_s - potential_curt * (1.0 - frac_w)
        # Charging recovers curtailed renewable energy but does not turn it into
        # direct wind/solar output. Discharge is reported separately.
        return {'reg': reg, 'con_w': con_w, 'con_s': con_s,
                'curt_w': curt_w, 'curt_s': curt_s,
                'usable_w': usable_w, 'usable_s': usable_s,
                'potential_curt_mw': potential_curt,
                'charge_mw': charge_mw, 'discharge_mw': discharge_mw,
                'soc_mwh': soc_mwh, 'operational_limit_mw': operational_limit,
                'storage_losses_mwh': (charge_mw.sum() * INTERVAL_HOURS -
                                       discharge_mw.sum() * INTERVAL_HOURS -
                                       (soc_mwh[-1] - e_cap * np.clip(initial_soc_pct / 100.0, 0.0, 1.0))
                                       if n else 0.0)}

    def interactive_scenario():
        """Ask for the scenario inputs (used when there is no scenarios.csv)."""
        print("\n(No scenarios.xlsx found: running one scenario from prompts.)")
        return {
            'scenario': 'interactive',
            'build_rate_wind_ie': ask_float("Enter annual WIND build-out rate in IE/ROI, GW/year",
                                            round(DEFAULT_BUILD_RATE_GW * base_ie_share, 3)),
            'build_rate_wind_ni': ask_float("Enter annual WIND build-out rate in NI, GW/year",
                                            round(DEFAULT_BUILD_RATE_GW * (1 - base_ie_share), 3)),
            'build_rate_solar_ie': ask_float("Enter annual SOLAR build-out rate in IE/ROI, GW/year",
                                             round(DEFAULT_SOLAR_BUILD_RATE_GW * base_solar_ie_share, 3)),
            'build_rate_solar_ni': ask_float("Enter annual SOLAR build-out rate in NI, GW/year",
                                             round(DEFAULT_SOLAR_BUILD_RATE_GW * (1 - base_solar_ie_share), 3)),
            'snsp_limit_pct': ask_float("Enter System Non-Synchronous Penetration (SNSP) Limit %", DEFAULT_SNSP_PCT),
            'muon_units_ie': ask_float("Enter IE MUON units online", DEFAULT_MUON_UNITS_IE),
            'muon_units_ni': ask_float("Enter NI MUON units online", DEFAULT_MUON_UNITS_NI),
            'storage_power_build_rate_mw': ask_float("Enter annual standalone storage power build rate, MW/year", 0.0),
            'storage_energy_build_rate_mwh': ask_float("Enter annual standalone storage energy build rate, MWh/year", 0.0),
            'storage_power_2026_mw': ask_float("Enter installed standalone storage power in 2026, MW", 0.0),
            'storage_energy_2026_mwh': ask_float("Enter installed standalone storage energy in 2026, MWh", 0.0),
            'storage_charge_efficiency': ask_float("Enter storage charge efficiency (0-1)", DEFAULT_STORAGE_CHARGE_EFFICIENCY),
            'storage_discharge_efficiency': ask_float("Enter storage discharge efficiency (0-1)", DEFAULT_STORAGE_DISCHARGE_EFFICIENCY),
            'storage_initial_soc_pct': ask_float("Enter initial battery state of charge (%)", DEFAULT_STORAGE_INITIAL_SOC_PCT),
            'ie_reinforcement_pct': ask_float("Enter IE network reinforcement rate (% change in its effective "
                                              "limit per year; 0 = none, negative = continued tightening)", 0.0),
            'ni_reinforcement_pct': ask_float("Enter NI network reinforcement rate (% change in its effective "
                                              "limit per year; 0 = none, negative = continued tightening)", 0.0),
        }

    BUILD_COLUMNS = ['build_rate_wind_ie', 'build_rate_wind_ni', 'build_rate_solar_ie', 'build_rate_solar_ni']

    def load_scenarios(path):
        """Read scenarios.xlsx; blank cells take the defaults.

        Headers are matched ignoring case, spaces, hyphens and underscores, so "Build rate_WIND_IE",
        "Build Rate WIND IE" and "build_rate_wind_ie" are all the same column. Files in the old
        format (build_rate_gw + new_build_ie_pct, solar_build_rate_gw + solar_new_build_ie_pct) are
        converted to the four regional build rates rather than ignored.
        """
        extension = os.path.splitext(path)[1].lower()
        if extension in ('.xlsx', '.xlsm', '.xls'):
            table = pd.read_excel(path, sheet_name=SCENARIO_SHEET)
        elif extension == '.csv':
            table = pd.read_csv(path, encoding='utf-8-sig')
        else:
            raise ValueError(f"Unsupported scenario input '{path}'. Use .xlsx or .csv.")
        key = lambda c: re.sub(r'[^a-z0-9]', '', str(c).lower())
        known = BUILD_COLUMNS + ['scenario', 'snsp_limit_pct', 'muon_units_ie', 'muon_units_ni', 'ie_reinforcement_pct', 'ni_reinforcement_pct',
                                 'description', 'storage_power_build_rate_mw', 'storage_energy_build_rate_mwh',
                                 'storage_power_2026_mw', 'storage_energy_2026_mwh',
                                 'storage_charge_efficiency', 'storage_discharge_efficiency', 'storage_initial_soc_pct',
                                 'wind_build_rate_gw', 'build_rate_gw', 'demand_rate_twh_per_year', 'units',
                                 'new_build_ie_pct', 'solar_build_rate_gw',
                                 'solar_new_build_ie_pct']
        lookup = {key(k): k for k in known}
        table.columns = [lookup.get(key(c), str(c).strip()) for c in table.columns]
        unknown = [c for c in table.columns if c not in known]
        if unknown:
            print(f"   ! scenarios.csv columns not recognised and ignored: {unknown}")

        new_cols = [c for c in BUILD_COLUMNS if c in table.columns]
        old_format = not new_cols and ('wind_build_rate_gw' in table.columns or 'build_rate_gw' in table.columns or 'solar_build_rate_gw' in table.columns)
        print(f">> Scenario build-rate columns found: "
              f"{new_cols if new_cols else ('old format (converted)' if old_format else 'none (defaults used)')}")
        if old_format:
            print("   ! Old-format scenario inputs: converting build_rate_gw / new_build_ie_pct and "
                  "solar_build_rate_gw / solar_new_build_ie_pct to the four regional build rates.")

        def val(row, col, default):
            v = row.get(col, np.nan)
            return float(default) if pd.isna(v) or str(v).strip() == '' else float(v)

        defaults = {'build_rate_wind_ie': DEFAULT_BUILD_RATE_GW * base_ie_share,
                    'build_rate_wind_ni': DEFAULT_BUILD_RATE_GW * (1 - base_ie_share),
                    'build_rate_solar_ie': DEFAULT_SOLAR_BUILD_RATE_GW * base_solar_ie_share,
                    'build_rate_solar_ni': DEFAULT_SOLAR_BUILD_RATE_GW * (1 - base_solar_ie_share),
                    'demand_rate_twh_per_year': DEFAULT_DEMAND_RATE_TWH_PER_YEAR,
                    'snsp_limit_pct': DEFAULT_SNSP_PCT,
                    'muon_units_ie': DEFAULT_MUON_UNITS_IE,
                    'muon_units_ni': DEFAULT_MUON_UNITS_NI,
                    'storage_power_build_rate_mw': DEFAULT_STORAGE_POWER_BUILD_RATE_MW,
                    'storage_energy_build_rate_mwh': DEFAULT_STORAGE_ENERGY_BUILD_RATE_MWH,
                    'storage_power_2026_mw': DEFAULT_STORAGE_POWER_2026_MW,
                    'storage_energy_2026_mwh': DEFAULT_STORAGE_ENERGY_2026_MWH,
                    'storage_charge_efficiency': DEFAULT_STORAGE_CHARGE_EFFICIENCY,
                    'storage_discharge_efficiency': DEFAULT_STORAGE_DISCHARGE_EFFICIENCY,
                    'storage_initial_soc_pct': DEFAULT_STORAGE_INITIAL_SOC_PCT,
                    'ie_reinforcement_pct': 0.0, 'ni_reinforcement_pct': 0.0}
        scenarios = []
        for i, row in table.iterrows():
            name = str(row.get('scenario', '')).strip()
            if name.lower() in ('[text]', 'units', '[units]'):
                continue
            if not name or name.lower() == 'nan':
                name = f"scenario_{i + 1}"
            sc = {'scenario': re.sub(r'[^A-Za-z0-9_.-]+', '_', name)}
            for k, default in defaults.items():
                sc[k] = val(row, k, default)
            if old_format:
                w = val(row, 'wind_build_rate_gw', val(row, 'build_rate_gw', DEFAULT_BUILD_RATE_GW))
                w_ie = val(row, 'new_build_ie_pct', 100 * base_ie_share) / 100.0
                so = val(row, 'solar_build_rate_gw', DEFAULT_SOLAR_BUILD_RATE_GW)
                s_ie = val(row, 'solar_new_build_ie_pct', 100 * base_solar_ie_share) / 100.0
                sc.update({'build_rate_wind_ie': w * w_ie, 'build_rate_wind_ni': w * (1 - w_ie),
                           'build_rate_solar_ie': so * s_ie, 'build_rate_solar_ni': so * (1 - s_ie)})
            sc['description'] = '' if pd.isna(row.get('description', np.nan)) else str(row.get('description'))
            scenarios.append(sc)
        return scenarios

    backcast_store = {}   # scenario name -> (backcast table, error summary)

    def run_scenario(sc, out_dir, make_charts=True):
        # The 2026 weather-completion step updates the merged 15-minute frame
        # defined in run_demonstrator(). Declaring it nonlocal prevents Python
        # from treating merged as an uninitialised local variable here.
        nonlocal merged
        os.makedirs(out_dir, exist_ok=True)
        # Use the unique scenario identifier from the scenario input workbook in
        # every plot filename and title. load_scenarios() has already converted
        # spaces and filename-unsafe characters to underscores.
        scenario_name = str(sc['scenario'])

        def scenario_plot_filename(suffix):
            return f"{scenario_name}_{suffix}"

        def scenario_plot_title(title):
            return f"{scenario_name} | {title}"

        def capacity_box_line(year):
            row = sim_df.loc[sim_df['Year'] == year].iloc[0]
            battery_gwh = float(row['Storage_Energy_MWh']) / 1000.0
            return (f"Installed: Wind {row['Wind_Cap_GW']:.2f} GW | "
                    f"Solar {row['Solar_Cap_GW']:.2f} GW\n"
                    f"Battery: {row['Storage_Power_MW']:.0f} MW / {battery_gwh:.2f} GWh")

        def renewables_including_storage_pct(year):
            row = sim_df.loc[sim_df['Year'] == year].iloc[0]
            delivered = float(row['Wind_Gen_TWh']) + float(row['Solar_Gen_TWh']) + float(row['Storage_Discharge_TWh'])
            return 100.0 * delivered / float(row['Dem_TWh']) if float(row['Dem_TWh']) > 0 else 0.0
        # 3. Decarbonisation Demand, Build Rate & SNSP User Prompts
        print("\n====================================================================")
        print(f" 3. SCENARIO '{sc['scenario']}': DEMAND, BUILD-RATE & SNSP CONFIGURATION")
        print("====================================================================")
        start_year = 2026
        final_year = 2050
        hzn = final_year - start_year
    
        # The 2026 baseline uses a full-year estimate derived from 2025 because
        # the 2026 15-minute series is incomplete. A fixed 0.9 TWh increase is
        # used for 2026; scenario demand growth applies from 2027 onward.
        demand_2025 = master_hist.loc[master_hist['year'] == 2025, 'Demand_TWh'].dropna()
        if demand_2025.empty:
            completed = master_hist.loc[master_hist['year'] < 2026, ['year', 'Demand_TWh']].dropna()
            if completed.empty:
                raise ValueError("No completed pre-2026 demand year is available for the 2026 baseline.")
            demand_2025_twh = float(completed.sort_values('year').iloc[-1]['Demand_TWh'])
        else:
            demand_2025_twh = float(demand_2025.iloc[0])
        annual_demand_growth_rate = float(sc['demand_rate_twh_per_year'])

        # 2026 is a transition year before the assumed decarbonisation and
        # electrification trajectory begins. Use a fixed 0.9 TWh increase over
        # the 2025 actual demand. The scenario-specific annual demand rate then
        # applies from 2027 onward.
        demand_increase_2026_twh = 0.9
        base_demand_twh = demand_2025_twh + demand_increase_2026_twh
        tot_demand_2050 = base_demand_twh + (hzn * annual_demand_growth_rate)
    
        # Build rates by technology and region (GW/yr). The model uses the total per technology
        # and the IE share of it, which sets where the new capacity connects.
        bw_ie, bw_ni = max(0.0, float(sc['build_rate_wind_ie'])), max(0.0, float(sc['build_rate_wind_ni']))
        bs_ie, bs_ni = max(0.0, float(sc['build_rate_solar_ie'])), max(0.0, float(sc['build_rate_solar_ni']))
        annual_build_rate_gw = bw_ie + bw_ni
        snsp_limit_pct = float(sc['snsp_limit_pct'])
        snsp_limit_fraction = snsp_limit_pct / 100.0
        muon_units_ie = max(0, int(round(float(sc['muon_units_ie']))))
        muon_units_ni = max(0, int(round(float(sc['muon_units_ni']))))
        muon_floor_mw = (muon_units_ie + muon_units_ni) * MUON_MIN_GEN_PER_UNIT_MW
        storage_power_build_rate_mw = max(0.0, float(sc['storage_power_build_rate_mw']))
        storage_energy_build_rate_mwh = max(0.0, float(sc['storage_energy_build_rate_mwh']))
        storage_power_2026_mw = max(0.0, float(sc['storage_power_2026_mw']))
        storage_energy_2026_mwh = max(0.0, float(sc['storage_energy_2026_mwh']))
        storage_charge_efficiency = np.clip(float(sc['storage_charge_efficiency']), 1e-9, 1.0)
        storage_discharge_efficiency = np.clip(float(sc['storage_discharge_efficiency']), 1e-9, 1.0)
        storage_initial_soc_pct = np.clip(float(sc['storage_initial_soc_pct']), 0.0, 100.0)
        reinforcement_rate = {'IE': float(sc['ie_reinforcement_pct']) / 100.0,
                              'NI': float(sc['ni_reinforcement_pct']) / 100.0}
        new_build_ie_share = bw_ie / annual_build_rate_gw if annual_build_rate_gw > 0 else base_ie_share
        solar_build_rate_gw = bs_ie + bs_ni
        solar_new_build_ie_share = bs_ie / solar_build_rate_gw if solar_build_rate_gw > 0 else base_solar_ie_share

        print(f"\n>> Baseline Demand (2026): {base_demand_twh:.2f} TWh")
        print(f">> 2026 Demand Increase over 2025: {demand_increase_2026_twh:.2f} TWh")
        print(f">> Scenario Demand Growth Rate from 2027: {annual_demand_growth_rate:.2f} TWh/year")
        print(f">> Projected Total Demand in {final_year}: {tot_demand_2050:.2f} TWh")
        print(f">> Wind build-out: IE {bw_ie:.3f} + NI {bw_ni:.3f} = {annual_build_rate_gw:.3f} GW/year")
        print(f">> Solar build-out: IE {bs_ie:.3f} + NI {bs_ni:.3f} = {solar_build_rate_gw:.3f} GW/year")
        print(f">> Capacity: 6.51 GW in 2026, adding {annual_build_rate_gw:.3f} GW each year from 2027")
        print(f">> Selected Forecast Operational SNSP Limit: {snsp_limit_pct:.1f}%")
        print(f">> MUON floor: IE {muon_units_ie} + NI {muon_units_ni} units x "
              f"{MUON_MIN_GEN_PER_UNIT_MW:.0f} MW = {muon_floor_mw:.0f} MW SEM")
        print(f">> Standalone storage in 2026: {storage_power_2026_mw:.0f} MW / {storage_energy_2026_mwh:.0f} MWh")
        print(f">> Storage build-out: {storage_power_build_rate_mw:.0f} MW/yr and {storage_energy_build_rate_mwh:.0f} MWh/yr")
        print(">> Storage is non-hybrid: it charges from operational curtailment only, never grid constraint.")
        for reg in REGIONS:
            steps = REINFORCEMENT_STEPS_MW.get(reg, {})
            no_reinf = reinforcement_rate[reg] == 0 and not steps
            print(f">> {reg} Network Reinforcement: {100 * reinforcement_rate[reg]:.1f}%/yr on a "
                  f"{cons_params[reg]['limit_mw']:.0f} MW effective limit"
                  + (f", plus steps {steps}" if steps else "")
                  + (" (no reinforcement: upper bound)" if no_reinf else ""))
        print(f">> Solar: {solar_capacity_2026_gw:.2f} GW in 2026, adding {solar_build_rate_gw:.3f} GW each year "
              f"from 2027, capacity factor {100 * SOLAR_CAPACITY_FACTOR:.0f}%")

        # 4. Weather-Loop Simulation & Loss Scaling Forecast
        print("\n====================================================================")
        print(" 4. WEATHER-LOOP SIMULATION & LOSS SCALING FORECAST (2026 - 2050)")
        print("====================================================================")
        base_capacity_gw = final_2026_wind_capacity_gw
    
        simulation_years = list(range(2026, 2051))
        sim_results = []
        # Complete October-December 2026 using explicit all-island SEM monthly
        # wind-generation forecasts. No 2020 wind-volume assumption is used.
        # The 2025 quarter-hour profile supplies only the intramonth shape; each
        # month is rescaled to the specified 2026 SEM energy total.
        wind_generation_forecast_2026_gwh = {10: 1500.0, 11: 1500.0, 12: 1800.0}
        shape_reference_year_2026 = 2025
        actual_2026 = merged.loc[merged['year'] == 2026].copy()
        reference_shape = merged.loc[merged['year'] == shape_reference_year_2026].copy()
        if actual_2026.empty:
            raise ValueError("No 2026 SEM intervals were detected in sem_demand_wind_solar_master.csv.")
        if reference_shape.empty:
            raise ValueError("The 2025 shape reference is unavailable in the master CSV.")

        reference_shape['weather_key'] = reference_shape['parsed_date'].dt.strftime('%m-%d %H:%M')
        actual_2026['weather_key'] = actual_2026['parsed_date'].dt.strftime('%m-%d %H:%M')
        actual_keys_2026 = set(actual_2026['weather_key'])
        missing_2026 = reference_shape.loc[
            reference_shape['month'].isin(wind_generation_forecast_2026_gwh)
            & ~reference_shape['weather_key'].isin(actual_keys_2026)
        ].copy()
        missing_2026['parsed_date'] = pd.to_datetime(
            '2026-' + missing_2026['weather_key'], format='%Y-%m-%d %H:%M', errors='coerce')
        missing_2026['year'] = 2026
        missing_2026['month'] = missing_2026['parsed_date'].dt.month
        missing_2026['day'] = missing_2026['parsed_date'].dt.day
        missing_2026['tod'] = missing_2026['parsed_date'].dt.hour * 4 + missing_2026['parsed_date'].dt.minute // 15
        missing_2026['Weather_Data_Source'] = '2026 fixed monthly SEM wind forecast; 2025 intramonth shape'
        actual_2026['Weather_Data_Source'] = '2026 SEM actual'

        # Build each missing month's quarter-hour wind shape robustly. Some
        # historical files contain zero wind-generation values even though wind
        # availability is present. Prefer the 2025 generation shape when usable;
        # otherwise use the 2025 availability shape. The selected shape is then
        # normalised to the explicit SEM monthly generation target.
        actual_gen_sum = actual_2026['sem_wind_generation'].clip(lower=0).sum()
        actual_avail_sum = actual_2026['sem_wind_availability'].clip(lower=0).sum()
        availability_to_generation_ratio = (
            actual_avail_sum / actual_gen_sum if actual_gen_sum > 0 else 1.0
        )
        availability_to_generation_ratio = max(1.0, availability_to_generation_ratio)

        for month, target_gwh in wind_generation_forecast_2026_gwh.items():
            actual_month_gwh = (
                actual_2026.loc[actual_2026['month'] == month, 'sem_wind_generation']
                .clip(lower=0).sum() * INTERVAL_HOURS / 1000.0
            )
            remaining_target_gwh = max(0.0, target_gwh - actual_month_gwh)
            mask = missing_2026['month'] == month

            generation_shape = missing_2026.loc[mask, 'sem_wind_generation'].clip(lower=0)
            availability_shape = missing_2026.loc[mask, 'sem_wind_availability'].clip(lower=0)
            if generation_shape.sum() > 0:
                shape = generation_shape
                shape_source = '2025 wind generation'
            elif availability_shape.sum() > 0:
                shape = availability_shape
                shape_source = '2025 wind availability'
            else:
                # Final fallback keeps the requested monthly total even when the
                # reference month has no usable wind values. It creates a flat
                # quarter-hour profile rather than aborting the whole run.
                shape = pd.Series(1.0, index=missing_2026.index[mask])
                shape_source = 'flat fallback'

            target_mwh = remaining_target_gwh * 1000.0
            profile_mw = shape / shape.sum() * target_mwh / INTERVAL_HOURS if shape.sum() > 0 else 0.0
            missing_2026.loc[mask, 'sem_wind_generation'] = np.asarray(profile_mw)
            missing_2026.loc[mask, 'sem_wind_availability'] = (
                np.asarray(profile_mw) * availability_to_generation_ratio
            )
            print(f">> 2026 month {month:02d} shape source: {shape_source}; "
                  f"availability/generation ratio {availability_to_generation_ratio:.3f}.")

        completed_2026 = pd.concat([actual_2026, missing_2026], ignore_index=True, sort=False)
        completed_2026 = completed_2026.sort_values('parsed_date').drop_duplicates('parsed_date', keep='first')
        merged['Weather_Data_Source'] = np.where(merged['year'] == 2026, '2026 SEM actual', 'Historical actual')
        merged = pd.concat([merged.loc[merged['year'] != 2026], completed_2026], ignore_index=True, sort=False)
        merged = merged.sort_values('parsed_date').reset_index(drop=True)

        print(f">> 2026 SEM completion: {len(actual_2026):,} actual intervals + {len(missing_2026):,} forecast intervals.")
        for month, target_gwh in wind_generation_forecast_2026_gwh.items():
            realised = (merged.loc[(merged['year'] == 2026) & (merged['month'] == month),
                                   'sem_wind_generation'].sum()
                        * INTERVAL_HOURS / 1000.0)
            print(f">> 2026 month {month:02d} SEM wind generation: {realised:.2f} GWh (target {target_gwh:.2f}).")

        # Recalculate the normalised availability after inserting the forecast
        # intervals. Actual Jan-Sep uses the current September fleet; the added
        # Oct-Dec intervals use the forecast final 2026 all-island capacity.
        actual_current_gw = float(capacity_row_for_year(2026, prefer_final=False)['Total_MW']) / 1000.0
        is_forecast_fill = merged['Weather_Data_Source'].eq(
            '2026 fixed monthly SEM wind forecast; 2025 intramonth shape')
        merged.loc[(merged['year'] == 2026) & ~is_forecast_fill, 'installed_gw'] = actual_current_gw
        merged.loc[(merged['year'] == 2026) & is_forecast_fill, 'installed_gw'] = final_2026_wind_capacity_gw
        merged['spec_avail_mw_per_gw'] = merged['sem_wind_availability'] / merged['installed_gw']

        complete_weather_years = sorted([int(y) for y in merged['year'].unique() if y <= 2026])

        # The forecast model is all-island SEM: demand, wind generation, wind
        # availability, installed capacity, wind share and fleet CF all use SEM totals.
        def capacity_for_year(year):
            """Installed capacity: 2026 baseline, then one full build increment per year from 2027."""
            return base_capacity_gw + max(0, year - start_year) * annual_build_rate_gw

        def region_limits(year):
            return {reg: limit_for_year(cons_params[reg], year, reinforcement_rate[reg],
                                        REINFORCEMENT_STEPS_MW.get(reg, {}))
                    for reg in REGIONS}

        def ie_share_for_capacity(cap_gw):
            """IE share of all-island availability: today's split for the existing fleet,
            the IE/NI build rates for capacity added after 2026."""
            added = max(0.0, cap_gw - base_capacity_gw)
            return (base_ie_share * base_capacity_gw + new_build_ie_share * added) / cap_gw

        def solar_capacity_for_year(year):
            return solar_capacity_2026_gw + max(0, year - start_year) * solar_build_rate_gw
        def storage_for_year(year):
            elapsed = max(0, year - start_year)
            return (storage_power_2026_mw + elapsed * storage_power_build_rate_mw,
                    storage_energy_2026_mwh + elapsed * storage_energy_build_rate_mwh)

        def solar_ie_share_for_capacity(cap_gw):
            if cap_gw <= 0:
                return base_solar_ie_share
            added = max(0.0, cap_gw - solar_capacity_2026_gw)
            return (base_solar_ie_share * solar_capacity_2026_gw + solar_new_build_ie_share * added) / cap_gw

        def run_weather_years(cap_gw, demand_twh, limits, snsp_fraction, solar_gw,
                              storage_power_mw, storage_energy_mwh, weather_years=None):
            """Run selected SEM weather years and average their annual results."""
            ie_share = ie_share_for_capacity(cap_gw)
            s_ie = solar_ie_share_for_capacity(solar_gw)
            rows = []
            selected_weather_years = complete_weather_years if weather_years is None else list(weather_years)
            for wy in selected_weather_years:
                df_wy = merged[merged['year'] == wy]
                avail = df_wy['spec_avail_mw_per_gw'].values * cap_gw
                solar = df_wy['solar_avail_mw_per_gw'].values * solar_gw
                hist_avg = df_wy['sem_demand'].mean()
                demand = df_wy['sem_demand'].values * ((demand_twh * 1e6 / 8760.0) / hist_avg if hist_avg > 0 else 1.0)

                d = dispatch(avail, solar, demand, limits, ie_share, s_ie, snsp_fraction,
                             storage_power_mw, storage_energy_mwh,
                             storage_charge_efficiency, storage_discharge_efficiency,
                             storage_initial_soc_pct, muon_floor_mw=muon_floor_mw)
                reg_w = {r: d['reg'][r]['wind'] for r in REGIONS}
                reg_s = {r: d['reg'][r]['solar'] for r in REGIONS}

                tot_av = avail.sum()
                tot_sv = solar.sum()
                if tot_av <= 0:
                    continue
                to_annual_twh = 0.25 / 1e6 * (365.25 / (len(avail) / 96.0))
                sv = tot_sv if tot_sv > 0 else np.nan
                rows.append({
                    'avail_twh': tot_av * to_annual_twh,
                    'dispatch_twh': d['usable_w'].sum() * to_annual_twh,
                    'curt_pct': 100 * d['curt_w'].sum() / tot_av,
                    'cons_pct': 100 * d['con_w'].sum() / tot_av,
                    'IE_pts': 100 * reg_w['IE'].sum() / tot_av,
                    'NI_pts': 100 * reg_w['NI'].sum() / tot_av,
                    'IE_own_pct': 100 * reg_w['IE'].sum() / (tot_av * ie_share) if ie_share > 0 else 0.0,
                    'NI_own_pct': 100 * reg_w['NI'].sum() / (tot_av * (1 - ie_share)) if ie_share < 1 else 0.0,
                    'solar_avail_twh': tot_sv * to_annual_twh,
                    'solar_dispatch_twh': d['usable_s'].sum() * to_annual_twh,
                    'solar_curt_pct': 100 * d['curt_s'].sum() / sv,
                    'solar_cons_pct': 100 * d['con_s'].sum() / sv,
                    'solar_IE_own_pct': 100 * reg_s['IE'].sum() / (sv * s_ie) if s_ie > 0 else 0.0,
                    'solar_NI_own_pct': 100 * reg_s['NI'].sum() / (sv * (1 - s_ie)) if s_ie < 1 else 0.0,
                    'storage_charge_twh': d['charge_mw'].sum() * to_annual_twh,
                    'storage_discharge_twh': d['discharge_mw'].sum() * to_annual_twh,
                    'storage_end_soc_mwh': d['soc_mwh'][-1] if len(d['soc_mwh']) else 0.0,
                    'remaining_curt_combined_pct': 100 * (d['curt_w'].sum() + d['curt_s'].sum()) / (tot_av + tot_sv),
                    # Wind + solar together, per region: the same basis as the fitted limits,
                    # the hindcast and the backcast.
                    'IE_comb_pct': 100 * (reg_w['IE'].sum() + reg_s['IE'].sum())
                                   / (tot_av * ie_share + tot_sv * s_ie),
                    'NI_comb_pct': 100 * (reg_w['NI'].sum() + reg_s['NI'].sum())
                                   / (tot_av * (1 - ie_share) + tot_sv * (1 - s_ie)),
                })
            out = pd.DataFrame(rows).mean().to_dict()
            out['ie_share'] = ie_share
            out['solar_ie_share'] = s_ie
            return out

        base_limits_2026 = region_limits(start_year)
        base_run = run_weather_years(base_capacity_gw, base_demand_twh, base_limits_2026,
                                     HISTORICAL_SNSP_PCT / 100.0, solar_capacity_2026_gw,
                                     *storage_for_year(start_year), weather_years=[2026])
        base_weather_oversupply_2026 = base_run['curt_pct']
        other_curt_pct = max(0.0, base_2026_curt - base_weather_oversupply_2026)
        print(f">> 2026 curtailment {base_2026_curt:.2f}% = modelled SNSP {base_weather_oversupply_2026:.2f}% "
              f"(at {HISTORICAL_SNSP_PCT:.0f}%) + other causes held fixed {other_curt_pct:.2f}%")
        base_model_cons_2026 = base_run['cons_pct']
        print(f">> Modelled 2026 constraint: {base_model_cons_2026:.2f}% of all-island available wind "
              f"(IE {base_run['IE_own_pct']:.2f}% of IE wind, NI {base_run['NI_own_pct']:.2f}% of NI wind); "
              f"spreadsheet 2026 figure: {base_2026_cons:.2f}%")
        print(f">> Modelled 2026 solar: constraint {base_run['solar_cons_pct']:.2f}% and SNSP curtailment "
              f"{base_run['solar_curt_pct']:.2f}% of solar available output; the same fixed 'other' "
              f"curtailment ({other_curt_pct:.2f}%) is applied to solar")

        for yr in simulation_years:
            years_elapsed = yr - start_year
            cap = capacity_for_year(yr)

            yr_demand = base_demand_twh + (years_elapsed * annual_demand_growth_rate)
            limits_yr = region_limits(yr)
            # 2026 is the anchor year, so it uses the SNSP limit in force then; the scenario's
            # SNSP limit applies from 2027.
            snsp_yr = HISTORICAL_SNSP_PCT / 100.0 if yr == start_year else snsp_limit_fraction
            solar_cap = solar_capacity_for_year(yr)
            storage_power_mw, storage_energy_mwh = storage_for_year(yr)
            selected_weather_years = [2026] if yr == 2026 else complete_weather_years
            run = run_weather_years(cap, yr_demand, limits_yr, snsp_yr, solar_cap,
                                    storage_power_mw, storage_energy_mwh,
                                    weather_years=selected_weather_years)

            avg_raw_curt_pct = other_curt_pct + run['curt_pct']
            sim_constraint_pct = run['cons_pct']
            total_loss_pct = min(100.0, avg_raw_curt_pct + sim_constraint_pct)

            implied_gen_twh = max(0.0, run['dispatch_twh'] - (other_curt_pct / 100.0) * run['avail_twh'])
            sim_cf = implied_gen_twh * 1000.0 / (cap * 8760.0)

            wind_pct_of_demand = (implied_gen_twh / yr_demand) * 100.0

            solar_curt = other_curt_pct + run['solar_curt_pct'] if solar_cap > 0 else 0.0
            solar_con = run['solar_cons_pct'] if solar_cap > 0 else 0.0
            solar_gen_twh = max(0.0, run['solar_dispatch_twh'] - (other_curt_pct / 100.0) * run['solar_avail_twh'])
            solar_cf = solar_gen_twh * 1000.0 / (solar_cap * 8760.0) if solar_cap > 0 else 0.0
            solar_pct_of_demand = 100.0 * solar_gen_twh / yr_demand

            sim_results.append({
                'Year': yr,
                'Wind_Cap_GW': round(cap, 2),
                'Dem_TWh': round(yr_demand, 2),
                'RawCurt_%': round(avg_raw_curt_pct, 2),
                'GridCon_%': round(sim_constraint_pct, 2),
                'TotLoss_%': round(total_loss_pct, 2),
                'Wind_Fleet_CF_%_SEM': round(sim_cf * 100, 2),
                'Wind_%_SEM': round(wind_pct_of_demand, 2),
                'IE_Share_%': round(100 * run['ie_share'], 1),
                'Limit_IE_MW': round(limits_yr['IE']),
                'Limit_NI_MW': round(limits_yr['NI']),
                'Con_IE_%': round(run['IE_own_pct'], 2),
                'Con_NI_%': round(run['NI_own_pct'], 2),
                'GridCon_IE_pts': round(run['IE_pts'], 2),
                'GridCon_NI_pts': round(run['NI_pts'], 2),
                'Solar_Cap_GW': round(solar_cap, 2),
                'Storage_Power_MW': round(storage_power_mw, 1),
                'Storage_Energy_MWh': round(storage_energy_mwh, 1),
                'Storage_Charge_TWh': round(run['storage_charge_twh'], 3),
                'Storage_Discharge_TWh': round(run['storage_discharge_twh'], 3),
                'Renewables_Plus_Storage_TWh': round(implied_gen_twh + solar_gen_twh + run['storage_discharge_twh'], 3),
                'Storage_Loss_TWh': round(max(0.0, run['storage_charge_twh'] - run['storage_discharge_twh']), 3),
                'Remaining_Operational_Curt_%': round(run['remaining_curt_combined_pct'], 2),
                'Solar_Avail_TWh': round(run['solar_avail_twh'], 2),
                'Solar_Gen_TWh': round(solar_gen_twh, 2),
                'Solar_GridCon_%': round(solar_con, 2),
                'Solar_RawCurt_%': round(solar_curt, 2),
                'Solar_TotLoss_%': round(min(100.0, solar_con + solar_curt), 2),
                'Solar_CF_%': round(100 * solar_cf, 2),
                'Solar_%': round(solar_pct_of_demand, 2),
                'Solar_IE_Share_%': round(100 * run['solar_ie_share'], 1),
                'Solar_Con_IE_%': round(run['solar_IE_own_pct'] if solar_cap > 0 else 0.0, 2),
                'Solar_Con_NI_%': round(run['solar_NI_own_pct'] if solar_cap > 0 else 0.0, 2),
                'Wind_Gen_TWh': round(implied_gen_twh, 2),
                'Wind+Solar_%': round(wind_pct_of_demand + solar_pct_of_demand, 2),
                'Con_WS_IE_%': round(run['IE_comb_pct'], 2),
                'Con_WS_NI_%': round(run['NI_comb_pct'], 2),
            })

        sim_df = pd.DataFrame(sim_results)

        # Prepend actual historical parameters through 2025. These rows use the
        # 15-minute measured demand/generation and the historical input workbook.
        # Fields that are inherently forecast-only remain NaN on actual rows.
        actual_rows = []
        for _, h in master_hist.loc[master_hist['year'] <= 2025].sort_values('year').iterrows():
            year = int(h['year'])
            wind_cap = float(h['Capacity_GW']) if pd.notna(h.get('Capacity_GW')) else np.nan
            demand_twh = float(h['Demand_TWh']) if pd.notna(h.get('Demand_TWh')) else np.nan
            wind_gen_twh = float(h['Gen_TWh']) if pd.notna(h.get('Gen_TWh')) else np.nan
            cf_pct = (100.0 * wind_gen_twh / (wind_cap * 8.76)) if wind_cap > 0 and pd.notna(wind_gen_twh) else np.nan
            wind_pct = (100.0 * wind_gen_twh / demand_twh) if demand_twh > 0 and pd.notna(wind_gen_twh) else np.nan
            actual_rows.append({
                'Scenario': sc['scenario'], 'Data_Type': 'KPI(Actual)', 'Year': year,
                'Wind_Cap_GW': wind_cap, 'Dem_TWh': demand_twh,
                'RawCurt_%': h.get('Curtailment_Pct', np.nan),
                'GridCon_%': h.get('Constraint_Pct', np.nan),
                'TotLoss_%': (h.get('Curtailment_Pct', 0) + h.get('Constraint_Pct', 0))
                             if pd.notna(h.get('Curtailment_Pct')) and pd.notna(h.get('Constraint_Pct')) else np.nan,
                'Wind_Fleet_CF_%_SEM': cf_pct, 'Wind_%_SEM': wind_pct, 'Wind_Gen_TWh': wind_gen_twh,
            })
        actual_df = pd.DataFrame(actual_rows)
        sim_df['Data_Type'] = 'Forecast'
        sim_df['GridCon_Low_%'] = (sim_df['GridCon_%'] * (1 - hindcast_band)).round(2)
        sim_df['GridCon_High_%'] = (sim_df['GridCon_%'] * (1 + hindcast_band)).round(2)
        sim_df.insert(0, 'Scenario', sc['scenario'])
        sim_df = pd.concat([actual_df, sim_df], ignore_index=True, sort=False).sort_values('Year').reset_index(drop=True)

        # Backcast: the forecast's starting limits run back over history (section 2). Optionally
        # also with this scenario's reinforcement trend run in reverse.
        if BACKCAST_SCENARIO_TREND and any(reinforcement_rate.values()):
            bc_df = backcast(reinforcement_rate)
            bc_errors = backcast_error_summary(bc_df)
            print()
            print_backcast(bc_df, f"Backcast for scenario '{sc['scenario']}' (its reinforcement trend run backwards):")
            try:
                bc_df.round(3).to_csv(os.path.join(out_dir, "backcast_results.csv"), index=False)
            except OSError as e:
                print(f">> Could not save backcast_results.csv: {e}")
        else:
            bc_df, bc_errors = baseline_backcast, baseline_errors
        backcast_store[sc['scenario']] = (bc_df, bc_errors)

        # Warn when reinforcement makes a limit so large that constraint disappears.
        for reg in REGIONS:
            peak_avail = dd[reg]['avail_mw'].max()
            for y in simulation_years:
                lim = region_limits(y)[reg]
                cap_share = capacity_for_year(y) / base_capacity_gw
                if lim > 2 * peak_avail * cap_share:
                    growth = region_limits(final_year)[reg] / region_limits(start_year)[reg]
                    print(f"   ! {reg}: by {y} the effective limit ({lim:,.0f} MW) is over twice the region's peak "
                          f"available wind at that capacity, so constraint is effectively zero from then on. "
                          f"{100 * reinforcement_rate[reg]:.1f}%/yr compounds to x{growth:,.0f} by {final_year}.")
                    break
    
        key_years = [2026, 2027, 2028, 2030, 2033, 2036, 2039, 2042, 2045, 2048, 2049, 2050]
        key_df = sim_df[(sim_df['Data_Type'] == 'Forecast') & sim_df['Year'].isin(key_years)]
        main_cols = ['Year', 'Wind_Cap_GW', 'Dem_TWh', 'RawCurt_%', 'GridCon_%', 'GridCon_Low_%', 'GridCon_High_%',
                     'TotLoss_%', 'Wind_Fleet_CF_%_SEM', 'Wind_%_SEM']
        region_cols = ['Year', 'IE_Share_%', 'Limit_IE_MW', 'Limit_NI_MW', 'Con_IE_%', 'Con_NI_%',
                       'GridCon_IE_pts', 'GridCon_NI_pts', 'GridCon_%']
        print("All-island results (GridCon_% = IE + NI constraint as a share of all-island available wind):")
        print(key_df[main_cols].to_string(index=False))
        print("\nConstraint by region (Con_IE_% / Con_NI_% are shares of each region's own available wind;")
        print("GridCon_IE_pts + GridCon_NI_pts = all-island GridCon_%):")
        print(key_df[region_cols].to_string(index=False))
        solar_cols = ['Year', 'Solar_Cap_GW', 'Solar_Avail_TWh', 'Solar_Gen_TWh', 'Solar_GridCon_%',
                      'Solar_Con_IE_%', 'Solar_Con_NI_%', 'Solar_RawCurt_%', 'Solar_TotLoss_%', 'Solar_CF_%',
                      'Solar_%', 'Wind+Solar_%']
        print("\nSolar (shares each region's network limit with wind; SNSP counts wind + solar together):")
        print(key_df[solar_cols].to_string(index=False))
        try:
            # Keep labels as text, but force all historical/forecast parameter
            # columns to numeric values. This prevents Excel's "number stored as
            # text" warning. Numerical outputs are written to two decimal places.
            text_columns = {'Scenario', 'Data_Type'}
            numeric_columns = [c for c in sim_df.columns if c not in text_columns]
            sim_df[numeric_columns] = sim_df[numeric_columns].apply(pd.to_numeric, errors='coerce')
            sim_df[numeric_columns] = sim_df[numeric_columns].round(2)
            sim_df.to_csv(os.path.join(out_dir, FORECAST_RESULTS_CSV), index=False, float_format='%.2f')
            print(f"\n>> Every year, with the regional split, saved to '{os.path.join(out_dir, FORECAST_RESULTS_CSV)}'")
        except OSError as e:
            print(f"\n>> Could not save '{FORECAST_RESULTS_CSV}': {e}")

        print("\n====================================================================")
        print(f" 2050 MODEL OUTCOME SUMMARY")
        print("====================================================================")
        row_2050 = sim_df[sim_df['Year'] == 2050].iloc[0]
        actual_cap_gw = row_2050['Wind_Cap_GW']
        actual_dem_twh = row_2050['Dem_TWh']
        actual_wind_pct = row_2050['Wind_%_SEM']
        actual_gen_twh = max(0.0, actual_dem_twh * (actual_wind_pct / 100.0))
    
        peak_demand_2050_gw = actual_dem_twh / (8760.0 * 0.68 / 1000.0)
        firm_thermal_required_gw = peak_demand_2050_gw * 0.90
    
        print(f">> Total Projected Demand (2050)      : {actual_dem_twh:.2f} TWh")
        print(f">> Usable Wind Generation (2050)      : {actual_gen_twh:.2f} TWh ({actual_wind_pct:.2f}% of demand)")
        print(f">> Installed Wind Capacity (2050)     : {actual_cap_gw:.2f} GW")
        print(f">> Usable Solar Generation (2050)     : {row_2050['Solar_Gen_TWh']:.2f} TWh ({row_2050['Solar_%']:.2f}% of demand)")
        print(f">> Installed Solar Capacity (2050)    : {row_2050['Solar_Cap_GW']:.2f} GW")
        print(f">> Wind + Solar Share of Demand (2050): {row_2050['Wind+Solar_%']:.2f}%")
        print(f">> Required Firm Thermal Plant (2050) : {firm_thermal_required_gw:.2f} GW (Dunkelflaute Backup)")
        print(f">> Applied Build-Out Rate             : {annual_build_rate_gw*1000:.2f} MW/year ({annual_build_rate_gw:.3f} GW/year)")
        print(f">> Applied Forecast SNSP Limit       : {snsp_limit_pct:.1f}%")

        if not make_charts:
            return sim_df

        hist_weather_map = {2026: 2026}
        future_loop_years = complete_weather_years
        hist_weather_map.update({fy: future_loop_years[(fy - 2027) % len(future_loop_years)]
                                 for fy in range(2027, final_year + 1)})

        def regional_setup(row):
            """Region limits and IE availability share for a year's results row."""
            limits = {'IE': float(row['Limit_IE_MW']), 'NI': float(row['Limit_NI_MW'])}
            return limits, float(row['IE_Share_%']) / 100.0

        def solar_setup(row):
            """Solar capacity and IE solar share for a year's results row."""
            return float(row['Solar_Cap_GW']), float(row['Solar_IE_Share_%']) / 100.0

        # Historical years shown on the monthly charts: every complete year in the 15-minute file
        # from 2019 (kept at 2019 so the charts match their titles).
        hist_chart_years = [y for y in complete_weather_years if y >= 2019]

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
                        solar_hist = (g['sem_solar_generation'].fillna(0.0).mean()
                                      if 'sem_solar_generation' in g else 0.0)
                        records.append({'year': y, 'month': m,
                                        'demand_gwh': g['sem_demand'].mean() * hours / 1000.0,
                                        'usable_wind_gwh': max(0.0, g['sem_wind_generation'].mean() * hours / 1000.0),
                                        'usable_solar_gwh': max(0.0, solar_hist * hours / 1000.0),
                                        'storage_charge_gwh': 0.0,
                                        'storage_discharge_gwh': 0.0})
                    continue
                row = sim_df[sim_df['Year'] == y].iloc[0]
                cap_y, dem_y = float(row['Wind_Cap_GW']), float(row['Dem_TWh'])
                limits_y, share_y = regional_setup(row)
                solar_y, s_share_y = solar_setup(row)
                snsp_y = HISTORICAL_SNSP_PCT / 100.0 if y == start_year else snsp_limit_fraction
                df_wy = merged[merged['year'] == hist_weather_map[y]]
                hist_avg = df_wy['sem_demand'].mean()
                scale = (dem_y * 1e6 / 8760.0) / hist_avg if hist_avg > 0 else 1.0
                # Dispatch the complete weather year in one chronological pass. This preserves
                # state of charge between months and prevents a fresh initial SOC being created
                # twelve times in a year solely for plotting.
                avail_year = df_wy['spec_avail_mw_per_gw'].values * cap_y
                solar_year = df_wy['solar_avail_mw_per_gw'].values * solar_y
                demand_year = df_wy['sem_demand'].values * scale
                sp_y, se_y = storage_for_year(y)
                d_year = dispatch(avail_year, solar_year, demand_year, limits_y, share_y, s_share_y, snsp_y,
                                  sp_y, se_y, storage_charge_efficiency,
                                  storage_discharge_efficiency, storage_initial_soc_pct, muon_floor_mw=muon_floor_mw)
                usable_w_year = np.maximum(0.0, d_year['usable_w'] - (other_curt_pct / 100.0) * avail_year)
                usable_s_year = np.maximum(0.0, d_year['usable_s'] - (other_curt_pct / 100.0) * solar_year)
                months_year = df_wy['month'].to_numpy()
                for m in sorted(df_wy['month'].dropna().unique()):
                    mask = months_year == m
                    hours = pd.Period(f"{y}-{int(m):02d}").days_in_month * 24.0
                    records.append({'year': y, 'month': int(m),
                                    'demand_gwh': demand_year[mask].mean() * hours / 1000.0,
                                    'usable_wind_gwh': usable_w_year[mask].mean() * hours / 1000.0,
                                    'usable_solar_gwh': usable_s_year[mask].mean() * hours / 1000.0,
                                    'storage_charge_gwh': d_year['charge_mw'][mask].mean() * hours / 1000.0,
                                    'storage_discharge_gwh': d_year['discharge_mw'][mask].mean() * hours / 1000.0})
            return records

        records_19_30 = monthly_series(hist_chart_years, historical=True) + monthly_series(range(2026, 2031))
        df_g1 = pd.DataFrame(records_19_30)
        df_g1['date'] = pd.to_datetime(df_g1[['year', 'month']].assign(day=1))
        df_g1 = df_g1.sort_values('date').drop_duplicates(subset=['date'], keep='first')

        fig1, ax1 = plt.subplots(figsize=(13.3, 6.5), dpi=300)
        fig1.subplots_adjust(right=0.73)

        ax1.fill_between(df_g1['date'], 0, df_g1['usable_wind_gwh'], color='#90EE90', edgecolor='#2CA02C', linewidth=0.8, label='Wind Gen (GWh)', alpha=0.9)
        ax1.fill_between(df_g1['date'], df_g1['usable_wind_gwh'], df_g1['usable_wind_gwh'] + df_g1['usable_solar_gwh'].fillna(0.0),
                         color='#FFD54F', edgecolor='#E0A800', linewidth=0.6, label='Solar Gen (GWh)', alpha=0.9)
        renewable_top1 = df_g1['usable_wind_gwh'] + df_g1['usable_solar_gwh'].fillna(0.0)
        storage_top1 = renewable_top1 + df_g1['storage_discharge_gwh'].fillna(0.0)
        ax1.fill_between(df_g1['date'], renewable_top1, storage_top1,
                         color='#9467BD', edgecolor='#6F42A5', linewidth=0.7, alpha=0.9,
                         label='Storage Discharge (GWh)')
        ax1.fill_between(df_g1['date'], 0, -df_g1['storage_charge_gwh'].fillna(0.0),
                         color='#4C78A8', edgecolor='#2F5D8A', linewidth=0.6, alpha=0.75,
                         label='Storage Charging (negative GWh)')
        ax1.axhline(0, color='#666666', linewidth=0.8)
        ax1.plot(df_g1['date'], df_g1['demand_gwh'], color='black', linewidth=2.2, label='Demand (GWh)')

        x_nums1 = mdates.date2num(df_g1['date'])
        z_d1 = np.polyfit(x_nums1, df_g1['demand_gwh'], 1)
        p_d1 = np.poly1d(z_d1)
        ax1.plot(df_g1['date'], p_d1(x_nums1), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        row_2030 = sim_df[sim_df['Year'] == 2030].iloc[0]
        wind_pct_2030 = float(row_2030['Wind_%_SEM'])

        ax1.plot([], [], ' ', label=f'2030 Wind % of Demand: {wind_pct_2030:.1f}%')

        ax1.set_title(scenario_plot_title('Ireland (All-Island) Overview + Short term 2030 Forecast (Jan 2019 to Dec 2030)'), fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax1.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax1.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax1.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax1.xaxis.set_major_locator(mdates.YearLocator(1))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax1.set_xlim(df_g1['date'].iloc[0], df_g1['date'].iloc[-1])

        ax1.legend(loc='upper left', bbox_to_anchor=(1.015, 1.00), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=8.5)

        renewables_2030_pct = renewables_including_storage_pct(2030)
        stats_text1 = (
            f"2026 Demand: {base_demand_twh:.2f} TWh\n"
            f"2030 Demand: {row_2030['Dem_TWh']:.2f} TWh\n"
            f"2030 Renewables (incl. Storage): {renewables_2030_pct:.1f}%\n"
            f"{capacity_box_line(2030)}\n"
            f"Wind Build Rate: {annual_build_rate_gw*1000:.1f} MW/yr\n"
            f"Solar Build Rate: {solar_build_rate_gw*1000:.1f} MW/yr\n"
            f"SNSP: {snsp_limit_pct:.1f}% | MUON: {muon_floor_mw:.0f} MW"
        )
        ax1.text(1.015, 0.03, stats_text1, transform=ax1.transAxes, va='bottom', fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

        plt.tight_layout()
        g1_png = scenario_plot_filename("Historical_2019_2030_Overview.png")
        plt.savefig(os.path.join(out_dir, g1_png), bbox_inches='tight', pad_inches=0.08)
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

        fig2, ax2 = plt.subplots(figsize=(13.3, 6.5), dpi=300)
        fig2.subplots_adjust(right=0.73)

        ax2.fill_between(df_monthly2['date'], 0, df_monthly2['usable_wind_gwh'], color='#90EE90', edgecolor='#2CA02C', linewidth=0.8, label='Wind Gen (GWh)', alpha=0.9)
        ax2.fill_between(df_monthly2['date'], df_monthly2['usable_wind_gwh'], df_monthly2['usable_wind_gwh'] + df_monthly2['usable_solar_gwh'].fillna(0.0),
                         color='#FFD54F', edgecolor='#E0A800', linewidth=0.6, label='Solar Gen (GWh)', alpha=0.9)
        renewable_top2 = df_monthly2['usable_wind_gwh'] + df_monthly2['usable_solar_gwh'].fillna(0.0)
        storage_top2 = renewable_top2 + df_monthly2['storage_discharge_gwh'].fillna(0.0)
        ax2.fill_between(df_monthly2['date'], renewable_top2, storage_top2,
                         color='#9467BD', edgecolor='#6F42A5', linewidth=0.7, alpha=0.9,
                         label='Storage Discharge (GWh)')
        ax2.fill_between(df_monthly2['date'], 0, -df_monthly2['storage_charge_gwh'].fillna(0.0),
                         color='#4C78A8', edgecolor='#2F5D8A', linewidth=0.6, alpha=0.75,
                         label='Storage Charging (negative GWh)')
        ax2.axhline(0, color='#666666', linewidth=0.8)
        ax2.plot(df_monthly2['date'], df_monthly2['demand_gwh'], color='black', linewidth=2.2, label='Demand (GWh)')

        x_nums2 = mdates.date2num(df_monthly2['date'])
        z_d2 = np.polyfit(x_nums2, df_monthly2['demand_gwh'], 1)
        p_d2 = np.poly1d(z_d2)
        ax2.plot(df_monthly2['date'], p_d2(x_nums2), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        ax2.plot([], [], ' ', label=f'2050 Wind % of Demand: {actual_wind_pct:.1f}%')

        ax2.set_title(scenario_plot_title('Ireland (All-Island) Energy Transition Forecast (Jan 2045 to Dec 2050)'), fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax2.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax2.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax2.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax2.xaxis.set_major_locator(mdates.YearLocator(1))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax2.set_xlim(df_monthly2['date'].iloc[0], df_monthly2['date'].iloc[-1])

        ax2.legend(loc='upper left', bbox_to_anchor=(1.015, 1.00), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=8.5)

        renewables_2050_pct = renewables_including_storage_pct(2050)
        stats_text2 = (
            f"2050 Demand: {actual_dem_twh:.2f} TWh\n"
            f"2050 Renewables (incl. Storage): {renewables_2050_pct:.1f}%\n"
            f"{capacity_box_line(2050)}\n"
            f"Wind Build Rate: {annual_build_rate_gw*1000:.1f} MW/yr\n"
            f"Solar Build Rate: {solar_build_rate_gw*1000:.1f} MW/yr\n"
            f"SNSP: {snsp_limit_pct:.1f}% | MUON: {muon_floor_mw:.0f} MW"
        )
        ax2.text(1.015, 0.03, stats_text2, transform=ax2.transAxes, va='bottom', fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

        plt.tight_layout()
        g2_png = scenario_plot_filename("Forecast_2045_2050_Overview.png")
        plt.savefig(os.path.join(out_dir, g2_png), bbox_inches='tight', pad_inches=0.08)
        print(f">> Graph 2 saved as '{g2_png}'!")

        # -------------------------------------------------------------------------
        # HELPER FUNCTION FOR DAILY DISPATCH PROFILE CHARTS (GRAPHS 3, 4, 5, 6)
        # -------------------------------------------------------------------------
        def generate_daily_chart(target_year, month_num, day_num, output_filename, chart_title_suffix):
            row_yr = sim_df[sim_df['Year'] == target_year].iloc[0]
            cap_gw = float(row_yr['Wind_Cap_GW'])
            demand_twh = float(row_yr['Dem_TWh'])
            limits_yr, ie_share_yr = regional_setup(row_yr)
            solar_gw_yr, solar_share_yr = solar_setup(row_yr)

            wy = hist_weather_map.get(target_year, complete_weather_years[target_year % len(complete_weather_years)])
            df_wy = merged[merged['year'] == wy].copy().sort_values('parsed_date').reset_index(drop=True)

            df_wy['scaled_avail_mw'] = df_wy['spec_avail_mw_per_gw'] * cap_gw
            expected_avg_mw = (demand_twh * 1000000.0) / 8760.0
            actual_hist_avg_mw = df_wy['sem_demand'].mean()
            mw_scale = expected_avg_mw / actual_hist_avg_mw if actual_hist_avg_mw > 0 else 1.0
            df_wy['scaled_demand_mw'] = df_wy['sem_demand'] * mw_scale

            # Dispatch the complete chronological weather year first, then extract the
            # requested day. This gives the chart the true SOC carried in from the
            # preceding day instead of resetting the battery at midnight.
            avail_w_year = df_wy['scaled_avail_mw'].to_numpy()
            avail_s_year = df_wy['solar_avail_mw_per_gw'].to_numpy() * solar_gw_yr
            demand_year = df_wy['scaled_demand_mw'].to_numpy()
            storage_power_day, storage_energy_day = storage_for_year(target_year)
            dd_year = dispatch(avail_w_year, avail_s_year, demand_year,
                               limits_yr, ie_share_yr, solar_share_yr,
                               snsp_limit_fraction, storage_power_day, storage_energy_day,
                               storage_charge_efficiency, storage_discharge_efficiency,
                               storage_initial_soc_pct, muon_floor_mw=muon_floor_mw)

            day_mask = ((df_wy['month'].to_numpy() == month_num) &
                        (df_wy['day'].to_numpy() == day_num))
            if not np.any(day_mask):
                print(f"Warning: Day {day_num} Month {month_num} not present in dataset!")
                return
            df_day = df_wy.loc[day_mask].copy()
            month_name = pd.to_datetime(f"2022-{month_num:02d}-{day_num:02d}").strftime('%B')

            time_hours = np.arange(day_mask.sum()) * INTERVAL_HOURS
            d_mw = demand_year[day_mask]
            avail_w_mw = avail_w_year[day_mask]
            avail_s_mw = avail_s_year[day_mask]
            snsp_limit_mw = np.minimum(d_mw * snsp_limit_fraction, np.maximum(0.0, d_mw - muon_floor_mw))

            dd_day = {
                key: (value[day_mask] if isinstance(value, np.ndarray) else value)
                for key, value in dd_year.items() if key != 'reg'
            }
            dd_day['reg'] = {
                r: {tech: values[day_mask] for tech, values in dd_year['reg'][r].items()}
                for r in REGIONS
            }
            reg_cons_mw = {r: dd_day['reg'][r]['wind'] + dd_day['reg'][r]['solar'] for r in REGIONS}
            grid_constraint_mw = dd_day['con_w'] + dd_day['con_s']
            snsp_curtailed_mw = dd_day['curt_w'] + dd_day['curt_s']
            storage_charge_mw = dd_day['charge_mw']
            storage_discharge_mw = dd_day['discharge_mw']
            usable_w_mw, usable_s_mw = dd_day['usable_w'], dd_day['usable_s']
            total_avail_mw = avail_w_mw + avail_s_mw
            usable_tot_mw = usable_w_mw + usable_s_mw
            total_dispatch_down_mw = grid_constraint_mw + snsp_curtailed_mw

            fig, ax = plt.subplots(figsize=(13.3, 6.5), dpi=300)
            fig.subplots_adjust(right=0.73)

            ax.plot(time_hours, total_avail_mw, color='#2CA02C', linewidth=2.0, linestyle='--', label='Available Wind + Solar (MW)')
            ax.plot(time_hours, d_mw, color='black', linewidth=2.5, label='System Demand (MW)')
            ax.plot(time_hours, snsp_limit_mw, color='#D62728', linewidth=2.0, linestyle='-', label=f'Operational Limit (SNSP {snsp_limit_pct:.1f}% / MUON floor)')
            # Firm requirement is the gap between renewable availability and the
            # shared operational limit, plus the gap from that limit to demand.
            ax.fill_between(time_hours, total_avail_mw, snsp_limit_mw,
                            where=(snsp_limit_mw > total_avail_mw), color='#BDBDBD', alpha=0.65,
                            label='Firm (Gas)', zorder=0)
            ax.fill_between(time_hours, snsp_limit_mw, d_mw,
                            where=(d_mw > snsp_limit_mw), color='#BDBDBD', alpha=0.65,
                            label='_nolegend_', zorder=0)

            ax.fill_between(time_hours, 0, usable_w_mw, color='#90EE90', alpha=0.85, label='Usable Dispatched Wind (MW)')
            ax.fill_between(time_hours, usable_w_mw, usable_tot_mw, color='#FFD54F', alpha=0.9, label='Usable Dispatched Solar (MW)')
            ax.fill_between(time_hours, usable_tot_mw, usable_tot_mw + storage_discharge_mw,
                            where=(storage_discharge_mw > 0), color='#9467BD', edgecolor='#6F42A5',
                            linewidth=0.7, alpha=0.9, label='Battery Discharge, stacked (MW)')
            ax.fill_between(time_hours, 0, -storage_charge_mw,
                            where=(storage_charge_mw > 0), color='#4C78A8', edgecolor='#2F5D8A',
                            linewidth=0.7, alpha=0.75,
                            label='Battery Charging from Curtailment, negative (MW)')
            ax.axhline(0, color='#666666', linewidth=0.8)
            ax.fill_between(time_hours, usable_tot_mw, usable_tot_mw + snsp_curtailed_mw, where=(snsp_curtailed_mw > 0),
                            facecolor='none', edgecolor='#D62728', hatch='///', linewidth=0.8, label='SNSP Curtailment (MW)')
            ax.fill_between(time_hours, usable_tot_mw + snsp_curtailed_mw, total_avail_mw, where=(grid_constraint_mw > 0),
                            facecolor='none', edgecolor='#FF8C00', hatch='\\\\\\', linewidth=0.8, label='Grid Bottleneck Constraint (MW)')

            ax.set_title(scenario_plot_title(f'Forecasted Daily Chart: {chart_title_suffix}, {day_num} {month_name} {target_year}'), fontsize=13, fontweight='bold', color='#000080', pad=15)
            ax.set_ylabel('Power Generation & Demand (MW)', fontsize=11, fontweight='bold')
            ax.set_xlabel('Time of Day (Hours)', fontsize=11, fontweight='bold')
            ax.set_xticks(range(0, 25, 2))
            ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 25, 2)])
            ax.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

            ax.legend(loc='upper left', bbox_to_anchor=(1.015, 1.00), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=8.2, ncol=1)

            daily_avail_gwh = (total_avail_mw.sum() * 0.25) / 1000.0
            daily_solar_gwh = (avail_s_mw.sum() * 0.25) / 1000.0
            daily_dem_gwh = (d_mw.sum() * 0.25) / 1000.0
            daily_curt_gwh = (snsp_curtailed_mw.sum() * INTERVAL_HOURS) / 1000.0
            daily_charge_gwh = (storage_charge_mw.sum() * INTERVAL_HOURS) / 1000.0
            daily_discharge_gwh = (storage_discharge_mw.sum() * INTERVAL_HOURS) / 1000.0
            daily_cons_gwh = (grid_constraint_mw.sum() * 0.25) / 1000.0
            daily_cons_ie_gwh = (reg_cons_mw['IE'].sum() * 0.25) / 1000.0
            daily_cons_ni_gwh = (reg_cons_mw['NI'].sum() * 0.25) / 1000.0
            daily_tot_dd_gwh = (total_dispatch_down_mw.sum() * 0.25) / 1000.0
            daily_dd_pct = (daily_tot_dd_gwh / daily_avail_gwh) * 100.0 if daily_avail_gwh > 0 else 0.0

            stats_text = (
                f"Simulated: {day_num} {month_name} {target_year} | Weather {wy}\n"
                f"Installed: Wind {cap_gw:.2f} GW | Solar {solar_gw_yr:.2f} GW\n"
                f"Battery: {storage_power_day:.0f} MW / {storage_energy_day/1000.0:.2f} GWh\n"
                f"Daily Demand: {daily_dem_gwh:.1f} GWh\n"
                f"Available Wind + Solar: {daily_avail_gwh:.1f} GWh\n"
                f"Grid Constraint: {daily_cons_gwh:.1f} GWh\n"
                f"SNSP Curtailment: {daily_curt_gwh:.1f} GWh\n"
                f"Battery Charge / Discharge: {daily_charge_gwh:.1f} / {daily_discharge_gwh:.1f} GWh\n"
                f"SNSP: {snsp_limit_pct:.1f}% | MUON: {muon_floor_mw:.0f} MW"
            )
            ax.text(1.015, 0.03, stats_text, transform=ax.transAxes, va='bottom', fontsize=9.5, fontweight='bold', color='#000080',
                     bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

            plt.tight_layout()
            output_filename = scenario_plot_filename(output_filename)
            plt.savefig(os.path.join(out_dir, output_filename), bbox_inches='tight', pad_inches=0.08)
            print(f">> Chart saved as '{output_filename}' for {day_num} {month_name} {target_year}!")

        # -------------------------------------------------------------------------
        # GENERATE DAILY DISPATCH PROFILES (GRAPHS 3, 4, 5, 6)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 7. GENERATING DAILY SHOWCASE PROFILES (2033 & 2048)")
        print("====================================================================")
        
        # 2048 Calculations (Storm, Typical Low, Winter Dunkelflaute)
        wy_2048 = hist_weather_map[2048]
        df_wy_2048 = merged[merged['year'] == wy_2048].copy()
        row_2048 = sim_df[sim_df['Year'] == 2048].iloc[0]
        wind_gw_2048 = float(row_2048['Wind_Cap_GW'])
        solar_gw_2048, _ = solar_setup(row_2048)
        df_wy_2048['scaled_avail_mw'] = df_wy_2048['spec_avail_mw_per_gw'] * wind_gw_2048
        df_wy_2048['scaled_solar_mw'] = df_wy_2048['solar_avail_mw_per_gw'] * solar_gw_2048

        daily_sums_2048 = df_wy_2048.groupby(['month', 'day'], as_index=False).agg(
            wind_mwh=('scaled_avail_mw', lambda x: x.sum() * INTERVAL_HOURS),
            solar_mwh=('scaled_solar_mw', lambda x: x.sum() * INTERVAL_HOURS)
        )
        daily_sums_2048['scaled_avail_mw'] = daily_sums_2048['wind_mwh'] / INTERVAL_HOURS
        daily_sums_2048 = daily_sums_2048.sort_values('scaled_avail_mw', ascending=True).reset_index(drop=True)

        low_avg_day = daily_sums_2048.iloc[int(len(daily_sums_2048) * 0.30)] # 30th percentile wind day
        storm_day = daily_sums_2048.iloc[-1] # Absolute maximum wind availability

        # A true dunkelflaute should have low wind and low solar. Restrict the search
        # to November, December and January, then minimise the worse of the day's
        # wind and solar percentile ranks. The average rank breaks close ties.
        winter_days = daily_sums_2048[daily_sums_2048['month'].isin([11, 12, 1])].copy()
        if winter_days.empty:
            raise ValueError("No November-January days are available for the 2048 weather reference year.")
        winter_days['wind_rank'] = winter_days['wind_mwh'].rank(method='average', pct=True)
        winter_days['solar_rank'] = winter_days['solar_mwh'].rank(method='average', pct=True)
        winter_days['dunkelflaute_score'] = (
            winter_days[['wind_rank', 'solar_rank']].max(axis=1) +
            0.25 * winter_days[['wind_rank', 'solar_rank']].mean(axis=1)
        )
        dunkel_day = winter_days.sort_values(
            ['dunkelflaute_score', 'wind_mwh', 'solar_mwh'], ascending=True
        ).iloc[0]
        print(f">> Selected winter dunkelflaute day: {int(dunkel_day['day']):02d}/"
              f"{int(dunkel_day['month']):02d}; wind={dunkel_day['wind_mwh']/1000.0:.1f} GWh, "
              f"solar={dunkel_day['solar_mwh']/1000.0:.1f} GWh.")
        
        # 2033 Calculations (Average)
        wy_2033 = hist_weather_map.get(2033, complete_weather_years[2033 % len(complete_weather_years)])
        df_wy_2033 = merged[merged['year'] == wy_2033].copy()
        df_wy_2033['scaled_avail_mw'] = df_wy_2033['spec_avail_mw_per_gw'] * float(sim_df[sim_df['Year'] == 2033]['Wind_Cap_GW'].values[0])
        daily_sums_2033 = df_wy_2033.groupby(['month', 'day'])['scaled_avail_mw'].sum().reset_index()
        daily_sums_2033 = daily_sums_2033.sort_values('scaled_avail_mw', ascending=True).reset_index(drop=True)
        
        avg_day_2033 = daily_sums_2033.iloc[int(len(daily_sums_2033) * 0.50)] # 50th percentile (Median average)
        
        # Generate Graph 3 (Storm 2048)
        generate_daily_chart(2048, int(storm_day['month']), int(storm_day['day']), "Daily_Absolute_Storm_2048.png", "Absolute Peak Wind Storm Event")
        
        # Generate Graph 4 (Typical Low 2048)
        generate_daily_chart(2048, int(low_avg_day['month']), int(low_avg_day['day']), "Daily_Typical_Low_Average_2048.png", "Typical Low-Average Wind Day")
        
        # Generate Graph 5 (Winter Dunkelflaute 2048: jointly low wind and solar)
        generate_daily_chart(2048, int(dunkel_day['month']), int(dunkel_day['day']),
                             "Daily_Dunkelflaute_2048.png",
                             "Winter Dunkelflaute: Joint Low Wind and Solar Event")
        
        # Generate Graph 6 (Average 2033)
        generate_daily_chart(2033, int(avg_day_2033['month']), int(avg_day_2033['day']), "Daily_Average_Wind_2033.png", "Average Wind Day")

        # Generate an additional 2040 daily chart selected from May-August. The chosen
        # day must contain both battery charging and discharging. Among qualifying
        # days, selection rewards both high renewable availability and high battery
        # throughput, so the result illustrates a genuine same-day storage cycle.
        target_cycle_year = 2040
        row_cycle = sim_df[sim_df['Year'] == target_cycle_year].iloc[0]
        cap_cycle = float(row_cycle['Wind_Cap_GW'])
        demand_cycle_twh = float(row_cycle['Dem_TWh'])
        limits_cycle, ie_share_cycle = regional_setup(row_cycle)
        solar_cycle_gw, solar_share_cycle = solar_setup(row_cycle)
        wy_cycle = hist_weather_map.get(target_cycle_year,
                                        complete_weather_years[target_cycle_year % len(complete_weather_years)])
        df_cycle = merged[merged['year'] == wy_cycle].copy().sort_values('parsed_date').reset_index(drop=True)
        wind_cycle = df_cycle['spec_avail_mw_per_gw'].to_numpy() * cap_cycle
        solar_cycle = df_cycle['solar_avail_mw_per_gw'].to_numpy() * solar_cycle_gw
        expected_cycle_mw = (demand_cycle_twh * 1000000.0) / 8760.0
        hist_cycle_mw = df_cycle['sem_demand'].mean()
        demand_cycle = df_cycle['sem_demand'].to_numpy() * (
            expected_cycle_mw / hist_cycle_mw if hist_cycle_mw > 0 else 1.0)
        storage_power_cycle, storage_energy_cycle = storage_for_year(target_cycle_year)
        dd_cycle = dispatch(wind_cycle, solar_cycle, demand_cycle,
                            limits_cycle, ie_share_cycle, solar_share_cycle,
                            snsp_limit_fraction, storage_power_cycle, storage_energy_cycle,
                            storage_charge_efficiency, storage_discharge_efficiency,
                            storage_initial_soc_pct, muon_floor_mw=muon_floor_mw)
        cycle_intervals = pd.DataFrame({
            'month': df_cycle['month'].to_numpy(),
            'day': df_cycle['day'].to_numpy(),
            'renewable_mwh': (wind_cycle + solar_cycle) * INTERVAL_HOURS,
            'charge_mwh': dd_cycle['charge_mw'] * INTERVAL_HOURS,
            'discharge_mwh': dd_cycle['discharge_mw'] * INTERVAL_HOURS,
        })
        cycle_days = cycle_intervals.groupby(['month', 'day'], as_index=False).sum()
        summer_days = cycle_days[cycle_days['month'].between(5, 8)].copy()
        qualifying = summer_days[(summer_days['charge_mwh'] > 0.1) &
                                 (summer_days['discharge_mwh'] > 0.1)].copy()
        if qualifying.empty:
            qualifying = cycle_days[(cycle_days['charge_mwh'] > 0.1) &
                                    (cycle_days['discharge_mwh'] > 0.1)].copy()
            print(">> No May-August 2040 day had both charge and discharge; using the best qualifying day in the full year.")
        if qualifying.empty:
            print(">> Warning: no 2040 day contains both battery charging and discharging; extra chart skipped.")
        else:
            def _normalise(series):
                span = series.max() - series.min()
                return (series - series.min()) / span if span > 0 else pd.Series(0.0, index=series.index)
            qualifying['cycle_score'] = (
                0.50 * _normalise(qualifying['renewable_mwh']) +
                0.25 * _normalise(qualifying['charge_mwh']) +
                0.25 * _normalise(qualifying['discharge_mwh'])
            )
            cycle_day = qualifying.sort_values(
                ['cycle_score', 'renewable_mwh'], ascending=False).iloc[0]
            print(f">> Selected 2040 storage-cycle day: {int(cycle_day['day']):02d}/"
                  f"{int(cycle_day['month']):02d}; renewable={cycle_day['renewable_mwh']/1000.0:.1f} GWh, "
                  f"charge={cycle_day['charge_mwh']/1000.0:.1f} GWh, "
                  f"discharge={cycle_day['discharge_mwh']/1000.0:.1f} GWh.")
            generate_daily_chart(target_cycle_year, int(cycle_day['month']), int(cycle_day['day']),
                                 "Daily_Storage_Charge_Discharge_2040.png",
                                 "High-Renewables Same-Day Battery Charge and Discharge")

        # -------------------------------------------------------------------------
        # GRAPH 7: GRAND MASTER OVERVIEW (JAN 2019 - DEC 2050)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 8. GENERATING GRAPH 7: GRAND MASTER OVERVIEW (2019 - 2050)")
        print("====================================================================")
    
        # Extract Maximum Wind % Attained and the Year it occurred for the stats box
        max_wind_row = sim_df.loc[sim_df['Wind_%_SEM'].idxmax()]
        max_wind_pct_val = max_wind_row['Wind_%_SEM']
        max_wind_year = int(max_wind_row['Year'])

        df_grand = pd.DataFrame(monthly_series(hist_chart_years, historical=True)
                                + monthly_series(range(2026, 2051)))

        df_grand['date'] = pd.to_datetime(df_grand[['year', 'month']].assign(day=1))
        df_grand = df_grand.sort_values('date').drop_duplicates(subset=['date'], keep='first')

        fig6, ax6 = plt.subplots(figsize=(14.5, 7), dpi=300)
        fig6.subplots_adjust(right=0.75)

        ax6.fill_between(df_grand['date'], 0, df_grand['usable_wind_gwh'], color='#90EE90', edgecolor='#2CA02C', linewidth=0.8, label='Usable Wind Gen (GWh)', alpha=0.9)
        ax6.fill_between(df_grand['date'], df_grand['usable_wind_gwh'], df_grand['usable_wind_gwh'] + df_grand['usable_solar_gwh'].fillna(0.0),
                         color='#FFD54F', edgecolor='#E0A800', linewidth=0.6, label='Solar Gen (GWh)', alpha=0.9)
        renewable_top6 = df_grand['usable_wind_gwh'] + df_grand['usable_solar_gwh'].fillna(0.0)
        storage_top6 = renewable_top6 + df_grand['storage_discharge_gwh'].fillna(0.0)
        ax6.fill_between(df_grand['date'], renewable_top6, storage_top6,
                         color='#9467BD', edgecolor='#6F42A5', linewidth=0.7, alpha=0.9,
                         label='Storage Discharge (GWh)')
        ax6.fill_between(df_grand['date'], 0, -df_grand['storage_charge_gwh'].fillna(0.0),
                         color='#4C78A8', edgecolor='#2F5D8A', linewidth=0.6, alpha=0.75,
                         label='Storage Charging (negative GWh)')
        ax6.axhline(0, color='#666666', linewidth=0.8)
        ax6.plot(df_grand['date'], df_grand['demand_gwh'], color='black', linewidth=2.0, label='System Demand (GWh)')

        x_nums6 = mdates.date2num(df_grand['date'])
        z_d6 = np.polyfit(x_nums6, df_grand['demand_gwh'], 1)
        p_d6 = np.poly1d(z_d6)
        ax6.plot(df_grand['date'], p_d6(x_nums6), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        ax6.set_title(scenario_plot_title('Ireland (All-Island) Grand Energy Transition Timeline & Wind Penetration (Jan 2019 to Dec 2050)'), fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax6.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax6.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax6.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax6.xaxis.set_major_locator(mdates.YearLocator(2))
        ax6.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax6.set_xlim(df_grand['date'].iloc[0], df_grand['date'].iloc[-1])

        ax6.legend(loc='upper left', bbox_to_anchor=(1.015, 1.00), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=8.2, ncol=1)

        # Added Max Wind % Attained (and the year) to the stats box
        renewables_2050_pct = renewables_including_storage_pct(2050)
        stats_text6 = (
            f"2050 Demand: {actual_dem_twh:.1f} TWh\n"
            f"2050 Renewables (incl. Storage): {renewables_2050_pct:.1f}%\n"
            f"{capacity_box_line(2050)}\n"
            f"Wind Build Rate: {annual_build_rate_gw*1000:.0f} MW/yr\n"
            f"Solar Build Rate: {solar_build_rate_gw*1000:.0f} MW/yr\n"
            f"SNSP: {snsp_limit_pct:.0f}% | MUON: {muon_floor_mw:.0f} MW"
        )
        ax6.text(1.015, 0.03, stats_text6, transform=ax6.transAxes, va='bottom', fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

        plt.tight_layout()
        g6_png = scenario_plot_filename("Grand_Overview_2019_2050.png")
        plt.savefig(os.path.join(out_dir, g6_png), bbox_inches='tight', pad_inches=0.08)
        print(f">> Grand Overview chart saved as '{g6_png}'!")
        # -------------------------------------------------------------------------
        # GRAPH 8: CONSTRAINT BACKCAST & FORECAST BY REGION
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(" 9. GENERATING GRAPH 8: CONSTRAINT BACKCAST & FORECAST BY REGION")
        print("====================================================================")
        fig8, axes8 = plt.subplots(1, 2, figsize=(14, 6), dpi=300, sharex=True)
        for ax8, reg in zip(axes8, REGIONS):
            b = bc_df[bc_df['Region'] == reg].sort_values('Year')
            full = b[b['Label'] == b['Year'].astype(str)]
            part = b[b['Label'] != b['Year'].astype(str)]
            ax8.plot(full['Year'], full['Actual_Cons_%'], 'o-', color='black', linewidth=2.0,
                     label='Actual (dispatch-down records)')
            if len(part):
                ax8.plot(part['Year'], part['Actual_Cons_%'], 'o', color='black', fillstyle='none',
                         markersize=8, label='Actual, part-year')
            ax8.plot(b['Year'], b['Predicted_Cons_%'], 's--', color='#1f77b4', linewidth=1.6,
                     label='Backcast (forecast starting model)')
            # Same basis as the fit and the backcast: wind + solar constraint over wind + solar
            # availability (wind only if there are no solar records).
            col = f'Con_WS_{reg}_%' if solar_in_fit else f'Con_{reg}_%'
            ax8.plot(sim_df['Year'], sim_df[col], '-', color='#FF8C00', linewidth=2.0,
                     label=f'Forecast ({sc["scenario"]})')
            ax8.set_title(f"{REGION_NAMES[reg]} ({reg})", fontsize=12, fontweight='bold', color='#000080')
            ax8.set_xlabel('Year', fontsize=10, fontweight='bold')
            ax8.set_ylabel(f"Constraint, % of {reg} available {'wind + solar' if solar_in_fit else 'wind'}",
                           fontsize=10, fontweight='bold')
            ax8.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')
            e = bc_errors.get(reg, {})
            if e.get('oos_n'):
                ax8.text(0.02, 0.97, f"Backcast error outside fit: ±{e['oos_mae']:.0f}% "
                         f"(bias {e['oos_bias']:+.0f}%)", transform=ax8.transAxes, va='top', fontsize=9,
                         color='#000080', bbox=dict(boxstyle='round,pad=0.4', facecolor='#F0F4FF',
                                                    edgecolor='#B0C4DE'))
            ax8.legend(loc='lower right', fontsize=8.5, frameon=True, facecolor='white')
        fig8.suptitle(scenario_plot_title('Constraint: Actual, Backcast from the Forecast Starting Model, and Forecast'),
                      fontsize=14, fontweight='bold', color='#000080')
        plt.tight_layout()
        g8_png = scenario_plot_filename("Constraint_Backcast_Forecast.png")
        plt.savefig(os.path.join(out_dir, g8_png))
        print(f">> Backcast chart saved as '{g8_png}'!")

        plt.close('all')
        return sim_df

    scenario_file = input_path(SCENARIO_FILE)
    summary_path = os.path.join(SCENARIO_OUTPUT_DIR, SCENARIO_SUMMARY_CSV)
    if os.path.exists(scenario_file):
        scenarios = load_scenarios(scenario_file)
        print(f"\n>> Running {len(scenarios)} scenarios from '{scenario_file}' "
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
                    'Build_Wind_IE_GW_yr': round(sc['build_rate_wind_ie'], 3),
                    'Build_Wind_NI_GW_yr': round(sc['build_rate_wind_ni'], 3),
                    'Build_Solar_IE_GW_yr': round(sc['build_rate_solar_ie'], 3),
                    'Build_Solar_NI_GW_yr': round(sc['build_rate_solar_ni'], 3),
                    'SNSP_%': sc['snsp_limit_pct'],
                    'Storage_Power_Build_MW_yr': sc['storage_power_build_rate_mw'],
                    'Storage_Energy_Build_MWh_yr': sc['storage_energy_build_rate_mwh'],
                    'Storage_Power_2026_MW': sc['storage_power_2026_mw'],
                    'Storage_Energy_2026_MWh': sc['storage_energy_2026_mwh'],
                    'IE_Reinf_%_yr': sc['ie_reinforcement_pct'], 'NI_Reinf_%_yr': sc['ni_reinforcement_pct'],
                    'Wind_Cap_GW': r['Wind_Cap_GW'], 'Dem_TWh': r['Dem_TWh'],
                    'GridCon_%': r['GridCon_%'], 'GridCon_Low_%': r['GridCon_Low_%'],
                    'GridCon_High_%': r['GridCon_High_%'], 'Con_IE_%': r['Con_IE_%'],
                    'Con_NI_%': r['Con_NI_%'], 'RawCurt_%': r['RawCurt_%'], 'TotLoss_%': r['TotLoss_%'],
                    'Wind_Fleet_CF_%_SEM': r['Wind_Fleet_CF_%_SEM'], 'Wind_%_SEM': r['Wind_%_SEM'],
                    'Solar_Cap_GW': r['Solar_Cap_GW'], 'Solar_GridCon_%': r['Solar_GridCon_%'],
                    'Solar_RawCurt_%': r['Solar_RawCurt_%'], 'Solar_TotLoss_%': r['Solar_TotLoss_%'],
                    'Solar_%': r['Solar_%'], 'Wind+Solar_%': r['Wind+Solar_%'],
                })
        summary = pd.DataFrame(summary_rows)
        summary.to_csv(summary_path, index=False)
        combined_results = pd.concat(all_results, ignore_index=True)
        combined_numeric = [c for c in combined_results.columns if c not in {'Scenario', 'Data_Type'}]
        combined_results[combined_numeric] = combined_results[combined_numeric].apply(pd.to_numeric, errors='coerce').round(2)
        combined_results.to_csv(
            os.path.join(SCENARIO_OUTPUT_DIR, "all_scenarios_by_year.csv"),
            index=False, float_format='%.2f')
        if BACKCAST_SCENARIO_TREND and backcast_store:
            pd.concat([v[0].assign(Scenario=k) for k, v in backcast_store.items()], ignore_index=True).round(3).to_csv(
                os.path.join(SCENARIO_OUTPUT_DIR, "all_scenarios_backcast.csv"), index=False)
        print("\n====================================================================")
        print(" SCENARIO SUMMARY")
        print("====================================================================")
        print(summary[summary['Year'] == 2050][['Scenario', 'GridCon_%', 'GridCon_Low_%', 'GridCon_High_%',
                                                'Con_IE_%', 'Con_NI_%', 'RawCurt_%', 'Wind_%_SEM', 'Solar_Cap_GW',
                                                'Solar_GridCon_%', 'Solar_RawCurt_%', 'Solar_%',
                                                'Wind+Solar_%']].to_string(index=False))
        print(">> Backcast (same for every scenario): forecast starting limits run back over history; "
              f"see section 2 and '{os.path.join(SCENARIO_OUTPUT_DIR, 'backcast_results.csv')}'.")
        print(f"\n>> Summary (2030/2040/2050) saved to '{summary_path}'; every year of every "
              f"scenario saved to '{os.path.join(SCENARIO_OUTPUT_DIR, 'all_scenarios_by_year.csv')}'")
    else:
        run_scenario(interactive_scenario(), os.path.join(SCENARIO_OUTPUT_DIR, "interactive"), make_charts=True)

if __name__ == "__main__":
    run_demonstrator()
