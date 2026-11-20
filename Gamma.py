"""
================================================================================
IRELAND (SEM) - ADVANCED WIND + SOLAR + STORAGE CAPACITY + ZONAL HEADROOM DEMO
(CONSTRAINT + CURTAILMENT MODEL, WITH USER INPUTS FOR SNSP AND BUILD RATES IN scenariosXLSX.xlsx)
================================================================================

PURPOSE & METHODOLOGY:
GAMMA.py Version 13  with transition parameters
Also demonstrates why static or linear loss assumptions fail when modeling large-scale 
offshore or onshore wind build-outs in TIMES/TIM Models. 
Model incorporating decarbonisation/electrification demand scaling (+2.2TWh/yr, required rate for a 2050 net zero target)

CAPACITY TIMING & COD RAMP ENGINE:
- 2026 Baseline anchored at exact current fleet capacity for the all island SEM (6.51 GW).
- New build capacity ramps linearly during construction/commissioning so that
  the first full annual build increment is completely online by end-2027, and maintains a user-input build rate. 
- Full 15-minute weather granularity and seasonal profile preserved across all forecast years.

DISPATCH ENGINE:
- Usable wind is summed directly from the 15-minute dispatch (constraint, then SNSP), and
  capacity factor is reported from it. Monthly charts are summed from the same intervals.

CONSTRAINT MODEL (ZONAL HEADROOM):
- Constraint uses the same lognormal expected-constraint formula as V8, but the limit is a
  per-zone headroom H_z(y) instead of a single IE/NI L grown by reinforcement %/yr.
- Zones: NW, W, MID, SW, SE (IE onshore), NI, and OFFSHORE. Offshore availability is added
  into the SE bucket (shared headroom): avail_SE_eff = avail_SE + avail_OFFSHORE.
- Base headrooms are IE/NI L0 split across IE zones by fleet dd_zone shares; grown using
  Data_inputs/zonal_headroom_by_year.csv (from published TID/TYTFS/TDPNI reinforcement path).
- headroom_curve = reinforcement_pct instead grows each zone's 2026 headroom by the scenario's
  ie_reinforcement_pct / ni_reinforcement_pct each year, as V8 grew L. Optional headroom_scale.
- Constraint is applied first; then SNSP curtailment (unchanged from V8).

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
9. Innterconnector Extreme Boundary Cases
================================================================================
"""



import builtins
import os
import re
import sys
import time
import traceback
import warnings
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.special import ndtr
from scipy.optimize import brentq, minimize_scalar

# =============================================================================
# CONSOLE AND RUN LOG
# =============================================================================
# The console shows a short readout (say): inputs, backcast, progress of each scenario, errors and
# the headline results. Every detailed table goes to RUN_LOG in SCENARIO_OUTPUT_DIR. Set
# CONSOLE_DETAIL = True to also see the detailed tables on screen.
CONSOLE_DETAIL = False
RUN_LOG = "run_log.txt"
_LOG = {'file': None}


def _to_log(text):
    if _LOG['file'] is not None:
        _LOG['file'].write(text)
        _LOG['file'].flush()


def print(*args, sep=' ', end='\n', file=None, flush=False):
    """Detailed output: always to the run log, to the console only when CONSOLE_DETAIL is True."""
    if file is not None:
        return builtins.print(*args, sep=sep, end=end, file=file, flush=flush)
    text = sep.join(str(a) for a in args) + end
    _to_log(text)
    if CONSOLE_DETAIL:
        builtins.print(text, end='', flush=flush)


def say(*args, end='\n'):
    """Console readout for the person running the model (also written to the run log)."""
    text = ' '.join(str(a) for a in args) + end
    _to_log(text)
    try:
        builtins.print(text, end='', flush=True)
    except UnicodeEncodeError:          # consoles that can't show a character get a '?' instead of a crash
        enc = getattr(sys.stdout, 'encoding', None) or 'ascii'
        builtins.print(text.encode(enc, errors='replace').decode(enc), end='', flush=True)


def _warning_to_log(message, category, filename, lineno, file=None, line=None):
    _to_log(f"{category.__name__}: {message} ({os.path.basename(filename)}:{lineno})\n")


def fmt_secs(s):
    return f"{s:.0f} s" if s < 90 else f"{s / 60:.1f} min"

# =============================================================================
# CONSTRAINT MODEL SETTINGS
# =============================================================================
REGIONS = ['IE', 'NI']
REGION_NAMES = {'IE': 'Republic of Ireland', 'NI': 'Northern Ireland'}
# Zonal headroom zones (OFFSHORE has no own headroom — shares SE)
IE_ZONES = ['NW', 'W', 'MID', 'NE', 'SW', 'SE']
HEADROOM_ZONES = IE_ZONES + ['NI']          # zones with a headroom series
ALL_GEN_ZONES = HEADROOM_ZONES + ['OFFSHORE']
# Zonal wind dispatch-down history (constraint / curtailment % by zone, monthly and annual) and each
# IE zone's installed MW. Sets the IE zone capacity split and calibrates each zone's 2026 headroom
# to HEADROOM_CALIBRATION_YEAR; the other years are the out-of-sample zonal backcast.
ZONAL_HISTORY_FILE = "zonal_dd_percentages.csv"
HEADROOM_CALIBRATION_YEAR = 2025
# NI headroom calibration years (issue #3). NI constraint depends heavily on how the conventional
# fleet is run: EirGrid/SONI attribute the 2024 peak (26.4%) partly to a must-run CCGT, summer
# transmission outages, OCGT testing and higher GB imports, and the 2025 fall (18.6%) primarily
# to a long unplanned outage of a large conventional generator (Annual Renewable Constraint and
# Curtailment Reports 2024 and 2025). Neither year alone is a clean base. Several years are
# pooled (energy-weighted). Default: 2025 only, as before; [2024, 2025] is the sensitivity.
NI_CALIBRATION_YEARS = [2025]
ZONAL_BACKCAST_CSV = "zonal_backcast_results.csv"   # written inside SCENARIO_OUTPUT_DIR
HEADROOM_FILE = "zonal_headroom_by_year.csv"   # default curve (TID/TDPNI/TYTFS path)
HEADROOM_CURVES_SUBDIR = "headroom_curves"     # named curves: Data_inputs/headroom_curves/<name>.csv
# Scenario headroom_curve aliases → file under Data_inputs/ (or headroom_curves/)
HEADROOM_CURVE_ALIASES = {
    'tid': HEADROOM_FILE,
    'tdpni': HEADROOM_FILE,
    'tytfs': HEADROOM_FILE,
    'published': HEADROOM_FILE,
    'default': HEADROOM_FILE,
    # Fixed 2026 headroom: use headroom_curve = reinforcement_pct with 0 %/yr
}
DEFAULT_HEADROOM_CURVE = "TID"              # scenario default: published TID path
REINFORCEMENT_CURVE = "reinforcement_pct"   # V8-style: 2026 headroom x (1 + ie/ni_reinforcement_pct)^years
# Issue #2: build-path alternative. 2026 headroom + years x ie/ni_reinforcement_mw_per_year (the IE
# MW/yr is split over the IE zones in proportion to their 2026 headroom).
REINFORCEMENT_MW_CURVE = "reinforcement_mw"
HYBRID_TID_2035_CURVE = "tid_to_2035_then_pct"  # published TID path through 2035, then scenario %/yr
# Named one-off steps, applied on top of any built-in headroom curve. Scenario column
# reinforcement_steps, e.g. "NI:2032:950" or "NI:2032:950; SE:2030:400" (zone:first year:+MW).
# Example: North-South interconnector, 300 to 1,250 MW from October 2031 (SEAI NEP26), as +950 MW
# of NI headroom from 2032. Not applied unless a scenario names it.
OFFSHORE_PROFILE_SCALE = 1.0                # kept for compatibility; see OFFSHORE_CF_REFERENCE below
# Offshore wind yield. Offshore availability uses the same all-island weather (per-GW availability
# shape) as onshore, multiplied by a factor k and capped at installed capacity in each interval, as in
# the regulators' SEM PLEXOS model (NERA 2021, s.6.2). k is set so that offshore availability averages
# OFFSHORE_CF_REFERENCE in the reference weather year 2020, the year of EirGrid's ECP constraint studies,
# whose vendor offshore profile implies an available capacity factor of about 40% (GSS-1 workbook,
# project extract 25 Oct 2026). The same k is applied to every weather year. Until 11 Nov 2026 offshore
# used the onshore shape unscaled (k = 1). Override with GAMMA_OFFSHORE_CF (e.g. 0.45, EirGrid's GCS value).
OFFSHORE_CF_REFERENCE = float(os.environ.get('GAMMA_OFFSHORE_CF', '0.40'))
OFFSHORE_CF_REFERENCE_YEAR = 2020
OFFSHORE_YIELD_K = 1.0                      # solved at run time from the weather data
DEFAULT_HEADROOM_SCALE = 1.0                # scenario sensitivity multiplier
DEFAULT_BUILD_RATE_WIND_OFFSHORE = 0.0      # GW/yr; scenarios may override
# Offshore connection (issue #1). 'own': offshore wind connects through dedicated 220/400 kV
# export infrastructure and has its own headroom, OFFSHORE_CONNECTION_RATIO x installed
# offshore capacity, so it does not compete for onshore zonal headroom. 'shared': the earlier
# treatment, offshore shares SE headroom (rates) or its ECP area's zone (pipeline); kept as a
# sensitivity. Offshore output still counts towards SNSP and min-gen curtailment either way.
DEFAULT_OFFSHORE_CONNECTION = 'own'
OFFSHORE_CONNECTION_RATIO = 1.0
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
# Prefer scenarios.csv if present (supports headroom_curve); else scenariosxlsx.xlsx
SCENARIO_FILE_CANDIDATES = ("scenariosXLSX.xlsx", "scenarios.xlsx")
SCENARIO_FILE = "scenariosXLSX.xlsx"
SCENARIO_SHEET = "Scenarios"
SCENARIO_OUTPUT_DIR = "scenario_outputs"
SCENARIO_SUMMARY_CSV = "scenario_summary.csv"   # written inside SCENARIO_OUTPUT_DIR
# Curtailment and capacity-factor tracking, actual years then forecast (per scenario and all scenarios)
EVALUATION_CSV = "evaluation_curtailment_cf.csv"
EVALUATION_CHART = "evaluation_curtailment_cf.png"
# Unambiguous names for the energy shares (2 Nov 2026). The old names stay in every output as
# aliases. "Overall" here never means SEAI's "RES Overall": state the denominator.
SHARE_COLUMN_NAMES = {
    'Overall_Fossil_Fuel_Pct': 'Primary_Fossil_Share_Pct',                  # % of primary energy
    'Overall_Renewables_Pct': 'Primary_Renewables_Share_Pct',               # % of primary energy
    'Overall_Imported_Electricity_Pct': 'Primary_Imported_Electricity_Share_Pct',
    'RES_Overall_RED_%': 'Modelled_RES_Overall_Gross_Final_Pct',            # % of gross final energy (RED)
    'RES_E_RED_%': 'Modelled_RES_E_Pct',                                    # % of electricity demand, wind+solar+storage
    'Final_Fossil_Fuel_Pct': 'Domestic_Final_Energy_Fossil_Pct',            # domestic final-energy accounting
    'Final_Renewables_Pct': 'Domestic_Final_Energy_Renewables_Pct',         # not RES Overall
}
DD_ALL_ISLAND_FILES = {'Wind': "system_dd_hourly_all_island.csv", 'Solar': "system_dd_hourly_all_island_solar.csv"}
SCENARIO_CHARTS = os.environ.get('GAMMA_CHARTS', '1') == '1'  # set False (or GAMMA_CHARTS=0) for faster CSV-only runs
DEFAULT_BUILD_RATE_GW = 1.87 / (8760 * 0.40 / 1000.0)   # ~0.534 GW/yr
DEFAULT_SNSP_PCT = 75.0
DEFAULT_DEMAND_RATE_TWH_PER_YEAR = 1.87  # legacy fallback only
DEFAULT_BACKGROUND_DEMAND_GROWTH_TWH_PER_YEAR = 0.50
DEFAULT_HEAT_DEMAND_GROWTH_TWH_PER_YEAR = 0.15
DEFAULT_TRANSPORT_DEMAND_GROWTH_TWH_PER_YEAR = 0.25
# Overall-transition calibration: 2025 physical baseline, 2026 percentage anchor.
TRANSITION_BASE_YEAR = 2026
ALL_ISLAND_HEAT_DEMAND_TWH = 70.6      # IE 41.3 (SEAI NEP 2026 results dataset) + NI 29.3 (DfE: heat 56% of 52.4 TWh final energy); as in paper Section 4.4
ALL_ISLAND_TRANSPORT_DEMAND_TWH = 62.2  # land transport: IE 46.5 (SEAI, excl. aviation and navigation) + NI 15.7 (DESNZ road); paper Section 4.4
BASE_HEAT_ELECTRICITY_TWH_2025 = 1.0
BASE_TRANSPORT_ELECTRICITY_TWH_2025 = 1.5
HEAT_COP = 3.5
# Heat-pump demand profile (Cian's review). Heat-pump electricity added after 2026 follows hourly
# heating degree hours from Met Eireann hourly temperature (Dublin Airport, station 532) instead of
# today's demand shape: weight = max(0, base - T) / COP(T), with COP falling HEAT_COP_SLOPE per K
# below its annual heating-weighted mean (clipped). Weather years without temperature data use
# the demand shape. Assumptions: one station stands for the island; no diurnal heating schedule.
TEMPERATURE_FILE = "met_eireann_hly532_dublin_airport.csv"
HEATING_BASE_TEMP_C = 15.5
HEAT_COP_SLOPE_PER_K = 0.025
TRANSPORT_DISPLACEMENT_FACTOR = 3.0
INTERVAL_HOURS = 0.25

# Interconnectors to GB/France (issues #5, #8, #9). These enter the dispatch: exports absorb
# surplus wind and solar, imports cover part of the residual before firm plant, and the
# capacity credit gives a second firm figure net of interconnectors (Firm_Capacity_Net_of_IC_Credit_GW). Capacities and dates follow SEAI NEP26
# (Appendix 1): existing EWIC + Moyle + Greenlink 1,450 MW; Celtic 700 MW from April 2028;
# MaresConnect 750 MW from January 2031. Energisation years may be decimal (2028.25 = April);
# a year is credited with the fraction of it the link is in service. Scenario columns override.
# Interconnector flows in the 15-minute dispatch. False (decision of 24 Oct 2026): no imports or
# exports in the dispatch; firm plant covers every shortfall and surplus is curtailed, as before
# issue #5. Interconnectors appear only in the chart-only sensitivities (50% import / max export).
# GAMMA_IC_DISPATCH=1 turns them on for a sensitivity run without editing this file.
INTERCONNECTOR_DISPATCH = os.environ.get('GAMMA_IC_DISPATCH', '0') == '1'
# Imported electricity in the Overall Transition Progress shares. Default 0 from 12 November 2026:
# the shares count only the imports in the dispatch, which are zero in the main runs
# (INTERCONNECTOR_DISPATCH off), so the headline shares hold no imported electricity.
# GAMMA_IMPORT_SHARE=4 restores the fixed 4% allowance used before (fossil and renewables scaled
# to 96%); it applies to runs without interconnector dispatch only.
FIXED_IMPORT_SHARE_PCT = float(os.environ.get('GAMMA_IMPORT_SHARE', '0.0'))
# Sensitivity switches (referee round 2, 12 November 2026). Defaults reproduce the published results.
# Demand growth since 2026 that is neither heat-pump nor transport load (underlying growth, mostly
#   data centres) is added as flat load. Default from 12 November 2026 (group decision);
#   GAMMA_FLAT_GROWTH=0 scales today's demand shape instead and reproduces earlier results.
FLAT_UNDERLYING_GROWTH = os.environ.get('GAMMA_FLAT_GROWTH', '1') == '1'
# Primary energy basis for the headline shares (the red box). Fuels for heat and transport are
# counted as delivered; electricity from firm plant is counted as the fuel burnt to make it, at
# the firm fleet efficiency below; wind, solar and heat-pump ambient heat are counted as the
# energy they deliver (physical energy content method, as SEAI and Eurostat use). Aviation and
# marine fuels are outside the model.
#
# Firm fleet efficiency (lower heating value basis, as the SEAI energy balance). Each weather
# year's 15-minute firm output is split by a screening-curve rule: output at levels needed for
# at least FIRM_PEAKER_MAX_HOURS a year is the baseload tranche (CCGT), output above that level
# is the peaking tranche (OCGT and engines). Fleet efficiency is the energy-weighted result, so
# it falls as firm plant moves from baseload to peaking duty. Part-load and start-up losses
# inside each tranche are not modelled. Values are placeholders for group agreement.
FIRM_CCGT_EFFICIENCY = 0.55
FIRM_PEAKER_EFFICIENCY = 0.38
FIRM_PEAKER_MAX_HOURS = 1500
# Firm plant on green hydrogen instead of gas: the same turbines and tranches, burning hydrogen
# made by electrolysis at ELECTROLYSER_EFFICIENCY (LHV). At a fleet efficiency of 50% each TWh
# of firm electricity needs 1 / (0.50 x 0.70) = 2.9 TWh of electricity for electrolysis; at 38%
# (all peaking) it needs 3.8 TWh. Physical quantities only; costs are for the second paper.
ELECTROLYSER_EFFICIENCY = 0.70
# Gas supply check. All gas quantities are daily energy on a gross calorific value (GCV) basis,
# as Gas Networks Ireland publishes capacity and demand. Moffat serves IE, NI and the Isle of Man.
# Within-day linepack is not modelled, so the test is daily energy against daily capacity.
# Supply by gas year from GNI Network Development Plan 2025 (CRU consultation copy): Moffat and
# Corrib maximum daily supply from Table A2-13 and Table 7-1; biomethane from Table 7-2, Low
# scenario (TWh a year, injected evenly), as agreed by Mark on 6 Nov 2026. Moffat rises from
# 433.3 to 475 GWh/d with the Scottish compressor upgrades committed for winter 2027/28. Not
# included: the EMD compressors at Beattock and Brighouse Bay (not committed), the State
# strategic gas emergency reserve (floating LNG, for supply disruption only) and any limit on
# supply from Great Britain. After 2034/35 Moffat and biomethane hold and Corrib keeps falling at
# its 2033/34 to 2034/35 rate. A winter in calendar year Y belongs to gas year (Y-1)/Y.
GAS_SUPPLY_GAS_YEARS = list(range(2026, 2036))   # gas years 2025/26 .. 2034/35, by end year
GAS_MOFFAT_GWH_PER_DAY = [433.3, 450.0, 475.0, 475.0, 475.0, 475.0, 475.0, 475.0, 475.0, 475.0]
GAS_CORRIB_GWH_PER_DAY = [25.7, 22.0, 19.9, 18.7, 16.3, 14.5, 13.1, 11.7, 10.6, 9.8]
GAS_BIOMETHANE_TWH_LOW = [0.1, 0.5, 0.6, 0.9, 1.2, 1.7, 2.2, 2.7, 3.2, 3.6]
GAS_LHV_PER_GCV = 0.90                  # plant efficiencies are LHV; capacity and demand are GCV
# Non-power gas, all-island (GWh/d, GCV): base + slope x heating degree days (Dublin Airport daily
# mean, base HEATING_BASE_TEMP_C). Fitted to IE non-power gas: Q1 2025 mean 71 GWh/d (CSO) at
# 9.24 HDD and 112.5 GWh/d on 8 Jan 2025 (41% of 274.4; GNI) at 18.02 HDD, then scaled by
# 1.377 for NI distribution (42.4 GWh/d on 8 Jan 2025; GMO NI GTO). The whole non-power term is
# scaled down as Gamma electrifies heat, so heat is not counted as both gas and electricity.
GAS_NONPOWER_BASE_GWH_PER_DAY = 37.6
GAS_NONPOWER_GWH_PER_HDD = 6.51
GAS_IOM_GWH_PER_DAY = 5.0               # Isle of Man, supplied through the same system (placeholder)
# Firm output not burning gas (MW). Hydro, biomass and waste run first (placeholder, all-island);
# Moneypoint on heavy fuel oil covers the top of the firm residual until its last year.
GAS_NONGAS_FIRM_MW = 400.0
GAS_MONEYPOINT_OIL_MW = 855.0
GAS_MONEYPOINT_OIL_LAST_YEAR = 2029
# Observed full-system gas day for the 2026 check (GNI Winter Outlook 2025; GMO NI GTO).
GAS_VALIDATION_DAY = (2025, 1, 8)
GAS_VALIDATION_TOTAL_GWH = 365.6        # IE 274.4 + NI 85.8 + IoM 5.4
GAS_VALIDATION_POWER_GWH = 205.3        # IE 161.9 (59%) + NI 43.4


def gas_supply_parts(year):
    """(Moffat, Corrib, biomethane) daily supply in GWh/d, GCV, for the winter of calendar year."""
    years = GAS_SUPPLY_GAS_YEARS
    i = min(max(year, years[0]), years[-1]) - years[0]
    moffat = GAS_MOFFAT_GWH_PER_DAY[i]
    bio = GAS_BIOMETHANE_TWH_LOW[i] * 1000.0 / 365.0
    corrib = GAS_CORRIB_GWH_PER_DAY[i]
    if year > years[-1]:
        corrib *= (GAS_CORRIB_GWH_PER_DAY[-1] / GAS_CORRIB_GWH_PER_DAY[-2]) ** (year - years[-1])
    return moffat, corrib, bio


def gas_supply_gwh_per_day(year):
    """Daily gas supply (GWh/d, GCV): Moffat plus Corrib plus biomethane."""
    return sum(gas_supply_parts(year))


def gas_power_fuel_mw(firm_mw, year):
    """Gas burnt for power (MW, GCV) and oil-fired output (MW electric) for a 15-minute firm series.

    Non-gas plant takes the first GAS_NONGAS_FIRM_MW. The rest is split by the screening-curve
    band used for the fleet efficiency: output up to the band burns at FIRM_CCGT_EFFICIENCY,
    output above it at FIRM_PEAKER_EFFICIENCY, except the part Moneypoint covers on oil.
    """
    g = np.maximum(0.0, np.asarray(firm_mw, dtype=float) - GAS_NONGAS_FIRM_MW)
    if g.size == 0:
        return g, g
    k = int(np.ceil(g.size * min(1.0, FIRM_PEAKER_MAX_HOURS / 8760.0)))
    k = max(1, min(g.size, k))
    band = np.partition(g, g.size - k)[g.size - k]
    base = np.minimum(g, band)
    peak = g - base
    oil_cap = GAS_MONEYPOINT_OIL_MW if year <= GAS_MONEYPOINT_OIL_LAST_YEAR else 0.0
    oil = np.minimum(peak, oil_cap)
    fuel_lhv = base / FIRM_CCGT_EFFICIENCY + (peak - oil) / FIRM_PEAKER_EFFICIENCY
    return fuel_lhv / GAS_LHV_PER_GCV, oil

# Full decarbonisation: the first year the fossil share of primary energy falls to or below this.
DECARBONISED_FOSSIL_PCT = 10.0
DECARBONISED_FOSSIL_PCT_STRICT = 5.0
EXISTING_INTERCONNECTOR_CAPACITY_MW = 1450.0
CELTIC_INTERCONNECTOR_CAPACITY_MW = 700.0
MARES_INTERCONNECTOR_CAPACITY_MW = 750.0
DEFAULT_CELTIC_ENERGISED_YEAR = 2028.25
DEFAULT_MARES_ENERGISED_YEAR = 2031.0
# Share of interconnector capacity usable for exports when Ireland has surplus wind/solar.
# GB wind is correlated with Irish wind, so exports are not always possible. Agreed by the
# group 24 Oct 2026 (assumption, not measured).
DEFAULT_IC_EXPORT_AVAILABILITY = 0.5
# Share of interconnector capacity usable for imports when Ireland has a firm residual.
# Agreed by the group 24 Oct 2026 (assumption, not measured).
DEFAULT_IC_IMPORT_AVAILABILITY = 0.7
# Capacity credit (de-rating) given to interconnectors at the system peak when sizing firm
# capacity. Agreed by the group 24 Oct 2026 (assumption, not measured).
DEFAULT_IC_CAPACITY_CREDIT = 0.5
# Firm capacity reserve: largest single infeed. The largest unit or link is taken as this
# minimum, or the largest interconnector in service if larger (Celtic 700, Mares 750 MW).
LARGEST_UNIT_INFEED_MW = 500.0
# Operating reserve added on top of the largest single infeed (agreed 24 Oct 2026).
OPERATING_RESERVE_MW = 500.0
# Percentile of the 15-minute firm residual reported beside the maximum (issue #8)
FIRM_RESIDUAL_PERCENTILE = 99.9
# Conservative aggregate BESS throughput safeguard. The original V8 allows
# geographically separate batteries to charge and discharge in the same interval,
# consistent with a multi-node interpretation. To prevent implausibly repeated
# cycling, total daily charge-input plus discharge-output energy is capped at
# this multiple of installed storage energy. A value of 1.0 means a 10 GWh fleet
# can move at most 10 GWh gross across charging and discharging during one day.
MAX_DAILY_BESS_GROSS_THROUGHPUT_PER_MWH = 1.0  # compatibility only; Gamma code aggregate dispatch does not use this cap

# Minimum Units Online (MUON) assumptions.
# The floor counts the jurisdictional minimums only: 4 conventional units in IE plus 2 in NI.
# The all-island requirement is 7 units; the seventh may be in either jurisdiction and is not
# counted here. Each unit is assumed to hold 150 MW (authors' assumption, no published source).
DEFAULT_MUON_UNITS_IE = 4
DEFAULT_MUON_UNITS_NI = 2
MUON_MIN_GEN_PER_UNIT_MW = 150.0
DEFAULT_MUON_FLOOR_MW = (
    DEFAULT_MUON_UNITS_IE + DEFAULT_MUON_UNITS_NI
) * MUON_MIN_GEN_PER_UNIT_MW  # 6 x 150 MW = 900 MW

# redbox 4pc fixed 25-10-26

# Standalone, non-hybrid battery defaults. Storage charges only from energy that
# remains operationally curtailed AFTER regional grid constraints are applied.
DEFAULT_STORAGE_POWER_BUILD_RATE_MW = 0.0
DEFAULT_STORAGE_ENERGY_BUILD_RATE_MWH = 0.0
DEFAULT_STORAGE_POWER_2026_MW = 0.0
DEFAULT_STORAGE_ENERGY_2026_MWH = 0.0
DEFAULT_STORAGE_CHARGE_EFFICIENCY = 0.9
DEFAULT_STORAGE_DISCHARGE_EFFICIENCY = 0.9
DEFAULT_STORAGE_INITIAL_SOC_PCT = 50.0  # fixed; not a scenario input (affects only the first day of each weather year)
CHART_DPI = 600  # resolution of saved PNG charts; 600 suits print journals (files are larger, runs slightly slower)
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
# Solar capacity factor on an MEC basis: observed 13.7% for the dispatch-reporting fleet over the
# full years 2024-2025 (analysis/build_solar_capacity.py; IE 13.1-14.8%, NI 11.0-12.1%). Was 0.11.
SOLAR_CAPACITY_FACTOR = 0.137
# Month-end installed solar (MW, IE / NI) from the SONI/EirGrid System and Renewable Data Summary
# Report project lists. When present, the 2026 solar capacity and IE share come from its latest
# month, and actual solar CF is reported in the evaluation table.
SOLAR_CAPACITY_FILE = "solar_capacity_monthly.csv"
SOLAR_CAPACITY_2026_GW = None             # None = estimate from the last 12 months of solar
                                          # availability records / (capacity factor x 8760 h)
SOLAR_CAPACITY_FALLBACK_GW = 2.0          # used only if there are no solar records
DEFAULT_SOLAR_BUILD_RATE_GW = 0.0         # GW/yr when a scenario leaves it blank          # 0.25 = stop if the ratio is outside 0.8-1.25

# =============================================================================
# ZONAL BUILD FROM THE ECP-GSS-1 GENERATOR LIST (scenario capacity_source = pipeline)
# =============================================================================
# Each project's zone comes from its ECP area code (A-K) via AREA_ZONE_MAP_FILE. "connected"
# projects are already in the 2026 base; "due to connected" projects are added evenly from
# PIPELINE_START_YEAR. At pipeline_build_pct = 100 (normal) the whole pipeline is online by
# pipeline_target_year (default 2050); 150 builds 1.5x as fast, 75 at three-quarter speed (so
# only 75% is online by {target_year}). Once the pipeline is complete the scenario's GW/yr (and storage
# MW/yr) build rates carry on, split across zones like the pipeline.
# Offshore wind shares the headroom of the zone its own area maps to. NI is not in the list,
# so NI keeps its GW/yr rates. Pipeline batteries are reported by zone; dispatch stays all-island.
GENERATION_LIST_FILE = "ECP-GSS-1-IE-Generation-List.xlsx"
AREA_ZONE_MAP_FILE = "area_zone_map.csv"
ZONE_ALIASES = {}                         # zone name -> model zone, for names that differ
CAPACITY_SOURCES = ('rates', 'pipeline')
DEFAULT_CAPACITY_SOURCE = 'rates'
PIPELINE_START_YEAR = 2027
DEFAULT_PIPELINE_TARGET_YEAR = 2050       # normal (100%) build: whole pipeline online by this year
DEFAULT_PIPELINE_BUILD_PCT = 100.0        # speed of the pipeline build, % of normal
# The list hides every pipeline battery's MWh ('*'). Its sheet note gives the pipeline total as
# 15,217.75 MWh for 5,632 MW, so that average duration is applied to each pipeline battery.
PIPELINE_BATTERY_HOURS = 15217.75 / 5632.0

# Validation: connected IE onshore wind in the list vs CapacityByYear 2026 ROI MW.
MAX_CONNECTED_CAPACITY_MISMATCH = 0.10
SCENARIOS_SWITCHED_OFF = set()   # scenario names (lower case) with run = no in the workbook
VALIDATION_REPORT_CSV = "validation_report.csv"   # written inside SCENARIO_OUTPUT_DIR
CAPACITY_BY_ZONE_CSV = "capacity_by_zone_year.csv"


def firm_tranche_split(firm_mw):
    """Split a firm output series (MW) into baseload and peaking energy (MW x intervals).

    Screening-curve rule: a MW level belongs to the baseload tranche if firm output reaches it
    in at least FIRM_PEAKER_MAX_HOURS a year (scaled to the series length); output above that
    level is the peaking tranche.
    """
    f = np.asarray(firm_mw, dtype=float)
    if f.size == 0:
        return 0.0, 0.0
    k = int(np.ceil(f.size * min(1.0, FIRM_PEAKER_MAX_HOURS / 8760.0)))
    k = max(1, min(f.size, k))
    band_mw = np.partition(f, f.size - k)[f.size - k]   # k-th largest value
    baseload = float(np.minimum(f, band_mw).sum())
    return baseload, float(f.sum()) - baseload


def fleet_efficiency(peaking_share):
    """Energy-weighted firm fleet efficiency (LHV) for a peaking share of firm output (0-1)."""
    p = np.clip(peaking_share, 0.0, 1.0)
    return 1.0 / ((1.0 - p) / FIRM_CCGT_EFFICIENCY + p / FIRM_PEAKER_EFFICIENCY)


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
    """Expected constrained MW in an interval with available output x: E[max(0, x - H*eta)],
    ln(eta) ~ N(0, sigma^2), so H is the median effective limit. Closed form (paper eq. 3):
    x*Phi(a) - H*exp(sigma^2/2)*Phi(a - sigma), a = ln(x/H)/sigma.
    Before 8 Nov 2026 the code used x*Phi(a + sigma/2) - H*exp(sigma^2/2)*Phi(a - sigma/2),
    which is not the expectation of any lognormal and went negative for x below about 0.3-0.4 H."""
    x = np.maximum(np.asarray(avail_mw, dtype=float), 1e-6)
    a = np.log(x / limit_mw) / sigma
    raw = x * ndtr(a) - limit_mw * np.exp(0.5 * sigma ** 2) * ndtr(a - sigma)
    return np.clip(calib * raw, 0.0, x)


def operational_ceiling_mw(system_demand_mw, snsp_fraction, muon_floor_mw, forced_import_mw=0.0):
    """Ceiling on all non-synchronous output in an interval, less recorded HVDC imports.

    system_demand_mw is native demand + BESS charging + exports (the SNSP denominator).
    The ceiling covers every MW of wind and solar, including the MW charging batteries or
    being exported, plus BESS discharge and imports. Returns (ceiling, SNSP part, MUON part).
    """
    snsp_mw = max(0.0, snsp_fraction * system_demand_mw - forced_import_mw)
    muon_mw = max(0.0, system_demand_mw - forced_import_mw - muon_floor_mw)
    return min(snsp_mw, muon_mw), snsp_mw, muon_mw


def dispatch_interval(native_demand_mw, post_constraint_vre_mw, charge_mw, discharge_cap_mw,
                      snsp_fraction, muon_floor_mw, forced_import_mw=0.0,
                      export_cap_mw=0.0, import_cap_mw=0.0):
    """One quarter-hour of wind, solar, BESS and interconnector dispatch.

    charge_mw is the battery charging already sized by the access rule; it is taken from
    post-constraint wind and solar. Since 22 November 2026 the MW charging the battery
    count against the SNSP and MUON ceiling as well as adding to its denominator, so

        direct + charge + export_vre + discharge + imports + recorded imports
            <= min(f (D + C + E), D + C + E - MUON floor).

    Before, direct wind and solar could use the whole ceiling on top of the charging MW,
    which let SNSP exceed its limit and synchronous output fall below the floor whenever the
    fleet charged. discharge_cap_mw is the power and state-of-charge limit on discharge.
    """
    f = snsp_fraction
    d = max(0.0, native_demand_mw)
    fi = max(0.0, forced_import_mw)
    post = max(0.0, post_constraint_vre_mw)
    c = min(max(0.0, charge_mw), post)
    if f < 1.0:
        # Charging alone may not take SNSP past its limit: c <= f (d + c) - fi.
        c = min(c, max(0.0, (f * d - fi) / (1.0 - f)))
    vre_after_charge = post - c

    limit, snsp_ceil, muon_ceil = operational_ceiling_mw(d + c, f, muon_floor_mw, fi)
    direct = min(vre_after_charge, max(0.0, limit - c), max(0.0, d - fi))
    curt = max(0.0, vre_after_charge - direct)

    # Exports absorb what is left, only as far as needed: the smallest E that lifts the ceiling
    # on all wind and solar (charging included) to the post-constraint output.
    export = export_vre = export_sync = 0.0
    if export_cap_mw > 0.0 and curt > 1e-9 and f > 0.0:
        needed = max((post + fi) / f, post + fi + muon_floor_mw) - (d + c)
        export = min(export_cap_mw, max(0.0, needed))
        limit, snsp_ceil, muon_ceil = operational_ceiling_mw(d + c + export, f, muon_floor_mw, fi)
        total_vre = min(post, limit)
        export_vre = min(export, max(0.0, total_vre - c - direct))
        export_sync = export - export_vre
        curt = max(0.0, vre_after_charge - direct - export_vre)
    system_demand = d + c + export

    surplus = min(curt, max(0.0, vre_after_charge - d - export_vre))

    discharge = 0.0
    if c <= 1e-9 and discharge_cap_mw > 0.0:
        used = direct + export_vre + fi
        discharge = min(
            max(0.0, discharge_cap_mw),
            max(0.0, d - fi - direct),
            max(0.0, f * system_demand - used),
            max(0.0, system_demand - muon_floor_mw - used),
        )

    imports = 0.0
    if import_cap_mw > 0.0 and c <= 1e-9 and export <= 0.0:
        used = direct + discharge + fi
        imports = min(
            import_cap_mw,
            max(0.0, d - used),
            max(0.0, f * d - used),
            max(0.0, d - muon_floor_mw - used),
        )

    nonsync = direct + c + export_vre + discharge + imports + fi
    return {
        'charge': c, 'direct': direct, 'curt': curt, 'surplus': surplus,
        'export': export, 'export_vre': export_vre, 'export_sync': export_sync,
        'discharge': discharge, 'imp': imports,
        'limit': limit, 'snspceil': snsp_ceil, 'muonceil': muon_ceil,
        'system_demand': system_demand, 'nonsync': nonsync,
        'snsppct': 100.0 * nonsync / system_demand if system_demand > 0.0 else 0.0,
    }


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
    """V8-compatible helper (kept for hindcast/backcast fallbacks). Prefer headroom_for_year."""
    ref_year = max(params['years'])
    growth = (1.0 + reinforcement_rate) ** max(0, year - ref_year)
    step_mw = sum(mw for yr, mw in steps.items() if yr <= year)
    return params['limit_mw'] * growth + step_mw


def load_zonal_history(path):
    """Zonal dispatch-down history. The file has one block per zone: a total row (zone name and its
    installed MW) followed by 'Constraints' and 'Curtailments' rows; columns are Jan..Dec then the
    year's annual figure, repeated per year. Returns (tidy frame: zone, year, month [0 = annual],
    kind [total / constraints / curtailments], pct) and {zone: installed MW}; 'IE' is the IE total."""
    raw = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
    header = [str(c).strip() for c in raw.iloc[0]]
    years = [int(c) for c in header[2:] if c.isdigit()]
    months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    cols, yi = [], 0
    for c in header[2:]:
        if c.isdigit():
            cols.append((int(c), 0))
            yi += 1
        else:
            cols.append((years[yi], months.index(c.lower()[:3]) + 1))
    rows, caps, zone = [], {}, None
    for _, r in raw.iloc[1:].iterrows():
        label = str(r[0]).strip()
        if not label:
            continue
        if label.lower() in ('constraints', 'curtailments'):
            kind = label.lower()
        else:
            zone, kind = ZONE_ALIASES.get(label, label), 'total'
            caps[zone] = float(str(r[1]).replace(',', ''))
        for (y, m), v in zip(cols, list(r[2:])):
            v = str(v).strip().rstrip('%')
            if v:
                rows.append({'zone': zone, 'year': y, 'month': m, 'kind': kind, 'pct': float(v)})
    return pd.DataFrame(rows), caps


def zone_shares_from_history(caps, roi_mw, ni_mw):
    """zone -> share_of_onshore (all-island, sums to 1) and share_of_ie_onshore (IE zones sum to 1).
    IE vs NI from CapacityByYear 2026; IE zones in proportion to the history file's installed MW."""
    total = roi_mw + ni_mw
    ie_cap = sum(caps[z] for z in IE_ZONES)
    out = {z: {'region': 'IE', 'share_of_onshore': roi_mw / total * caps[z] / ie_cap,
               'share_of_ie_onshore': caps[z] / ie_cap, 'mec_mw': caps[z]} for z in IE_ZONES}
    out['NI'] = {'region': 'NI', 'share_of_onshore': ni_mw / total, 'share_of_ie_onshore': 0.0, 'mec_mw': ni_mw}
    return out


def calibrate_headroom(avail_mw, target_pct, sigma):
    """Headroom H (MW) at which the expected constraint on this availability equals target_pct of it."""
    x = np.asarray(avail_mw, dtype=float)
    target = target_pct / 100.0 * x.sum()
    if target <= 0:
        return float(max(x.max(), 1.0) * 100)          # no recorded constraint: effectively unconstrained
    gap = lambda ln_h: expected_constraint_mw(x, np.exp(ln_h), sigma).sum() - target
    return float(np.exp(brentq(gap, np.log(1.0), np.log(max(x.max(), 1.0) * 100))))


def rebase_headroom_table(table, base):
    """Keep a curve's year-on-year path but start each zone from base[zone] (the calibrated 2026
    headroom). A zone the curve does not list (e.g. NE in the TID file) follows the IE zones' path."""
    years = sorted({y for y, _ in table})
    first = years[0]
    ie_listed = [z for z in IE_ZONES if (first, z) in table]
    out = {}
    for z in HEADROOM_ZONES:
        for y in years:
            if (first, z) in table:
                ratio = table[(y, z)] / table[(first, z)]
            else:
                ratio = sum(table[(y, zz)] for zz in ie_listed) / sum(table[(first, zz)] for zz in ie_listed)
            out[(y, z)] = base[z] * ratio
    return out


def load_zonal_headroom(path):
    """(year, zone) -> headroom_mw for HEADROOM_ZONES."""
    df = pd.read_csv(path)
    table = {}
    for r in df.itertuples():
        table[(int(r.year), str(r.zone))] = float(r.headroom_mw)
    years = sorted({y for y, _ in table})
    zones = sorted({z for _, z in table})
    return table, years, zones


def headroom_for_year(headroom_table, year, scale=1.0):
    """Return {zone: headroom_mw} for HEADROOM_ZONES; clamp year to available range."""
    years = sorted({y for y, _ in headroom_table})
    y = int(year)
    if y < years[0]:
        y = years[0]
    if y > years[-1]:
        y = years[-1]
    out = {}
    for z in HEADROOM_ZONES:
        if (y, z) in headroom_table:
            out[z] = float(headroom_table[(y, z)]) * float(scale)
        else:
            # nearest prior year
            prior = [yy for yy in years if yy <= y and (yy, z) in headroom_table]
            yy = prior[-1] if prior else years[0]
            out[z] = float(headroom_table[(yy, z)]) * float(scale)
    return out


def is_reinforcement_curve(name):
    """headroom_curve = reinforcement_pct: V8-style compound %/yr from the scenario's ie/ni_reinforcement_pct."""
    return re.sub(r'[^a-z0-9]', '', str(name).lower()) == re.sub(r'[^a-z0-9]', '', REINFORCEMENT_CURVE)


def is_reinforcement_mw_curve(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower()) == re.sub(r'[^a-z0-9]', '', REINFORCEMENT_MW_CURVE)

def is_hybrid_tid_2035_curve(name):
    """Published/rebased TID headroom to 2035, then compound scenario reinforcement rates."""
    return re.sub(r'[^a-z0-9]', '', str(name).lower()) == re.sub(r'[^a-z0-9]', '', HYBRID_TID_2035_CURVE)


def reinforcement_mw_headroom_table(base, ie_mw_per_year, ni_mw_per_year, last_year=2050):
    """(year, zone) -> headroom: 2026 headroom plus a fixed MW added each year (issue #2).
    IE MW/yr is split over the IE zones in proportion to their 2026 headroom."""
    ie_base = sum(base[z] for z in IE_ZONES) or 1.0
    table = {}
    for z in HEADROOM_ZONES:
        add = ni_mw_per_year if z == 'NI' else ie_mw_per_year * base[z] / ie_base
        for y in range(2026, last_year + 1):
            table[(y, z)] = max(1.0, base[z] + add * (y - 2026))
    return table


def parse_reinforcement_steps(text):
    """'NI:2032:950; SE:2030:400' -> [('NI', 2032, 950.0), ('SE', 2030, 400.0)]."""
    steps = []
    if text is None or str(text).strip().lower() in ('', 'nan', 'none'):
        return steps
    for part in re.split(r'[;,]', str(text)):
        part = part.strip()
        if not part:
            continue
        bits = [b.strip() for b in part.split(':')]
        if len(bits) != 3 or bits[0].upper() not in HEADROOM_ZONES:
            raise ValueError(f"reinforcement step '{part}' should be zone:year:MW with zone in {HEADROOM_ZONES}")
        steps.append((bits[0].upper(), int(float(bits[1])), float(bits[2])))
    return steps


def apply_reinforcement_steps(table, steps):
    out = dict(table)
    for zone, first_year, mw in steps:
        for (y, z) in table:
            if z == zone and y >= first_year:
                out[(y, z)] = max(1.0, out[(y, z)] + mw)
    return out


def reinforcement_headroom_table(base, ie_pct, ni_pct, last_year=2050):
    """(year, zone) -> headroom: each zone's 2026 headroom base[zone] x (1 + r)^(year - 2026), as V8
    grew L, with r = ie_reinforcement_pct for the IE zones and ni_reinforcement_pct for NI."""
    table = {}
    for z in HEADROOM_ZONES:
        r = (ni_pct if z == 'NI' else ie_pct) / 100.0
        for y in range(2026, last_year + 1):
            table[(y, z)] = base[z] * (1.0 + r) ** (y - 2026)
    return table


def resolve_headroom_curve(name_or_path):
    """Map scenario headroom_curve (TID / path / filename) to an on-disk CSV path.

    Accepts:
      - alias: TID, TDPNI, published, fixed, default
      - bare filename in Data_inputs/ or Data_inputs/headroom_curves/
      - relative/absolute path
    """
    raw = '' if name_or_path is None else str(name_or_path).strip()
    if not raw or raw.lower() in ('nan', 'none', ''):
        raw = DEFAULT_HEADROOM_CURVE
    key = re.sub(r'[^a-z0-9]', '', raw.lower())
    rel = HEADROOM_CURVE_ALIASES.get(key, raw)
    # Try alias/relative under Data_inputs first
    candidates = [
        input_path(rel),
        input_path(os.path.join(HEADROOM_CURVES_SUBDIR, raw if raw.lower().endswith('.csv') else f"{raw}.csv")),
        input_path(raw if raw.lower().endswith('.csv') else f"{raw}.csv"),
        input_path(HEADROOM_FILE),  # always allow default zonal file as last-chance for TID/published
        os.path.join(BASE_DIR, rel),
        raw,
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError(
        f"Headroom curve '{name_or_path}' not found. Tried: "
        + "; ".join(candidates[:4])
        + f". Put a CSV under Data_inputs/{HEADROOM_CURVES_SUBDIR}/ or use alias TID."
    )


# Scenario paths: optional year-by-year inputs for a scenario, read from
# Data_inputs/scenario_paths/<name>.csv and named in the scenario's 'scenario_path' column.
# A path sets values in the years it lists (straight lines between them). Before its first
# year the value moves in a straight line from the model's 2026 value; after its last year
# capacity and demand carry on at the scenario's build and demand-growth rates, and SNSP and
# minimum units stay at their last value. Any column left out of the path uses the scenario's
# ordinary inputs. Used for the EirGrid study portfolios and for the dated offshore projects
# in the historical-trend run.
SCENARIO_PATHS_SUBDIR = "scenario_paths"
PATH_COLUMNS = ('ie_onshore_gw', 'ni_onshore_gw', 'offshore_gw', 'ie_solar_gw', 'ni_solar_gw',
                'storage_mw', 'storage_mwh', 'demand_twh', 'snsp_pct', 'muon_units_ie', 'muon_units_ni')


def load_scenario_path(name):
    """Return the scenario path as a DataFrame indexed by year, or None if no path is named."""
    raw = '' if name is None else str(name).strip()
    if not raw or raw.lower() in ('nan', 'none'):
        return None
    fname = raw if raw.lower().endswith('.csv') else f"{raw}.csv"
    p = input_path(os.path.join(SCENARIO_PATHS_SUBDIR, fname))
    if not os.path.exists(p):
        raise FileNotFoundError(f"Scenario path '{raw}' not found at {p}")
    df = pd.read_csv(p, comment='#')
    df.columns = [str(c).strip().lower() for c in df.columns]
    if 'year' not in df.columns:
        raise ValueError(f"Scenario path {p} has no 'year' column")
    keep = ['year'] + [c for c in PATH_COLUMNS if c in df.columns]
    df = df[keep].dropna(subset=['year']).astype(float).sort_values('year')
    df['year'] = df['year'].astype(int)
    return df.set_index('year')


def parse_weather_years(text, available):
    """'2020' or '2019-2025' or '2014,2020' -> list of available weather years; blank -> all."""
    raw = '' if text is None else str(text).strip()
    if not raw or raw.lower() in ('nan', 'none', 'all'):
        return list(available)
    years = set()
    for part in re.split(r'[,;\s]+', raw):
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            years.update(range(int(float(a)), int(float(b)) + 1))
        else:
            years.add(int(float(part)))
    chosen = [y for y in available if y in years]
    if not chosen:
        raise ValueError(f"weather_years '{raw}' matches none of the weather years {list(available)}")
    return chosen


# Validation checks recorded during a run: one row per check, written to VALIDATION_REPORT_CSV.
# status is PASS, WARN or FAIL. Any FAIL in the input checks stops the run before the forecast.
VALIDATION = []


def record_check(stage, scenario, check, status, detail=''):
    VALIDATION.append({'Stage': stage, 'Scenario': scenario, 'Check': check,
                       'Status': status, 'Detail': detail})
    if status == 'FAIL':
        say(f"      FAIL {scenario + ': ' if scenario else ''}{check} — {detail}")
    elif status != 'PASS':
        print(f"   ! {status} [{stage}{' / ' + scenario if scenario else ''}] {check}: {detail}")


def say_checks(stage, scenario=None, indent="      "):
    """One console line per stage: how many checks passed, then each warning."""
    rows = [v for v in VALIDATION if v['Stage'] == stage and (scenario is None or v['Scenario'] == scenario)]
    warn = [v for v in rows if v['Status'] == 'WARN']
    fail = [v for v in rows if v['Status'] == 'FAIL']
    say(f"{indent}checks: {sum(v['Status'] == 'PASS' for v in rows)} passed, {len(warn)} warning(s), {len(fail)} failed")
    for v in warn:
        who = f"{v['Scenario']}: " if v['Scenario'] and scenario is None else ''
        say(f"{indent}  ! {who}{v['Check']} — {v['Detail']}")


def write_validation_report(out_dir):
    path = os.path.join(out_dir, VALIDATION_REPORT_CSV)
    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame(VALIDATION, columns=['Stage', 'Scenario', 'Check', 'Status', 'Detail']).to_csv(path, index=False)
    return path


def stop_on_failures(stage, out_dir):
    """Write the report and raise if any check in this stage failed."""
    failed = [v for v in VALIDATION if v['Stage'] == stage and v['Status'] == 'FAIL']
    if failed:
        path = write_validation_report(out_dir)
        raise ValueError(f"{len(failed)} {stage} check(s) failed; see '{path}':\n"
                         + "\n".join(f"  - {v['Scenario'] or '-'}: {v['Check']}: {v['Detail']}" for v in failed))


def load_generation_list(path, area_map_path):
    """ECP-GSS-1 IE wind, solar, offshore and battery projects with a model zone each.

    Returns one row per project: name, area, node, tech (wind / solar / offshore / battery),
    status (connected / pipeline), mw, mwh, zone. Records validation checks as it goes.
    """
    stage = 'inputs'
    amap = pd.read_csv(area_map_path, dtype=str)
    amap = {str(a).strip(): ZONE_ALIASES.get(str(z).strip(), str(z).strip())
            for a, z in zip(amap['area'], amap['zone'])}
    bad_zones = sorted({z for z in amap.values() if z not in IE_ZONES})
    record_check(stage, '', 'area_zone_map zones are model zones', 'FAIL' if bad_zones else 'PASS',
                 f"unknown zones {bad_zones}; use {IE_ZONES}" if bad_zones else '')

    def clean(df):
        df = df.dropna(axis=1, how='all')
        df.columns = [re.sub(r'\s+', ' ', str(c)).strip() for c in df.columns]
        return df

    gen = clean(pd.read_excel(path, sheet_name='Wind and Solar Generation Table', header=1))
    bat = clean(pd.read_excel(path, sheet_name='Battery Generation Table', header=1))
    mec = 'Maximum Export Capacity (MW)'
    tech_map = {'wind': 'wind', 'solar': 'solar', 'offshore wind': 'offshore'}
    raw_type = gen['Generation Type'].astype(str).str.strip().str.lower()
    unknown_types = sorted(set(raw_type) - set(tech_map))
    record_check(stage, '', 'generation types recognised', 'FAIL' if unknown_types else 'PASS',
                 f"unknown types {unknown_types}" if unknown_types else '')
    w = pd.DataFrame({'name': gen['Name'], 'area': gen['Area'], 'node': gen['Node'],
                      'tech': raw_type.map(tech_map), 'status': gen['Connection Status'],
                      'mw': pd.to_numeric(gen[mec], errors='coerce'), 'mwh': np.nan,
                      'ptype': gen.get('Processing Type', pd.Series(index=gen.index, dtype=object))})
    b_mwh = pd.to_numeric(bat['Battery Capacity (MWh)'], errors='coerce')
    b = pd.DataFrame({'name': bat['Project Name'], 'area': bat['Area'], 'node': bat['Node'],
                      'tech': 'battery', 'status': bat['Connection Status'],
                      'mw': pd.to_numeric(bat[mec], errors='coerce'), 'mwh': b_mwh,
                      'ptype': bat.get('Processing Type', pd.Series(index=bat.index, dtype=object))})
    df = pd.concat([w, b], ignore_index=True)
    df = df[df['name'].notna()].copy()
    for c in ('name', 'area', 'node', 'status'):
        df[c] = df[c].astype(str).str.strip()
    df['status'] = df['status'].str.lower().map({'connected': 'connected', 'due to connected': 'pipeline',
                                                  'due to connect': 'pipeline'})
    bad_status = int(df['status'].isna().sum())
    record_check(stage, '', 'connection status recognised', 'FAIL' if bad_status else 'PASS',
                 f"{bad_status} rows not 'connected' / 'due to connected'" if bad_status else '')
    bad_mw = int((~(df['mw'] > 0)).sum())
    record_check(stage, '', 'MEC is a positive number', 'FAIL' if bad_mw else 'PASS',
                 f"{bad_mw} rows" if bad_mw else '')
    df['zone'] = df['area'].map(amap)
    unmapped = sorted(df.loc[df['zone'].isna(), 'area'].unique())
    record_check(stage, '', 'every ECP area maps to a zone', 'FAIL' if unmapped else 'PASS',
                 f"areas {unmapped} missing from {AREA_ZONE_MAP_FILE}" if unmapped else '')
    # Issue #10: a name may appear more than once when a project was processed in more than one
    # ECP batch (e.g. Ballyroe Solar: 120 MW in ECP-2.2 and a 7 MW increment in ECP-GSS1). Those are
    # separate capacity increments and are kept. Only rows repeating name, technology and
    # processing batch are flagged as possible duplicates.
    df['ptype'] = df['ptype'].astype(str).str.strip()
    dups = df[df.duplicated(['name', 'tech', 'ptype'], keep=False)]
    increments = df[df.duplicated(['name', 'tech'], keep=False) & ~df.index.isin(dups.index)]
    record_check(stage, '', 'no duplicate project rows', 'WARN' if len(dups) else 'PASS',
                 (f"{sorted(dups['name'].unique())} repeat name, technology and ECP batch (each row kept)"
                  if len(dups) else
                  (f"same name in different ECP batches kept as separate increments: "
                   f"{sorted(increments['name'].unique())}" if len(increments) else '')))
    no_mwh = (df['tech'] == 'battery') & df['mwh'].isna()
    df.loc[no_mwh, 'mwh'] = df.loc[no_mwh, 'mw'] * PIPELINE_BATTERY_HOURS
    # Issue #10: project MWh are masked in the published list; EirGrid's sheet total (15,217.75 MWh
    # for 5,632 MW) is applied as the average duration. Dispatch uses the all-island fleet total, so
    # the per-project split affects only the zonal battery reporting, not results.
    record_check(stage, '', 'battery MWh given', 'PASS',
                 (f"{int(no_mwh.sum())} batteries ({df.loc[no_mwh, 'mw'].sum():.0f} MW) have masked MWh; "
                  f"EirGrid sheet-total duration {PIPELINE_BATTERY_HOURS:.2f} h applied (fleet total exact; "
                  f"zonal split approximate)") if no_mwh.any() else '')
    return df.reset_index(drop=True)


def pipeline_mw_by_zone(gen_list):
    """{tech: {zone: MW}} and battery {zone: MWh} for projects due to connect."""
    p = gen_list[gen_list['status'] == 'pipeline']
    mw = {t: p[p['tech'] == t].groupby('zone')['mw'].sum().reindex(IE_ZONES, fill_value=0.0).to_dict()
          for t in ('wind', 'solar', 'offshore', 'battery')}
    mwh = p[p['tech'] == 'battery'].groupby('zone')['mwh'].sum().reindex(IE_ZONES, fill_value=0.0).to_dict()
    return mw, mwh


def write_evaluation_outputs(evaluation_store, historical_evaluation):
    """All-scenario curtailment and capacity-factor table and a four-panel chart (actual + forecast)."""
    allev = pd.concat(evaluation_store.values(), ignore_index=True, sort=False)
    cols = ['Scenario', 'Data_Type', 'Year'] + [c for c in allev.columns if c not in ('Scenario', 'Data_Type', 'Year')]
    allev[cols].to_csv(os.path.join(SCENARIO_OUTPUT_DIR, 'all_scenarios_' + EVALUATION_CSV), index=False)
    panels = [('Wind_Delivered_CF_%', 'Wind delivered capacity factor, %'),
              ('Solar_Delivered_CF_%', 'Solar delivered capacity factor, %'),
              ('Wind_Curtailment_%', 'Wind curtailment, % of available'),
              ('Solar_Curtailment_%', 'Solar curtailment, % of available')]
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    act = historical_evaluation[historical_evaluation['Data_Type'] == 'Actual'] if len(historical_evaluation) else None
    part = (historical_evaluation[historical_evaluation['Data_Type'] == 'Actual (part year)']
            if len(historical_evaluation) else None)
    for ax, (col, title) in zip(axes.flat, panels):
        # Each forecast line starts from the last full recorded year, so it joins the black line
        # (Cian, 4 Nov 2026). Forecast years are means over the weather years; the part-year
        # record is shown on its own, unjoined, because it is seasonally biased.
        last = None
        if act is not None and col in act and act[col].notna().any():
            last = act.dropna(subset=[col]).iloc[-1]
        for name, ev_df in evaluation_store.items():
            f = ev_df[ev_df['Data_Type'] == 'Forecast']
            x, y = list(f['Year']), list(f[col])
            if last is not None and len(x) and last['Year'] < x[0]:
                x, y = [last['Year']] + x, [last[col]] + y
            ax.plot(x, y, lw=1.4, label=name)
        if last is not None:
            ax.plot(act['Year'], act[col], 'ko-', lw=1.6, ms=4, label='Actual (all-island)')
        if part is not None and col in part and part[col].notna().any():
            ax.plot(part['Year'], part[col], 'o', mfc='none', mec='k', ms=5, label='Actual, part year')
        ax.set_title(title, fontsize=11)
        ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=7, ncol=2)
    fig.suptitle('Capacity factors and curtailment by scenario\n'
                 '(curtailment excludes grid constraint; solar CF on MEC basis; forecasts are weather-year means '
                 'starting from the last full recorded year)', fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(SCENARIO_OUTPUT_DIR, EVALUATION_CHART), dpi=CHART_DPI)
    plt.close(fig)


def _run_demonstrator():
    # Read inputs and write outputs next to this script, whatever the working directory is
    # (Spyder and other IDEs don't always start in the script's folder).
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    print("=" * 90)
    print("      IRELAND (SEM) - WIND, SOLAR & STORAGE GAMMA MODEL    ")
    print("      (Zonal headroom; ECP pipeline by zone; hindcast + charts)")
    print("=" * 90)
    say("=" * 72)
    say(" GAMMA -  wind, solar & storage, zonal constraint, 2026-Target")
    say("=" * 72)
    t_step = time.time()
    say("[1/5] Loading history, weather and capacity ...", end=' ')

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

        # Hourly temperature for the heat-pump profile (optional input)
        merged['heat_weight'] = np.nan
        merged['temp_c'] = np.nan
        temp_path = input_path(TEMPERATURE_FILE)
        if os.path.exists(temp_path):
            with open(temp_path, encoding='utf-8', errors='replace') as fh:
                lines = fh.readlines()
            hdr = next(i for i, ln in enumerate(lines) if ln.lower().startswith('date,'))
            met = pd.read_csv(temp_path, skiprows=hdr, low_memory=False)
            met.columns = [c.strip().lower() for c in met.columns]
            met['t'] = pd.to_datetime(met['date'], format='%d-%b-%Y %H:%M', errors='coerce')
            met['temp'] = pd.to_numeric(met['temp'], errors='coerce')
            met = met.dropna(subset=['t', 'temp']).drop_duplicates('t').set_index('t')['temp']
            key = (pd.to_datetime(merged['datetime_utc'], format='%d/%m/%Y %H:%M', errors='coerce')
                   if 'datetime_utc' in merged else merged['parsed_date']).dt.floor('h')
            temp = key.map(met)
            merged['temp_c'] = temp.to_numpy()
            hdh = np.maximum(0.0, HEATING_BASE_TEMP_C - temp)
            t_mean = float(np.nansum(temp * hdh) / np.nansum(hdh)) if np.nansum(hdh) > 0 else 6.0
            cop_rel = np.clip(1.0 + HEAT_COP_SLOPE_PER_K * (temp - t_mean), 0.5, 1.5)
            merged['heat_weight'] = hdh / cop_rel
            covered = sorted(merged.loc[merged['heat_weight'].notna(), 'year'].unique())
            print(f">> Heat-pump profile: hourly temperature '{TEMPERATURE_FILE}' covers weather years {covered}")
        else:
            print(f">> Heat-pump profile: '{TEMPERATURE_FILE}' not found; added heat demand follows the demand shape")

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
        say(f"done ({fmt_secs(time.time() - t_step)})")
        say(f"      history {int(master_hist['year'].min())}-{int(master_hist['year'].max())}; "
            f"2026 fleet {final_2026_wind_capacity_gw:.2f} GW wind")

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
    hindcast_band_by_region = {r: 0.0 for r in REGIONS}
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
        # Issue #3: each region gets its own band from its own hindcast error. The all-island
        # band is built from the IE and NI bands applied to each region's constraint, so NI's
        # larger uncertainty is not hidden by IE.
        for reg in REGIONS:
            e_r = hind_df.loc[hind_df['Region'] == reg, 'Error_%'].dropna()
            hindcast_band_by_region[reg] = float(e_r.abs().mean()) / 100.0 if len(e_r) else hindcast_band
        print(f">> Forecast constraint bands (typical one-year-ahead error by region): "
              + ", ".join(f"{r} ±{100 * hindcast_band_by_region[r]:.0f}%" for r in REGIONS)
              + f"; all-island band = regional bands applied to each region's constraint "
              f"(all-island hindcast alone gives ±{100 * hindcast_band:.0f}%).")

    cons_params = {}
    print()
    for reg in REGIONS:
        years = CONSTRAINT_FIT_YEARS.get(reg) or fit_years_avail[reg]
        years = [y for y in years if y in fit_years_avail[reg]] or fit_years_avail[reg]
        cons_params[reg] = fit_constraint_model(dd[reg], years)
        p = cons_params[reg]
        print(f"Forecast model {reg} fitted on {years}: L = {p['limit_mw']:.0f} MW, "
              f"sigma = {p['sigma']:.2f} (used for zone sigma / hindcast only)")
    say("[2/5] Constraint model")
    say(f"      spread fitted on 2024-26: IE {cons_params['IE']['sigma']:.2f}, NI {cons_params['NI']['sigma']:.2f}")
    say(f"      rolling hindcast 2022-26: error IE +/-{100 * hindcast_band_by_region['IE']:.1f}%, "
        f"NI +/-{100 * hindcast_band_by_region['NI']:.1f}% (all-island +/-{100 * hindcast_band:.1f}%)  "
        f"-> regional bands on constraint (Constraint_Low/High)")

    # --- Zonal history: zone capacity split and checks ---
    VALIDATION.clear()
    zonal_hist, zone_caps_mw = load_zonal_history(input_path(ZONAL_HISTORY_FILE))
    missing_hist = [z for z in IE_ZONES if z not in zone_caps_mw]
    record_check('inputs', '', 'zonal history has every IE zone', 'FAIL' if missing_hist else 'PASS',
                 f"missing {missing_hist} in {ZONAL_HISTORY_FILE}" if missing_hist else
                 f"{sorted(zonal_hist['year'].unique())}")
    stop_on_failures('inputs', SCENARIO_OUTPUT_DIR)
    hist_annual = zonal_hist[(zonal_hist['month'] == 0) & (zonal_hist['kind'] == 'constraints')] \
        .pivot(index='zone', columns='year', values='pct')
    ie_cap_sum = sum(zone_caps_mw[z] for z in IE_ZONES)
    if 'IE' in zone_caps_mw:
        record_check('inputs', '', 'zone MW add up to the IE total', 'PASS' if abs(ie_cap_sum - zone_caps_mw['IE']) <= 1 else 'WARN',
                     f"zones {ie_cap_sum:.0f} MW vs IE {zone_caps_mw['IE']:.0f} MW")
        wavg = sum(hist_annual.loc[z] * zone_caps_mw[z] for z in IE_ZONES) / ie_cap_sum
        gap = (wavg - hist_annual.loc['IE']).abs().max()
        record_check('inputs', '', 'zone constraint % consistent with the IE total', 'PASS' if gap <= 0.5 else 'WARN',
                     f"capacity-weighted zones vs IE row: largest gap {gap:.2f} pts")
    zone_shares = zone_shares_from_history(zone_caps_mw, float(final_2026_capacity['ROI_MW']),
                                           float(final_2026_capacity['NI_MW']))
    # Sensitivity on the spread (identification test, analysis/sigma_identification.py): GAMMA_SIGMA_IE /
    # GAMMA_SIGMA_NI fix sigma; headrooms are then recalibrated so 2025 constraint still matches.
    for _r in ('IE', 'NI'):
        if os.environ.get(f'GAMMA_SIGMA_{_r}'):
            cons_params[_r]['sigma'] = float(os.environ[f'GAMMA_SIGMA_{_r}'])
            say(f"      sigma for {_r} fixed at {cons_params[_r]['sigma']:.2f} (GAMMA_SIGMA_{_r})")
    sigma_by_zone = {z: cons_params['IE']['sigma'] for z in IE_ZONES}
    sigma_by_zone['NI'] = cons_params['NI']['sigma']
    calib_by_zone = {z: cons_params['IE']['calib'] for z in IE_ZONES}
    calib_by_zone['NI'] = cons_params['NI']['calib']

    # --- Calibrate each zone's 2026 headroom to its recorded constraint in HEADROOM_CALIBRATION_YEAR ---
    # IE zones: the IE hourly availability (wind + solar) split by zone MW; the zone's recorded
    # constraint % is matched exactly. NI: its own hourly records. Every IE zone uses the IE sigma.
    cy = HEADROOM_CALIBRATION_YEAR
    ie_cy = dd['IE'].loc[dd['IE']['year'] == cy, 'avail_mw'].values
    ni_cy = dd['NI'][dd['NI']['year'].isin(NI_CALIBRATION_YEARS)]
    if not len(ie_cy) or cy not in hist_annual.columns:
        raise ValueError(f"Calibration year {cy} needs hourly IE records and a {cy} column in {ZONAL_HISTORY_FILE}.")
    headroom_base = {z: calibrate_headroom(ie_cy * zone_shares[z]['share_of_ie_onshore'], hist_annual.loc[z, cy],
                                           sigma_by_zone[z]) for z in IE_ZONES}
    ni_cy_pct = 100.0 * ni_cy['cons_mw'].sum() / ni_cy['avail_mw'].sum()
    headroom_base['NI'] = calibrate_headroom(ni_cy['avail_mw'].values, ni_cy_pct, sigma_by_zone['NI'])
    default_table = rebase_headroom_table(load_zonal_headroom(input_path(HEADROOM_FILE))[0], headroom_base)
    print(f">> Zones {HEADROOM_ZONES}; 2026 headroom calibrated to each zone's recorded {cy} constraint "
          f"('{ZONAL_HISTORY_FILE}'; NI from its hourly records for {NI_CALIBRATION_YEARS}):")
    print(pd.DataFrame({'Zone_MW': {z: zone_caps_mw.get(z, np.nan) for z in IE_ZONES},
                        f'Constraint_{cy}_%': {**{z: hist_annual.loc[z, cy] for z in IE_ZONES}, 'NI': ni_cy_pct},
                        'Headroom_2026_MW': headroom_base}).round(1).to_string())

    # --- Zonal backcast: the calibrated zonal model run over every recorded year ---
    # Each year's IE hourly availability is split by today's zone MW (the only split on record) and
    # run against the calibrated headroom, held fixed, as the regional backcast does.
    zb_rows = []
    for y in sorted(hist_annual.columns):
        ie_y = dd['IE'].loc[dd['IE']['year'] == y, 'avail_mw'].values
        if not len(ie_y):
            continue
        pred_e, avail_e = 0.0, 0.0
        for z in IE_ZONES:
            x = ie_y * zone_shares[z]['share_of_ie_onshore']
            pred = expected_constraint_mw(x, headroom_base[z], sigma_by_zone[z], calib_by_zone[z]).sum()
            pred_e, avail_e = pred_e + pred, avail_e + x.sum()
            zb_rows.append({'Year': y, 'Zone': z, 'In_fit': y == cy, 'Actual_Cons_%': hist_annual.loc[z, y],
                            'Predicted_Cons_%': 100 * pred / x.sum()})
        zb_rows.append({'Year': y, 'Zone': 'IE', 'In_fit': y == cy,
                        'Actual_Cons_%': hist_annual.loc['IE', y] if 'IE' in hist_annual.index else np.nan,
                        'Predicted_Cons_%': 100 * pred_e / avail_e})
        ni_y = dd['NI'][dd['NI']['year'] == y]
        if len(ni_y):
            pred = expected_constraint_mw(ni_y['avail_mw'].values, headroom_base['NI'], sigma_by_zone['NI']).sum()
            zb_rows.append({'Year': y, 'Zone': 'NI', 'In_fit': y == cy,
                            'Actual_Cons_%': 100 * ni_y['cons_mw'].sum() / ni_y['avail_mw'].sum(),
                            'Predicted_Cons_%': 100 * pred / ni_y['avail_mw'].sum()})
    zonal_backcast = pd.DataFrame(zb_rows)
    zonal_backcast['Error_pts'] = zonal_backcast['Predicted_Cons_%'] - zonal_backcast['Actual_Cons_%']
    print(f"\nZonal backcast: calibrated {cy} zonal headroom held fixed over every recorded year "
          f"(constraint % of the zone's available output; {cy} matches by construction):")
    show = zonal_backcast.pivot(index='Zone', columns='Year', values=['Actual_Cons_%', 'Predicted_Cons_%'])
    print(show.reindex(IE_ZONES + ['IE', 'NI']).round(1).to_string())
    oos = zonal_backcast[~zonal_backcast['In_fit']]
    for z, g in oos.groupby('Zone', sort=False):
        mae, bias = g['Error_pts'].abs().mean(), g['Error_pts'].mean()
        record_check('backcast', z, 'zonal backcast error (years outside the calibration)',
                     'PASS' if mae <= 2.0 else 'WARN',
                     f"typical error ±{mae:.1f} pts, bias {bias:+.1f} pts over {len(g)} years")
    print(">> A positive bias means the zone was less constrained in earlier years than the calibrated "
          "network allows today, i.e. it has tightened since.")
    say(f"[3/5] Zonal calibration ({cy}) and backcast  -  constraint %, recorded / model")
    bc_years = sorted(zonal_backcast['Year'].unique())
    say("      zone   2026 limit  " + "  ".join(f"{y:>11}" for y in bc_years))
    for z in IE_ZONES + ['NI']:
        g = zonal_backcast[zonal_backcast['Zone'] == z].set_index('Year')
        cells = "  ".join(f"{g.loc[y, 'Actual_Cons_%']:5.1f}/{g.loc[y, 'Predicted_Cons_%']:<5.1f}" if y in g.index else " " * 11
                          for y in bc_years)
        say(f"      {z:<4} {headroom_base[z]:>8.0f} MW  {cells}")
    say(f"      ({cy} matches by construction; earlier years test the model)")
    say_checks('backcast')
    try:
        os.makedirs(SCENARIO_OUTPUT_DIR, exist_ok=True)
        zonal_backcast.round(3).to_csv(os.path.join(SCENARIO_OUTPUT_DIR, ZONAL_BACKCAST_CSV), index=False)
        print(f">> Saved to '{os.path.join(SCENARIO_OUTPUT_DIR, ZONAL_BACKCAST_CSV)}'")
    except OSError as e:
        print(f">> Could not save {ZONAL_BACKCAST_CSV}: {e}")

    # --- Input checks: the ECP-GSS-1 generator list ---
    gen_list_path = input_path(GENERATION_LIST_FILE)
    if os.path.exists(gen_list_path):
        gen_list = load_generation_list(gen_list_path, input_path(AREA_ZONE_MAP_FILE))
        pipe_mw, pipe_mwh = pipeline_mw_by_zone(gen_list)
        conn_wind_mw = gen_list.loc[(gen_list['status'] == 'connected') & (gen_list['tech'] == 'wind'), 'mw'].sum()
        roi_2026_mw = float(final_2026_capacity.get('ROI_MW', np.nan))
        if roi_2026_mw > 0:
            gap = conn_wind_mw / roi_2026_mw - 1.0
            record_check('inputs', '', 'connected IE wind in list matches CapacityByYear 2026 ROI',
                         'PASS' if abs(gap) <= MAX_CONNECTED_CAPACITY_MISMATCH else 'WARN',
                         f"list {conn_wind_mw:.0f} MW vs ROI {roi_2026_mw:.0f} MW ({100 * gap:+.1f}%)")
        print(f">> ECP-GSS-1 pipeline (due to connect) MW by zone, from '{GENERATION_LIST_FILE}' "
              f"+ '{AREA_ZONE_MAP_FILE}':")
        print(pd.DataFrame(pipe_mw).rename(columns=str.capitalize).round(0).to_string())
    else:
        gen_list, pipe_mw, pipe_mwh = None, None, None
        print(f">> '{GENERATION_LIST_FILE}' not found: scenarios with capacity_source=pipeline cannot run.")

    stop_on_failures('inputs', SCENARIO_OUTPUT_DIR)
    say("[4/5] Input files")
    if gen_list is not None:
        say(f"      ECP-GSS-1 pipeline: wind {sum(pipe_mw['wind'].values()):,.0f}, solar {sum(pipe_mw['solar'].values()):,.0f}, "
            f"offshore {sum(pipe_mw['offshore'].values()):,.0f}, batteries {sum(pipe_mw['battery'].values()):,.0f} MW")
    say_checks('inputs')

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
    solar_cap_file = input_path(SOLAR_CAPACITY_FILE)
    solar_cap_monthly = None
    if os.path.exists(solar_cap_file):
        solar_cap_monthly = pd.read_csv(solar_cap_file, parse_dates=['month_end'])
    if SOLAR_CAPACITY_2026_GW is not None:
        solar_capacity_2026_gw = float(SOLAR_CAPACITY_2026_GW)
        solar_cap_note = "set in SOLAR_CAPACITY_2026_GW"
    elif solar_cap_monthly is not None and solar_cap_monthly['Total_MW'].max() > 0:
        latest = solar_cap_monthly.iloc[-1]
        solar_capacity_2026_gw = float(latest['Total_MW']) / 1000.0
        base_solar_ie_share = float(latest['IE_MW'] / latest['Total_MW'])
        solar_cap_note = (f"latest listed dispatch-reporting fleet in '{SOLAR_CAPACITY_FILE}'; "
                          f"recorded availability implies {est_solar_gw or float('nan'):.2f} GW at "
                          f"{100 * SOLAR_CAPACITY_FACTOR:.1f}%")
    elif est_solar_gw:
        solar_capacity_2026_gw = est_solar_gw
        solar_cap_note = (f"estimated from the last 12 months of solar availability at a "
                          f"{100 * SOLAR_CAPACITY_FACTOR:.0f}% capacity factor")
    else:
        solar_capacity_2026_gw = SOLAR_CAPACITY_FALLBACK_GW
        solar_cap_note = "! no solar records, using SOLAR_CAPACITY_FALLBACK_GW; set SOLAR_CAPACITY_2026_GW"
    # --- Actual curtailment and capacity factors (EirGrid/SONI dispatch-down records) ---
    # Recorded reasons map to the model's categories: SNSP = snsp; Other = high frequency + RoCoF
    # + other + TSO test. Minimum generation is not recorded separately in these files.
    # Solar capacity history is not in the inputs, so actual solar CF is left blank.
    hist_eval_rows = []
    # Last recorded month of the anchor year (part-year record), for the matched-window
    # comparison of modelled and recorded 2026 dispatch down (22 November 2026).
    anchor_record_last_month = None
    for tech, fname in DD_ALL_ISLAND_FILES.items():
        path = input_path(fname)
        if not os.path.exists(path):
            continue
        h = pd.read_csv(path, parse_dates=['datetime'])
        h['year'] = h['datetime'].dt.year
        _a = h.loc[(h['year'] == 2026) & (h['av_mwh'] > 0), 'datetime']
        if len(_a):
            m = int(_a.max().month)
            anchor_record_last_month = m if anchor_record_last_month is None else min(anchor_record_last_month, m)
        g = h.groupby('year').agg(hours=('av_mwh', 'size'), av=('av_mwh', 'sum'), ao=('ao_mwh', 'sum'),
                                  con=('constraint_mwh', 'sum'), curt=('curtailment_mwh', 'sum'),
                                  snsp=('snsp_mwh', 'sum'), hf=('hi_frq_mwh', 'sum'), rocof=('rocof_mwh', 'sum'),
                                  oth=('other_mwh', 'sum'), test=('tso_test_mwh', 'sum'))
        for y, r in g.iterrows():
            if r['av'] <= 0:
                continue
            cap_mw = np.nan
            if tech == 'Solar' and solar_cap_monthly is not None:
                hh = h.loc[h['year'] == y, 'datetime']
                me = (hh + pd.offsets.MonthEnd(0)).dt.normalize()
                cap_series = me.map(solar_cap_monthly.set_index('month_end')['Total_MW'])
                cap_mw = float(cap_series.mean()) if cap_series.notna().all() and cap_series.mean() > 0 else np.nan
            if tech == 'Wind':
                rows_y = df_cap.loc[df_cap['year'] == y]
                if len(rows_y):
                    cap_mw = float(capacity_row_for_year(int(y), prefer_final=False)['Total_MW'])
            pct = lambda x: round(100.0 * x / r['av'], 2)
            hist_eval_rows.append({'tech': tech, 'Year': int(y), 'hours': int(r['hours']),
                f'{tech}_Capacity_GW': round(cap_mw / 1000, 3) if pd.notna(cap_mw) else np.nan,
                f'{tech}_Available_TWh': round(r['av'] / 1e6, 3), f'{tech}_Generation_TWh': round(r['ao'] / 1e6, 3),
                f'{tech}_Available_CF_%': round(100 * r['av'] / (cap_mw * r['hours']), 2) if pd.notna(cap_mw) else np.nan,
                f'{tech}_Delivered_CF_%': round(100 * r['ao'] / (cap_mw * r['hours']), 2) if pd.notna(cap_mw) else np.nan,
                f'{tech}_Constraint_%': pct(r['con']), f'{tech}_Curtail_SNSP_%': pct(r['snsp']),
                f'{tech}_Curtail_MinGen_%': np.nan, f'{tech}_Curtail_Other_%': pct(r['hf'] + r['rocof'] + r['oth'] + r['test']),
                f'{tech}_Curtailment_%': pct(r['curt']), f'{tech}_Dispatch_Down_%': pct(r['con'] + r['curt']),
                f'{tech}_Constrained_TWh': round(r['con'] / 1e6, 3), f'{tech}_Curtailed_TWh': round(r['curt'] / 1e6, 3)})
    if hist_eval_rows:
        he = pd.DataFrame(hist_eval_rows)
        historical_evaluation = None
        for tech in DD_ALL_ISLAND_FILES:
            part = he[he['tech'] == tech].drop(columns='tech').dropna(axis=1, how='all')
            historical_evaluation = part if historical_evaluation is None else historical_evaluation.merge(
                part, on=['Year', 'hours'], how='outer')
        full = historical_evaluation['hours'] >= 8760
        historical_evaluation.insert(0, 'Data_Type', np.where(full, 'Actual', 'Actual (part year)'))
        av_ws = historical_evaluation[['Wind_Available_TWh', 'Solar_Available_TWh']].sum(axis=1)
        historical_evaluation['WindSolar_Curtailment_%'] = (100 * historical_evaluation[['Wind_Curtailed_TWh', 'Solar_Curtailed_TWh']].sum(axis=1) / av_ws).round(2)
        historical_evaluation['WindSolar_Dispatch_Down_%'] = (100 * historical_evaluation[['Wind_Curtailed_TWh', 'Solar_Curtailed_TWh', 'Wind_Constrained_TWh', 'Solar_Constrained_TWh']].sum(axis=1) / av_ws).round(2)
        historical_evaluation = historical_evaluation.drop(columns='hours')
    else:
        historical_evaluation = pd.DataFrame(columns=['Data_Type', 'Year'])
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

    def zonal_constraint_mw(wind_onshore_mw, wind_offshore_mw, solar_mw, headrooms,
                            zone_caps_gw, offshore_caps_gw, solar_caps_gw, offshore_own=False):
        """V9: expected constraint by zone; each zone's onshore wind, offshore wind and solar
        share that zone's headroom.

        zone_caps_gw / offshore_caps_gw / solar_caps_gw: GW by zone for this year, used to split
        the all-island onshore, offshore and solar availability series across zones.
        Returns zone dict (OFFSHORE = offshore constraint summed over zones) plus IE/NI rollups.
        """
        wind_on = np.asarray(wind_onshore_mw, dtype=float) * avail_basis_ratio
        wind_off = np.asarray(wind_offshore_mw, dtype=float) * avail_basis_ratio
        solar = np.zeros_like(wind_on) if solar_mw is None else np.asarray(solar_mw, dtype=float)
        onshore_gw = sum(float(zone_caps_gw.get(z, 0.0)) for z in HEADROOM_ZONES) or 1e-9
        offshore_gw = sum(float(v) for v in offshore_caps_gw.values())
        solar_gw = sum(float(v) for v in solar_caps_gw.values())
        zone_out = {}
        offshore_con = np.zeros_like(wind_on)
        for z in HEADROOM_ZONES:
            w_z = wind_on * (float(zone_caps_gw.get(z, 0.0)) / onshore_gw)
            if offshore_own or offshore_gw <= 0:
                o_z = 0.0 * wind_off          # own connection: offshore takes no onshore headroom
            else:
                o_z = wind_off * (float(offshore_caps_gw.get(z, 0.0)) / offshore_gw)
            s_z = solar * (float(solar_caps_gw.get(z, 0.0)) / solar_gw) if solar_gw > 0 else 0.0 * solar
            x = w_z + o_z + s_z
            total = expected_constraint_mw(x, headrooms[z], sigma_by_zone[z], calib_by_zone[z])
            # Attribute the zone's constraint to onshore / offshore / solar by available share
            denom = np.maximum(x, 1e-9)
            zone_out[z] = {
                'wind': total * (w_z / denom) / avail_basis_ratio,
                'solar': total * (s_z / denom) / avail_basis_ratio,
                'offshore': total * (o_z / denom) / avail_basis_ratio,     # this zone's offshore wind
            }
            offshore_con += zone_out[z]['offshore']
        if offshore_own and offshore_gw > 0:
            # Dedicated export connection sized at OFFSHORE_CONNECTION_RATIO x installed capacity.
            # Output above the connection rating is constrained; nothing else is.
            connection_mw = OFFSHORE_CONNECTION_RATIO * offshore_gw * 1000.0 * avail_basis_ratio
            offshore_con = np.maximum(0.0, wind_off - connection_mw) / avail_basis_ratio
        zone_out['OFFSHORE'] = {'wind': offshore_con, 'solar': np.zeros_like(offshore_con)}
        # IE/NI rollups (offshore attributed to IE)
        reg = {
            'IE': {
                'wind': sum(zone_out[z]['wind'] for z in IE_ZONES) + zone_out['OFFSHORE']['wind'],
                'solar': sum(zone_out[z]['solar'] for z in IE_ZONES),
            },
            'NI': {
                'wind': zone_out['NI']['wind'],
                'solar': zone_out['NI']['solar'],
            },
        }
        return reg, zone_out

    def dispatch(wind_onshore, wind_offshore, solar, demand, headrooms, zone_caps_gw, offshore_caps_gw,
                 solar_caps_gw, snsp_fraction,
                 storage_power_mw=0.0, storage_energy_mwh=0.0,
                 charge_efficiency=DEFAULT_STORAGE_CHARGE_EFFICIENCY,
                 discharge_efficiency=DEFAULT_STORAGE_DISCHARGE_EFFICIENCY,
                 initial_soc_pct=DEFAULT_STORAGE_INITIAL_SOC_PCT,
                 pc_storage_hybrid=DEFAULT_PC_STORAGE_HYBRID,
                 muon_floor_mw=DEFAULT_MUON_FLOOR_MW,
                 offshore_own=False, export_cap_mw=0.0, import_cap_mw=0.0,
                 historical_import_mw=None, historical_export_mw=None):
        """Quarter-hour gamma.py dispatch with Marcel's zonal/offshore constraints and V10's aggregated BESS fleet.

        Order of operation:
          1. Apply the fitted IE/NI grid constraint to available wind and solar.
          2. Limit BESS access to otherwise-curtailed post-constraint VRE by the
             unconstrained VRE fraction and the standalone/hybrid access weighting.
          3. Charge from that accessible original curtailment; charging is included
             in overall demand used for the SNSP and MUON operational ceilings, and the
             wind and solar MW charging the fleet count against those ceilings
             (dispatch_interval, 22 November 2026).
          4. If the fleet is not charging, dispatch post-constraint wind and solar
             first, then discharge BESS into residual demand and remaining SNSP/MUON
             headroom. There is no time-of-day discharge window.

          5. Interconnectors (issues #5, #9). export_cap_mw and import_cap_mw are the usable
             MW this year (capacity x availability). In intervals with curtailment left after
             charging, exports are added to demand up to export_cap_mw, only as far as needed
             to absorb the surplus. Exports enter the SNSP denominator and the MUON ceiling, so
             the extra wind/solar dispatched is L(D + C + E) - L(D + C). When SNSP binds, part of
             the export flow, (1 - SNSP) x E, has to come from synchronous plant; that part is
             returned as export_sync_mw and counted as firm generation. In deficit intervals,
             imports cover the residual after wind, solar and BESS, up to import_cap_mw and
             within the SNSP and MUON headroom (HVDC imports are non-synchronous).

        SNSP used here (EirGrid definition):
            (dispatched wind + solar + BESS discharge + HVDC imports)
            ----------------------------------------------------------
                    (native demand + BESS charging + HVDC exports)

        The fleet has one MW limit, one MWh state of charge and one dispatch rule.
        pc_storage_hybrid affects only access to otherwise-curtailed VRE:
        standalone capacity receives a 0.90 factor and hybrid capacity a 1.10
        factor. Accessible charging is calculated from original otherwise-curtailed
        VRE and capped by actual curtailment, battery MW and SoC headroom.
        """
        wind_onshore = np.asarray(wind_onshore, dtype=float)
        wind_offshore = np.asarray(wind_offshore, dtype=float)
        solar = np.asarray(solar, dtype=float)
        demand = np.asarray(demand, dtype=float)
        wind = wind_onshore + wind_offshore
        if not (len(wind_onshore) == len(wind_offshore) == len(solar) == len(demand)):
            raise ValueError("onshore wind, offshore wind, solar and demand arrays must have equal length")

        # Optional FIXED observed flows for a historical sensitivity only.
        # Unlike import_cap_mw/export_cap_mw these are exogenous flows, not
        # capacity which dispatch chooses to use. All regular runs use zeros.
        n_intervals = len(demand)
        forced_import = (np.zeros(n_intervals) if historical_import_mw is None
                         else np.asarray(historical_import_mw, dtype=float))
        forced_export = (np.zeros(n_intervals) if historical_export_mw is None
                         else np.asarray(historical_export_mw, dtype=float))
        if (forced_import.shape != (n_intervals,) or forced_export.shape != (n_intervals,)
                or not np.isfinite(forced_import).all()
                or not np.isfinite(forced_export).all()
                or (forced_import < 0).any() or (forced_export < 0).any()):
            raise ValueError('Historical imports/exports must be nonnegative, finite MW arrays matching demand')
        if (historical_import_mw is not None or historical_export_mw is not None) and (
                import_cap_mw != 0 or export_cap_mw != 0):
            raise ValueError('Do not combine recorded historical flows with optional interconnector capacity dispatch')

        reg, zone_detail = zonal_constraint_mw(
            wind_onshore, wind_offshore, solar, headrooms, zone_caps_gw,
            offshore_caps_gw, solar_caps_gw, offshore_own=offshore_own
        )
        export_cap_mw = max(0.0, float(export_cap_mw))
        import_cap_mw = max(0.0, float(import_cap_mw))
        gross_con_w = sum(reg[r]['wind'] for r in REGIONS)
        gross_con_s = sum(reg[r]['solar'] for r in REGIONS)
        gross_con = gross_con_w + gross_con_s
        post_w = np.maximum(0.0, wind - gross_con_w)
        post_s = np.maximum(0.0, solar - gross_con_s)
        post = post_w + post_s
        n = len(post)

        power_mw = max(0.0, float(storage_power_mw))
        energy_mwh = max(0.0, float(storage_energy_mwh))
        charge_eff = np.clip(float(charge_efficiency), 1e-9, 1.0)
        discharge_eff = np.clip(float(discharge_efficiency), 1e-9, 1.0)
        initial_fraction = np.clip(float(initial_soc_pct) / 100.0, 0.0, 1.0)
        soc_mwh_now = energy_mwh * initial_fraction
        f = np.clip(float(snsp_fraction), 0.0, 1.0)

        hybrid_fraction = np.clip(float(pc_storage_hybrid) / 100.0, 0.0, 1.0)
        standalone_fraction = 1.0 - hybrid_fraction
        hybrid_access_weight = hybrid_fraction * 1.10
        standalone_access_weight = standalone_fraction * 0.90
        access_weight_total = hybrid_access_weight + standalone_access_weight
        curtailment_access_factor = min(1.0, access_weight_total)

        if access_weight_total > 0.0:
            hybrid_access_share = hybrid_access_weight / access_weight_total
        else:
            hybrid_access_share = hybrid_fraction
        standalone_access_share = 1.0 - hybrid_access_share

        names = [
            'charge', 'discharge', 'soc', 'curt', 'direct', 'limit',
            'snspceil', 'muonceil', 'snsppct', 'potential_curt',
            'accessible_curt', 'charge_blocked_constraint',
            'export', 'export_vre', 'export_sync', 'imp', 'surplus', 'surplus_pre'
        ]
        a = {name: np.zeros(n, dtype=float) for name in names}

        for i in range(n):
            forced_import_i = float(forced_import[i])
            forced_export_i = float(forced_export[i])
            native_demand_mw = max(0.0, demand[i] + forced_export_i)
            post_constraint_vre_mw = max(0.0, post[i])
            available_vre_mw = max(0.0, wind[i] + solar[i])
            unconstrained_vre_fraction = (
                min(1.0, max(0.0, post_constraint_vre_mw / available_vre_mw))
                if available_vre_mw > 0.0 else 0.0
            )

            no_charge_limit_mw = min(
                max(0.0, f * native_demand_mw - forced_import_i),
                max(0.0, native_demand_mw - forced_import_i - muon_floor_mw)
            )
            potential_curtailment_mw = max(
                0.0, post_constraint_vre_mw - no_charge_limit_mw
            )
            # Only the unconstrained share can reach the national BESS fleet. The
            # 0.90/1.10 standalone/hybrid weighting is applied to the original
            # otherwise-curtailed VRE, not to curtailment left after charging.
            accessible_curtailment_mw = min(
                potential_curtailment_mw,
                potential_curtailment_mw
                * unconstrained_vre_fraction
                * curtailment_access_factor,
            )
            a['potential_curt'][i] = potential_curtailment_mw

            charge_power_cap_mw = min(
                power_mw,
                max(0.0, energy_mwh - soc_mwh_now)
                / (INTERVAL_HOURS * charge_eff),
            )

            charge_mw = min(
                charge_power_cap_mw,
                accessible_curtailment_mw,
            )
            # This diagnostic is the portion of otherwise-curtailed VRE made
            # inaccessible by the aggregate network-location proxy. It does not
            # imply that all charging is blocked whenever any constraint exists.
            a['charge_blocked_constraint'][i] = max(
                0.0,
                potential_curtailment_mw * curtailment_access_factor
                - accessible_curtailment_mw,
            )

            # Charging is physically withdrawn from post-constraint VRE, adds to system demand
            # and counts against the SNSP/MUON ceiling (see dispatch_interval).
            charge_mw = min(charge_mw, post_constraint_vre_mw)
            discharge_cap_mw = min(power_mw, soc_mwh_now * discharge_eff / INTERVAL_HOURS)
            r = dispatch_interval(
                native_demand_mw, post_constraint_vre_mw, charge_mw, discharge_cap_mw,
                f, muon_floor_mw, forced_import_i, export_cap_mw, import_cap_mw,
            )
            charge_mw = r['charge']
            discharge_mw = r['discharge']
            # The same quantity on available output before the network is applied, which is the
            # order EirGrid uses (surplus first, then curtailment, then constraint). Diagnostic only.
            surplus_pre_mw = max(0.0, available_vre_mw - charge_mw - native_demand_mw - r['export_vre'])

            soc_mwh_now += charge_mw * INTERVAL_HOURS * charge_eff
            soc_mwh_now -= discharge_mw * INTERVAL_HOURS / discharge_eff
            soc_mwh_now = min(energy_mwh, max(0.0, soc_mwh_now))

            a['charge'][i] = charge_mw
            a['discharge'][i] = discharge_mw
            a['soc'][i] = soc_mwh_now
            a['direct'][i] = r['direct']
            a['curt'][i] = r['curt']
            a['surplus'][i] = r['surplus']
            a['surplus_pre'][i] = surplus_pre_mw
            a['accessible_curt'][i] = charge_mw
            a['limit'][i] = r['limit']
            a['snspceil'][i] = r['snspceil']
            a['muonceil'][i] = r['muonceil']
            a['export'][i] = r['export'] + forced_export_i
            a['export_vre'][i] = r['export_vre']
            a['export_sync'][i] = r['export_sync']
            a['imp'][i] = r['imp'] + forced_import_i
            # SNSP diagnostic: all non-synchronous output, including wind and solar charging
            # the batteries, over native demand + charging + exports.
            a['snsppct'][i] = r['snsppct']

        # BESS cannot recover energy behind an active fitted network constraint.
        # Physical grid constraint remains exactly the fitted zonal constraint.
        con_w = gross_con_w.copy()
        con_s = gross_con_s.copy()
        recovered_constraint_mw = np.zeros(n, dtype=float)

        # ------------------------------------------------------------------
        # REPORTING-ONLY DISPATCH-DOWN RECLASSIFICATION
        # ------------------------------------------------------------------
        # Some renewable energy is physically trapped behind a zonal grid
        # constraint during intervals when gross renewable availability also
        # exceeds the all-island operational ceiling. Grid reinforcement alone
        # would not make that coincident oversupply dispatchable. Reclassify that
        # overlap from the reporting category "grid constraint" to
        # "Operational Curtailment / Oversupply".
        #
        # This does NOT change chronological dispatch, BESS charge/discharge,
        # SOC, usable renewables, firm supply, the fitted zonal constraint, or
        # total dispatch-down. The original physical constraint remains in
        # con_w/con_s, gross_con_w/gross_con_s, reg and zones.
        gross_available_vre_mw = np.maximum(0.0, wind + solar)
        original_grid_constraint_mw = np.maximum(0.0, gross_con)
        gross_operational_oversupply_mw = np.maximum(
            0.0, gross_available_vre_mw - a['limit']
        )
        grid_constrained_oversupply_mw = np.minimum(
            original_grid_constraint_mw,
            gross_operational_oversupply_mw,
        )
        recoverable_grid_constraint_mw = np.maximum(
            0.0,
            original_grid_constraint_mw - grid_constrained_oversupply_mw,
        )
        operational_curtailment_oversupply_mw = (
            a['curt'] + grid_constrained_oversupply_mw
        )

        # Attribute the reporting-only split to wind and solar in proportion to
        # their original fitted grid constraint. This preserves technology totals.
        constraint_w_share = np.divide(
            gross_con_w,
            original_grid_constraint_mw,
            out=np.zeros_like(original_grid_constraint_mw),
            where=original_grid_constraint_mw > 0.0,
        )
        constrained_oversupply_w_mw = (
            grid_constrained_oversupply_mw * constraint_w_share
        )
        constrained_oversupply_s_mw = (
            grid_constrained_oversupply_mw - constrained_oversupply_w_mw
        )
        recoverable_grid_constraint_w_mw = np.maximum(
            0.0, gross_con_w - constrained_oversupply_w_mw
        )
        recoverable_grid_constraint_s_mw = np.maximum(
            0.0, gross_con_s - constrained_oversupply_s_mw
        )

        # Exact accounting checks: attribution may change, total dispatch-down may not.
        if not np.allclose(
            original_grid_constraint_mw,
            recoverable_grid_constraint_mw + grid_constrained_oversupply_mw,
            rtol=1e-9,
            atol=1e-6,
        ):
            raise RuntimeError(
                "Grid-constraint reclassification failed its conservation check."
            )
        if not np.allclose(
            original_grid_constraint_mw + a['curt'],
            recoverable_grid_constraint_mw
            + operational_curtailment_oversupply_mw,
            rtol=1e-9,
            atol=1e-6,
        ):
            raise RuntimeError(
                "Dispatch-down changed during reporting reclassification."
            )

        post_wind_fraction = np.divide(
            post_w,
            post,
            out=np.ones_like(post),
            where=post > 0.0,
        )
        initial_mwh = energy_mwh * initial_fraction
        losses_mwh = (
            a['charge'].sum() * INTERVAL_HOURS
            - a['discharge'].sum() * INTERVAL_HOURS
            - ((a['soc'][-1] if n else initial_mwh) - initial_mwh)
        )

        # Compatibility outputs retain hybrid/standalone columns, but both portions
        # now use the same aggregate SoC and dispatch rules. Charging is apportioned
        # by weighted access contribution; discharge and SoC by installed share.
        hybrid_charge_mw = a['charge'] * hybrid_access_share
        standalone_charge_mw = a['charge'] * standalone_access_share
        hybrid_discharge_mw = a['discharge'] * hybrid_fraction
        standalone_discharge_mw = a['discharge'] * standalone_fraction
        hybrid_soc_mwh = a['soc'] * hybrid_fraction
        standalone_soc_mwh = a['soc'] * standalone_fraction

        zones = zone_detail

        return {
            'reg': reg,
            'zones': zones,
            'con_w': con_w,
            'con_s': con_s,
            'gross_con_w': gross_con_w,
            'gross_con_s': gross_con_s,
            'original_grid_constraint_mw': original_grid_constraint_mw,
            'grid_constrained_oversupply_mw': grid_constrained_oversupply_mw,
            'recoverable_grid_constraint_mw': recoverable_grid_constraint_mw,
            'recoverable_grid_constraint_w_mw': recoverable_grid_constraint_w_mw,
            'recoverable_grid_constraint_s_mw': recoverable_grid_constraint_s_mw,
            'operational_curtailment_oversupply_mw': operational_curtailment_oversupply_mw,
            'recovered_constraint_mw': recovered_constraint_mw,
            'curt_w': a['curt'] * post_wind_fraction,
            'curt_s': a['curt'] * (1.0 - post_wind_fraction),
            'surplus_mw': a['surplus'],
            'surplus_pre_mw': a['surplus_pre'],
            # usable = wind/solar generated and dispatched, including the part exported
            'usable_w': (a['direct'] + a['export_vre']) * post_wind_fraction,
            'usable_s': (a['direct'] + a['export_vre']) * (1.0 - post_wind_fraction),
            'domestic_vre_mw': a['direct'],
            'export_mw': a['export'],
            'export_vre_mw': a['export_vre'],
            'export_sync_mw': a['export_sync'],
            'import_mw': a['imp'],
            'potential_curt_mw': a['potential_curt'],
            'accessible_curtailment_mw': a['accessible_curt'],
            'charge_blocked_by_constraint_mw': a['charge_blocked_constraint'],
            'curtailment_access_factor': curtailment_access_factor,
            'charge_mw': a['charge'],
            'discharge_mw': a['discharge'],
            'soc_mwh': a['soc'],
            'operational_limit_mw': a['limit'],
            'snsp_ceiling_mw': a['snspceil'],
            'muon_ceiling_mw': a['muonceil'],
            'actual_snsp_pct': a['snsppct'],
            'hybrid_charge_mw': hybrid_charge_mw,
            'standalone_charge_mw': standalone_charge_mw,
            'hybrid_discharge_mw': hybrid_discharge_mw,
            'standalone_discharge_mw': standalone_discharge_mw,
            'hybrid_soc_mwh': hybrid_soc_mwh,
            'standalone_soc_mwh': standalone_soc_mwh,
            'storage_losses_mwh': losses_mwh,
        }
    def interactive_scenario():
        """Ask for the scenario inputs (used when there is no scenarios.csv)."""
        print("\n(No scenariosXLSX.xlsx found: running one scenario from prompts.)")
        return {
            'scenario': 'interactive',
            'target_year': int(ask_float("Enter final simulation year", 2050)),
            'build_rate_wind_ie': ask_float("Enter annual WIND build-out rate in IE/ROI, GW/year",
                                            round(DEFAULT_BUILD_RATE_GW * base_ie_share, 3)),
            'build_rate_wind_ni': ask_float("Enter annual WIND build-out rate in NI, GW/year",
                                            round(DEFAULT_BUILD_RATE_GW * (1 - base_ie_share), 3)),
            'build_rate_solar_ie': ask_float("Enter annual SOLAR build-out rate in IE/ROI, GW/year",
                                             round(DEFAULT_SOLAR_BUILD_RATE_GW * base_solar_ie_share, 3)),
            'build_rate_solar_ni': ask_float("Enter annual SOLAR build-out rate in NI, GW/year",
                                             round(DEFAULT_SOLAR_BUILD_RATE_GW * (1 - base_solar_ie_share), 3)),
            'background_demand_growth_twh_per_year': ask_float("Enter annual background/native/data-centre demand growth, TWh/year", DEFAULT_BACKGROUND_DEMAND_GROWTH_TWH_PER_YEAR),
            'heat_demand_growth_twh_per_year': ask_float("Enter annual heat-sector electricity demand growth, TWh/year", DEFAULT_HEAT_DEMAND_GROWTH_TWH_PER_YEAR),
            'transport_demand_growth_twh_per_year': ask_float("Enter annual transport-sector electricity demand growth, TWh/year", DEFAULT_TRANSPORT_DEMAND_GROWTH_TWH_PER_YEAR),
            'snsp_limit_pct': ask_float("Enter System Non-Synchronous Penetration (SNSP) Limit %", DEFAULT_SNSP_PCT),
            'muon_units_ie': ask_float("Enter IE MUON units online", DEFAULT_MUON_UNITS_IE),
            'muon_units_ni': ask_float("Enter NI MUON units online", DEFAULT_MUON_UNITS_NI),
            'storage_power_build_rate_mw': ask_float("Enter annual standalone storage power build rate, MW/year", 0.0),
            'storage_energy_build_rate_mwh': ask_float("Enter annual standalone storage energy build rate, MWh/year", 0.0),
            'storage_power_2026_mw': ask_float("Enter installed standalone storage power in 2026, MW", 0.0),
            'storage_energy_2026_mwh': ask_float("Enter installed standalone storage energy in 2026, MWh", 0.0),
            'storage_charge_efficiency': ask_float("Enter storage charge efficiency (0-1)", DEFAULT_STORAGE_CHARGE_EFFICIENCY),
            'storage_discharge_efficiency': ask_float("Enter storage discharge efficiency (0-1)", DEFAULT_STORAGE_DISCHARGE_EFFICIENCY),
            'storage_initial_soc_pct': DEFAULT_STORAGE_INITIAL_SOC_PCT,
            'pc_storage_hybrid': ask_float("Enter hybrid/co-located storage share (%)", DEFAULT_PC_STORAGE_HYBRID),
            'celtic_energised_year': DEFAULT_CELTIC_ENERGISED_YEAR,
            'mares_energised_year': DEFAULT_MARES_ENERGISED_YEAR,
            'build_rate_wind_offshore': ask_float("Enter annual OFFSHORE wind build-out rate, GW/year",
                                                  DEFAULT_BUILD_RATE_WIND_OFFSHORE),
            'headroom_scale': ask_float("Enter zonal headroom scale factor (1.0 = published path)",
                                        DEFAULT_HEADROOM_SCALE),
            'headroom_curve': DEFAULT_HEADROOM_CURVE,  # TID → Data_inputs/zonal_headroom_by_year.csv
            'ie_reinforcement_pct': 0.0,  # ignored when headroom_curve is set
            'ni_reinforcement_pct': 0.0,
            'ie_reinforcement_mw_per_year': 0.0, 'ni_reinforcement_mw_per_year': 0.0,
            'reinforcement_steps': '', 'offshore_connection': DEFAULT_OFFSHORE_CONNECTION,
            'ic_export_availability': DEFAULT_IC_EXPORT_AVAILABILITY,
            'ic_import_availability': DEFAULT_IC_IMPORT_AVAILABILITY,
            'ic_capacity_credit': DEFAULT_IC_CAPACITY_CREDIT,
            'capacity_source': 'rates', 'pipeline_target_year': DEFAULT_PIPELINE_TARGET_YEAR,
            'pipeline_build_pct': DEFAULT_PIPELINE_BUILD_PCT, 'defaulted': [],
        }

    BUILD_COLUMNS = ['build_rate_wind_ie', 'build_rate_wind_ni', 'build_rate_solar_ie', 'build_rate_solar_ni']

    def load_scenarios(path):
        """Read scenariosXLSX.xlsx; blank cells take the defaults.

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
        known = BUILD_COLUMNS + ['scenario', 'snsp_limit_pct', 'muon_units_ie', 'muon_units_ni',
                                 'ie_reinforcement_pct', 'ni_reinforcement_pct',  # used with headroom_curve=reinforcement_pct
                                 'build_rate_wind_offshore', 'headroom_scale', 'headroom_curve',
                                 'description', 'storage_power_build_rate_mw', 'storage_energy_build_rate_mwh',
                                 'storage_power_2026_mw', 'storage_energy_2026_mwh',
                                 'storage_charge_efficiency', 'storage_discharge_efficiency', 'storage_initial_soc_pct', 'pc_storage_hybrid',
                                 'wind_build_rate_gw', 'build_rate_gw', 'demand_rate_twh_per_year',
                                 'background_demand_growth_twh_per_year', 'heat_demand_growth_twh_per_year',
                                 'transport_demand_growth_twh_per_year', 'units',
                                 'new_build_ie_pct', 'solar_build_rate_gw',
                                 'solar_new_build_ie_pct', 'capacity_source', 'pipeline_target_year',
                                 'pipeline_build_pct',
                                 'total_demand_growth_twh_per_year',      # calculated in the workbook; not read
                                 'offshore_connection', 'celtic_energised_year', 'mares_energised_year',
                                 'ic_export_availability', 'ic_import_availability', 'ic_capacity_credit',
                                 'ie_reinforcement_mw_per_year', 'ni_reinforcement_mw_per_year',
                                 'reinforcement_steps', 'target_year', 'scenario_path', 'weather_years',
                                 'headroom_pipeline_cover_pct', 'battery_hours_target', 'battery_hours_target_year',
                                 'path_heat_growth_twh_per_year', 'path_transport_growth_twh_per_year',
                                 'run']
        lookup = {key(k): k for k in known}
        # Also accept Build_WIND_OFFSHORE / TID / HeadroomCurve style headers
        lookup[key('Build_WIND_OFFSHORE')] = 'build_rate_wind_offshore'
        lookup[key('build_rate_wind_offshore')] = 'build_rate_wind_offshore'
        lookup[key('HeadroomCurve')] = 'headroom_curve'
        lookup[key('headroom_curve')] = 'headroom_curve'
        lookup[key('reinforcement_curve')] = 'headroom_curve'
        table.columns = [lookup.get(key(c), str(c).strip()) for c in table.columns]
        # 'run' column (Cian, 4 Nov 2026): no / n / 0 / false / off keeps a scenario in the workbook
        # but leaves it out of a full run. Naming it on the command line still runs it.
        SCENARIOS_SWITCHED_OFF.clear()
        if 'run' in table.columns and 'scenario' in table.columns:
            off = table['run'].astype(str).str.strip().str.lower().isin(('no', 'n', '0', 'false', 'off'))
            SCENARIOS_SWITCHED_OFF.update(table.loc[off, 'scenario'].astype(str).str.lower())
        unknown = [c for c in table.columns if c not in known]
        record_check('scenarios', '', 'all scenario columns recognised', 'WARN' if unknown else 'PASS',
                     f"ignored: {unknown}" if unknown else '')

        new_cols = [c for c in BUILD_COLUMNS if c in table.columns]
        old_format = not new_cols and ('wind_build_rate_gw' in table.columns or 'build_rate_gw' in table.columns or 'solar_build_rate_gw' in table.columns)
        print(f">> Scenario build-rate columns found: "
              f"{new_cols if new_cols else ('old format (converted)' if old_format else 'none (defaults used)')}")
        if old_format:
            print("   ! Old-format scenario inputs: converting build_rate_gw / new_build_ie_pct and "
                  "solar_build_rate_gw / solar_new_build_ie_pct to the four regional build rates.")

        def is_blank(row, col):
            v = row.get(col, np.nan)
            return pd.isna(v) or str(v).strip() == ''

        def val(row, col, default):
            return float(default) if is_blank(row, col) else float(row.get(col))

        defaults = {'build_rate_wind_ie': DEFAULT_BUILD_RATE_GW * base_ie_share,
                    'build_rate_wind_ni': DEFAULT_BUILD_RATE_GW * (1 - base_ie_share),
                    'build_rate_solar_ie': DEFAULT_SOLAR_BUILD_RATE_GW * base_solar_ie_share,
                    'build_rate_solar_ni': DEFAULT_SOLAR_BUILD_RATE_GW * (1 - base_solar_ie_share),
                    'build_rate_wind_offshore': DEFAULT_BUILD_RATE_WIND_OFFSHORE,
                    'headroom_scale': DEFAULT_HEADROOM_SCALE,
                    'celtic_energised_year': DEFAULT_CELTIC_ENERGISED_YEAR,
                    'mares_energised_year': DEFAULT_MARES_ENERGISED_YEAR,
                    'demand_rate_twh_per_year': DEFAULT_DEMAND_RATE_TWH_PER_YEAR,
                    'background_demand_growth_twh_per_year': DEFAULT_BACKGROUND_DEMAND_GROWTH_TWH_PER_YEAR,
                    'heat_demand_growth_twh_per_year': DEFAULT_HEAT_DEMAND_GROWTH_TWH_PER_YEAR,
                    'transport_demand_growth_twh_per_year': DEFAULT_TRANSPORT_DEMAND_GROWTH_TWH_PER_YEAR,
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
                    'pc_storage_hybrid': DEFAULT_PC_STORAGE_HYBRID,
                    'pipeline_build_pct': DEFAULT_PIPELINE_BUILD_PCT,
                    'ic_export_availability': DEFAULT_IC_EXPORT_AVAILABILITY,
                    'ic_import_availability': DEFAULT_IC_IMPORT_AVAILABILITY,
                    'ic_capacity_credit': DEFAULT_IC_CAPACITY_CREDIT,
                    'ie_reinforcement_mw_per_year': 0.0, 'ni_reinforcement_mw_per_year': 0.0,
                    'ie_reinforcement_pct': 0.0, 'ni_reinforcement_pct': 0.0, 'target_year': 2050.0,
                    'headroom_pipeline_cover_pct': 0.0, 'battery_hours_target': 0.0,
                    'battery_hours_target_year': 2035.0,
                    # Heat and transport growth already inside a scenario_path demand_twh column.
                    # Blank: the scenario's own rates (no change). Sensitivities that alter the
                    # rates set these to the rates of the scenario the path belongs to.
                    'path_heat_growth_twh_per_year': float('nan'),
                    'path_transport_growth_twh_per_year': float('nan')}
        not_flagged = ('ie_reinforcement_pct', 'ni_reinforcement_pct', 'ie_reinforcement_mw_per_year',
                       'ni_reinforcement_mw_per_year', 'headroom_pipeline_cover_pct',
                       'storage_initial_soc_pct', 'battery_hours_target', 'battery_hours_target_year',
                       'path_heat_growth_twh_per_year', 'path_transport_growth_twh_per_year')
        scenarios = []
        for i, row in table.iterrows():
            name = str(row.get('scenario', '')).strip()
            if name.lower() in ('[text]', 'units', '[units]'):
                continue
            if not name or name.lower() == 'nan':
                name = f"scenario_{i + 1}"
            sc = {'scenario': re.sub(r'[^A-Za-z0-9_.-]+', '_', name)}
            sc['defaulted'] = [k for k in defaults if is_blank(row, k) and k not in not_flagged]
            # reinforcement %/yr only matters with headroom_curve=reinforcement_pct; flagged there
            for k, default in defaults.items():
                try:
                    sc[k] = val(row, k, default)
                except (TypeError, ValueError):
                    record_check('scenarios', sc['scenario'], f'{k} is a number', 'FAIL',
                                 f"got '{row.get(k)}'")
                    sc[k] = float(default)
            if old_format:
                w = val(row, 'wind_build_rate_gw', val(row, 'build_rate_gw', DEFAULT_BUILD_RATE_GW))
                w_ie = val(row, 'new_build_ie_pct', 100 * base_ie_share) / 100.0
                so = val(row, 'solar_build_rate_gw', DEFAULT_SOLAR_BUILD_RATE_GW)
                s_ie = val(row, 'solar_new_build_ie_pct', 100 * base_solar_ie_share) / 100.0
                sc.update({'build_rate_wind_ie': w * w_ie, 'build_rate_wind_ni': w * (1 - w_ie),
                           'build_rate_solar_ie': so * s_ie, 'build_rate_solar_ni': so * (1 - s_ie)})
            sc['description'] = '' if pd.isna(row.get('description', np.nan)) else str(row.get('description'))
            # Headroom curve: TID / fixed / path — string, not float
            hc = row.get('headroom_curve', DEFAULT_HEADROOM_CURVE)
            if pd.isna(hc) or str(hc).strip() == '':
                hc = DEFAULT_HEADROOM_CURVE
            sc['headroom_curve'] = str(hc).strip()
            for text_col, text_default in (('offshore_connection', DEFAULT_OFFSHORE_CONNECTION),
                                           ('reinforcement_steps', ''), ('scenario_path', ''),
                                           ('weather_years', '')):
                sc[text_col] = text_default if is_blank(row, text_col) else str(row.get(text_col)).strip().lower()
            if is_blank(row, 'offshore_connection'):
                sc['defaulted'].append('offshore_connection')
            # Capacity source: GW/yr rates (as before) or the ECP-GSS-1 pipeline by zone
            cs = DEFAULT_CAPACITY_SOURCE if is_blank(row, 'capacity_source') else str(row.get('capacity_source')).strip().lower()
            if is_blank(row, 'capacity_source'):
                sc['defaulted'].append('capacity_source')
            sc['capacity_source'] = cs
            if is_blank(row, 'pipeline_target_year'):
                sc['pipeline_target_year'] = DEFAULT_PIPELINE_TARGET_YEAR
                if cs == 'pipeline':
                    sc['defaulted'].append('pipeline_target_year')
            else:
                sc['pipeline_target_year'] = row.get('pipeline_target_year')
            if cs != 'pipeline' and 'pipeline_build_pct' in sc['defaulted']:
                sc['defaulted'].remove('pipeline_build_pct')     # only matters for pipeline scenarios
            scenarios.append(sc)
        validate_scenarios(scenarios)
        return scenarios

    # Allowed range (inclusive) for each numeric scenario input. Values outside stop the run.
    SCENARIO_RANGES = {
        'build_rate_wind_ie': (0, 10), 'build_rate_wind_ni': (0, 10), 'build_rate_wind_offshore': (0, 10),
        'build_rate_solar_ie': (0, 10), 'build_rate_solar_ni': (0, 10),
        'snsp_limit_pct': (1, 100), 'demand_rate_twh_per_year': (-10, 20),
        'background_demand_growth_twh_per_year': (-10, 20),
        'heat_demand_growth_twh_per_year': (0, 20),
        'transport_demand_growth_twh_per_year': (0, 20), 'headroom_scale': (0.01, 10),
        'muon_units_ie': (0, 20), 'muon_units_ni': (0, 20),
        'storage_power_build_rate_mw': (0, 20000), 'storage_energy_build_rate_mwh': (0, 100000),
        'storage_power_2026_mw': (0, 50000), 'storage_energy_2026_mwh': (0, 200000),
        'storage_charge_efficiency': (0.01, 1), 'storage_discharge_efficiency': (0.01, 1),
        'storage_initial_soc_pct': (0, 100), 'pc_storage_hybrid': (0, 100),
        'pipeline_build_pct': (10, 400),
        'ie_reinforcement_pct': (-10, 50), 'ni_reinforcement_pct': (-10, 50),
        'ie_reinforcement_mw_per_year': (-500, 5000), 'ni_reinforcement_mw_per_year': (-500, 5000),
        'ic_export_availability': (0, 1), 'ic_import_availability': (0, 1), 'ic_capacity_credit': (0, 1),
        'celtic_energised_year': (2026, 2100), 'mares_energised_year': (2026, 2100),
        'target_year': (2030, 2100), 'headroom_pipeline_cover_pct': (0, 200),
        'battery_hours_target': (0, 12), 'battery_hours_target_year': (2027, 2100),
    }

    def validate_scenarios(scenarios):
        """Range, name and capacity-source checks for every scenario; FAILs stop the run."""
        stage = 'scenarios'
        names = [sc['scenario'] for sc in scenarios]
        dup = sorted({n for n in names if names.count(n) > 1})
        record_check(stage, '', 'scenario names unique (after cleaning)', 'FAIL' if dup else 'PASS',
                     f"repeated: {dup}" if dup else '')
        for sc in scenarios:
            name = sc['scenario']
            out_of_range = [f"{k}={sc[k]:g} (allowed {lo:g}-{hi:g})" for k, (lo, hi) in SCENARIO_RANGES.items()
                            if not lo <= float(sc[k]) <= hi]
            record_check(stage, name, 'inputs within allowed ranges', 'FAIL' if out_of_range else 'PASS',
                         '; '.join(out_of_range))
            if sc['storage_power_build_rate_mw'] > 0 and sc['storage_energy_build_rate_mwh'] < sc['storage_power_build_rate_mw'] * 0.25:
                record_check(stage, name, 'storage build MWh/MW at least 0.25 h', 'WARN',
                             f"{sc['storage_power_build_rate_mw']:g} MW/yr with {sc['storage_energy_build_rate_mwh']:g} "
                             f"MWh/yr: added batteries have (almost) no energy")
            if sc['storage_energy_2026_mwh'] < sc['storage_power_2026_mw'] * 0.25:
                record_check(stage, name, 'storage 2026 MWh/MW at least 0.25 h', 'WARN',
                             f"{sc['storage_power_2026_mw']:g} MW / {sc['storage_energy_2026_mwh']:g} MWh")
            if is_reinforcement_curve(sc['headroom_curve']) or is_hybrid_tid_2035_curve(sc['headroom_curve']):
                target_year = int(sc.get('target_year', 2050))
                exponent = (target_year - 2035) if is_hybrid_tid_2035_curve(sc['headroom_curve']) else (target_year - 2026)
                growth = {r: (1 + sc[f'{r.lower()}_reinforcement_pct'] / 100.0) ** exponent for r in REGIONS}
                record_check(stage, name, 'headroom from ie/ni_reinforcement_pct', 'PASS',
                             f"IE {sc['ie_reinforcement_pct']:g}%/yr (x{growth['IE']:.1f} over the simplified period), "
                             f"NI {sc['ni_reinforcement_pct']:g}%/yr (x{growth['NI']:.1f} over the simplified period)")
                if max(growth.values()) > 20:
                    record_check(stage, name, 'reinforcement keeps some constraint', 'WARN',
                                 f"headroom grows x{max(growth.values()):,.0f} by {target_year}: constraint will "
                                 f"effectively disappear (unconstrained-grid case)")
            else:
                try:
                    table, label = headroom_table_for(sc)
                    years = sorted({y for y, _ in table})
                    zones = {z for _, z in table}
                    missing = [z for z in HEADROOM_ZONES if z not in zones]
                    record_check(stage, name, 'headroom curve has every zone', 'FAIL' if missing else 'PASS',
                                 f"'{sc['headroom_curve']}' missing {missing}" if missing else os.path.basename(label))
                    if len(years) > 1 and (years[0] > 2026 or years[-1] < int(sc.get('target_year', 2050))):   # one year = held flat on purpose
                        record_check(stage, name, 'headroom curve covers 2026-target year', 'WARN',
                                     f"{years[0]}-{years[-1]}; years outside are held at the nearest year")
                except FileNotFoundError as e:
                    record_check(stage, name, 'headroom curve found', 'FAIL', str(e))
                except ValueError as e:
                    record_check(stage, name, 'reinforcement_steps readable', 'FAIL', str(e))
            if str(sc.get('offshore_connection', DEFAULT_OFFSHORE_CONNECTION)).lower() not in ('own', 'shared'):
                record_check(stage, name, 'offshore_connection valid', 'FAIL',
                             f"'{sc.get('offshore_connection')}'; use own or shared")
            cs = sc['capacity_source']
            if cs not in CAPACITY_SOURCES:
                record_check(stage, name, 'capacity_source valid', 'FAIL', f"'{cs}'; use one of {CAPACITY_SOURCES}")
            elif cs == 'pipeline':
                ty = pd.to_numeric(sc['pipeline_target_year'], errors='coerce')
                ok = pd.notna(ty) and float(ty).is_integer() and PIPELINE_START_YEAR <= ty <= 2050
                record_check(stage, name, 'pipeline_target_year valid', 'PASS' if ok else 'FAIL',
                             f"{int(ty)}" if ok else f"got '{sc['pipeline_target_year']}'; need a year "
                                                     f"{PIPELINE_START_YEAR}-2050 (blank = {DEFAULT_PIPELINE_TARGET_YEAR})")
                if ok:
                    sc['pipeline_target_year'] = int(ty)
                    done = pipeline_complete_year(sc['pipeline_target_year'], sc['pipeline_build_pct'])
                    if done > 2050:
                        built = 100 * (2050 - 2026) / (done - 2026)
                        record_check(stage, name, f'pipeline complete by {target_year}', 'WARN',
                                     f"at {sc['pipeline_build_pct']:g}% only {built:.0f}% of the pipeline is "
                                     f"online by {target_year} (complete {done:.1f})")
                if gen_list is None:
                    record_check(stage, name, 'generator list available', 'FAIL',
                                 f"'{GENERATION_LIST_FILE}' not found in {INPUT_DIR}")
            else:
                ignored = [c for c in ('pipeline_target_year', 'pipeline_build_pct') if c not in sc['defaulted']
                           and not (c == 'pipeline_target_year' and sc[c] == DEFAULT_PIPELINE_TARGET_YEAR)
                           and not (c == 'pipeline_build_pct' and sc[c] == DEFAULT_PIPELINE_BUILD_PCT)]
                if ignored:
                    record_check(stage, name, 'pipeline settings used', 'WARN',
                                 f"{ignored} ignored because capacity_source=rates")

    def headroom_table_for(sc):
        """(table, description) for a scenario's headroom_curve. Every built-in option starts from the
        calibrated 2026 headroom: TID / default = the published path rebased on it
        each run, reinforcement_pct = compound %/yr on it. Any other CSV is used exactly as written."""
        name = sc.get('headroom_curve', DEFAULT_HEADROOM_CURVE) or DEFAULT_HEADROOM_CURVE
        if is_reinforcement_curve(name):
            table, desc = (reinforcement_headroom_table(headroom_base, sc['ie_reinforcement_pct'], sc['ni_reinforcement_pct'], int(sc.get('target_year', 2050))),
                           f"calibrated 2026 headroom x (1 + IE {sc['ie_reinforcement_pct']:g}% / NI "
                           f"{sc['ni_reinforcement_pct']:g}%)^years")
        elif is_hybrid_tid_2035_curve(name):
            # Use the published/rebased TID zonal path exactly through 2035. From 2036 onward,
            # simplify to compound annual growth from each zone's 2035 headroom.
            table = {(y, z): v for (y, z), v in default_table.items() if y <= 2035}
            for z in HEADROOM_ZONES:
                base_2035 = headroom_for_year(default_table, 2035, 1.0)[z]
                rate = (sc['ni_reinforcement_pct'] if z == 'NI' else sc['ie_reinforcement_pct']) / 100.0
                for y in range(2036, int(sc.get('target_year', 2050)) + 1):
                    table[(y, z)] = base_2035 * (1.0 + rate) ** (y - 2035)
            desc = (f"published TID path rebased on calibrated 2026 headroom through 2035; "
                    f"then IE {sc['ie_reinforcement_pct']:g}% / NI {sc['ni_reinforcement_pct']:g}% per year to {int(sc.get('target_year', 2050))}")
        elif is_reinforcement_mw_curve(name):
            table, desc = (reinforcement_mw_headroom_table(headroom_base, sc['ie_reinforcement_mw_per_year'],
                                                           sc['ni_reinforcement_mw_per_year'], int(sc.get('target_year', 2050))),
                           f"calibrated 2026 headroom + IE {sc['ie_reinforcement_mw_per_year']:g} / NI "
                           f"{sc['ni_reinforcement_mw_per_year']:g} MW per year")
        else:
            path = resolve_headroom_curve(name)
            if os.path.abspath(path) == os.path.abspath(input_path(HEADROOM_FILE)):
                table, desc = default_table, f"{path} path, rebased on the calibrated 2026 headroom"
            else:
                table, desc = load_zonal_headroom(path)[0], path
        steps = parse_reinforcement_steps(sc.get('reinforcement_steps', ''))
        if steps:
            table = apply_reinforcement_steps(table, steps)
            desc += "; steps " + ", ".join(f"{z} +{mw:g} MW from {y}" for z, y, mw in steps)
        return table, desc

    def pipeline_complete_year(target_year, build_pct):
        """Year the whole pipeline is online: normal speed reaches it at target_year."""
        return 2026 + (target_year - 2026) * 100.0 / build_pct

    def validate_results(name, sim_df, capacity_df, balance_err_by_year):
        """Sanity checks on one scenario's forecast; recorded, never stop the run."""
        stage = 'results'
        worst_year = max(balance_err_by_year, key=balance_err_by_year.get)
        worst = balance_err_by_year[worst_year]
        record_check(stage, name, 'energy balance (available = usable + constrained + curtailed + stored)',
                     'PASS' if worst <= 0.001 else ('WARN' if worst <= 0.1 else 'FAIL'),
                     f"largest gap {worst:.4f}% of available energy ({worst_year})")
        pct_cols = [c for c in sim_df.columns if c.endswith('%')]
        bad = [f"{c} {sim_df[c].min():.2f}..{sim_df[c].max():.2f}" for c in pct_cols
               if sim_df[c].min() < -0.01 or sim_df[c].max() > 100.01]
        record_check(stage, name, 'percentages within 0-100', 'FAIL' if bad else 'PASS', '; '.join(bad))
        shrink = [c for c in ('Wind_Cap_GW', 'Solar_Cap_GW', 'Storage_Power_MW', 'Storage_Energy_MWh')
                  if (sim_df[c].diff().dropna() < -1e-6).any()]
        record_check(stage, name, 'installed capacity never falls', 'FAIL' if shrink else 'PASS',
                     f"falls in {shrink}" if shrink else '')
        by_year = capacity_df.groupby('Year')[['Wind_Onshore_MW', 'Wind_Offshore_MW', 'Solar_MW', 'Battery_MW']].sum()
        totals = sim_df.set_index('Year')
        gaps = {
            'onshore wind': (by_year['Wind_Onshore_MW'] - 1000 * totals['Wind_Onshore_GW']).abs().max(),
            'offshore wind': (by_year['Wind_Offshore_MW'] - 1000 * totals['Wind_Offshore_GW']).abs().max(),
            'solar': (by_year['Solar_MW'] - 1000 * totals['Solar_Cap_GW']).abs().max(),
            'battery': (by_year['Battery_MW'] - totals['Storage_Power_MW']).abs().max(),
        }
        off = {k: round(v, 1) for k, v in gaps.items() if v > 10.0}   # totals are rounded to 0.01 GW
        record_check(stage, name, 'zone capacities add up to the totals', 'FAIL' if off else 'PASS',
                     f"largest gap MW: {off}" if off else '')

    backcast_store = {}   # scenario name -> (backcast table, error summary)
    capacity_store = {}   # scenario name -> capacity by zone and year
    summary_store = {}    # scenario name -> {'wind' / 'solar' / 'total' / 'system': yearly summary}
    evaluation_store = {}  # scenario name -> curtailment and capacity-factor tracking table
    latest_results = {}   # scenario name -> results, saved before the charts are drawn
    scenario_stage = {}   # scenario name -> 'model' or 'charts', for error messages

    def run_scenario(sc, out_dir, make_charts=True, interconnector_chart_sensitivities=False):
        # The 2026 weather-completion step updates the merged 15-minute frame
        # defined in run_demonstrator(). Declaring it nonlocal prevents Python
        # from treating merged as an uninitialised local variable here.
        nonlocal merged
        # Start every scenario from the same 15-minute data. The completion step below rewrites
        # 2026, so without this each scenario after the first would run on the previous one's
        # rewritten data and results would depend on run order.
        merged = merged_input.copy()
        os.makedirs(out_dir, exist_ok=True)
        # Use the unique scenario identifier from the scenario input workbook in
        # every plot filename and title. load_scenarios() has already converted
        # spaces and filename-unsafe characters to underscores.
        scenario_name = str(sc['scenario'])
        final_year = int(round(float(sc.get('target_year', 2050))))
        target_year = final_year

        def scenario_plot_filename(suffix):
            return f"{scenario_name}_{suffix}"

        # Compound reinforcement that grows headroom more than 20x by {target_year} removes network
        # constraint altogether: label such scenarios as an unconstrained-grid bound.
        if is_reinforcement_curve(sc.get('headroom_curve', '')):
            headroom_growth_2050 = max((1 + float(sc[f'{r.lower()}_reinforcement_pct']) / 100.0) ** (2050 - 2026)
                                       for r in REGIONS)
        else:
            headroom_growth_2050 = 1.0
        unconstrained_bound = headroom_growth_2050 > 20
        headroom_note = (f"Unconstrained-grid bound (headroom x{headroom_growth_2050:,.0f} by {target_year}), not a build path"
                         if unconstrained_bound else '')
        sc['headroom_note'] = headroom_note
        if unconstrained_bound:
            print(f">> NOTE: {headroom_note}")

        def scenario_plot_title(title):
            """Return a compact two-line plot title.

            The scenario label is always on line 1 and the chart description is
            always on line 2. Any newline supplied by a caller is collapsed so
            titles remain exactly two lines and do not widen the plot canvas.
            """
            compact_title = ' | '.join(
                part.strip() for part in str(title).splitlines() if part.strip())
            scenario_line = scenario_name
            if unconstrained_bound:
                scenario_line += ' [unconstrained-grid bound]'
            return f"{scenario_line}\n{compact_title}"

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
        background_demand_growth_rate = float(sc['background_demand_growth_twh_per_year'])
        heat_demand_growth_rate = float(sc['heat_demand_growth_twh_per_year'])
        transport_demand_growth_rate = float(sc['transport_demand_growth_twh_per_year'])
        annual_demand_growth_rate = (background_demand_growth_rate + heat_demand_growth_rate
                                     + transport_demand_growth_rate)
        # Heat and transport growth built into a demand path (see demand_for_year).
        _ph = float(sc.get('path_heat_growth_twh_per_year', float('nan')))
        _pt = float(sc.get('path_transport_growth_twh_per_year', float('nan')))
        path_heat_growth_rate = _ph if np.isfinite(_ph) else heat_demand_growth_rate
        path_transport_growth_rate = _pt if np.isfinite(_pt) else transport_demand_growth_rate

        # 2026 is a transition year before the assumed decarbonisation and
        # electrification trajectory begins. Use a fixed 0.9 TWh increase over
        # the 2025 actual demand. The scenario-specific annual demand rate then
        # applies from 2027 onward.
        demand_increase_2026_twh = 0.9
        base_demand_twh = demand_2025_twh + demand_increase_2026_twh
        tot_demand_final = base_demand_twh + (hzn * annual_demand_growth_rate)
    
        # Build rates by technology and region (GW/yr). The model uses the total per technology
        # and the IE share of it, which sets where the new capacity connects.
        bw_ie, bw_ni = max(0.0, float(sc['build_rate_wind_ie'])), max(0.0, float(sc['build_rate_wind_ni']))
        bs_ie, bs_ni = max(0.0, float(sc['build_rate_solar_ie'])), max(0.0, float(sc['build_rate_solar_ni']))
        annual_build_rate_gw = bw_ie + bw_ni
        snsp_limit_pct = float(sc['snsp_limit_pct'])
        snsp_limit_fraction = snsp_limit_pct / 100.0
        # Convert the scenario's regional unit counts into one all-island minimum-
        # generation floor. Defaults are 4 IE + 3 NI = 7 units, so the default
        # floor is 7 x 150 MW = 1,050 MW.
        muon_units_ie = max(0, int(round(float(sc['muon_units_ie']))))
        muon_units_ni = max(0, int(round(float(sc['muon_units_ni']))))
        total_muon_units = muon_units_ie + muon_units_ni
        muon_floor_mw = total_muon_units * MUON_MIN_GEN_PER_UNIT_MW
        storage_power_build_rate_mw = max(0.0, float(sc['storage_power_build_rate_mw']))
        storage_energy_build_rate_mwh = max(0.0, float(sc['storage_energy_build_rate_mwh']))
        storage_power_2026_mw = max(0.0, float(sc['storage_power_2026_mw']))
        storage_energy_2026_mwh = max(0.0, float(sc['storage_energy_2026_mwh']))
        storage_charge_efficiency = np.clip(float(sc['storage_charge_efficiency']), 1e-9, 1.0)
        storage_discharge_efficiency = np.clip(float(sc['storage_discharge_efficiency']), 1e-9, 1.0)
        storage_initial_soc_pct = np.clip(float(sc['storage_initial_soc_pct']), 0.0, 100.0)
        pc_storage_hybrid = np.clip(float(sc['pc_storage_hybrid']), 0.0, 100.0)
        # V9: scenario picks a headroom curve (TID or a CSV), or reinforcement_pct
        # to grow each zone's 2026 headroom at the scenario's ie/ni_reinforcement_pct as V8 did.
        headroom_scale = float(sc.get('headroom_scale', DEFAULT_HEADROOM_SCALE) or DEFAULT_HEADROOM_SCALE)
        headroom_curve_name = sc.get('headroom_curve', DEFAULT_HEADROOM_CURVE) or DEFAULT_HEADROOM_CURVE
        headroom_table, curve_path = headroom_table_for(sc)
        headroom_years = sorted({y for y, _ in headroom_table})
        bw_off = max(0.0, float(sc.get('build_rate_wind_offshore', DEFAULT_BUILD_RATE_WIND_OFFSHORE) or 0.0))
        offshore_own = str(sc.get('offshore_connection', DEFAULT_OFFSHORE_CONNECTION)).strip().lower() != 'shared'
        # Zones shown in the readable summaries. With its own connection, offshore is a zone of its own.
        summary_zones = HEADROOM_ZONES + (['OFFSHORE'] if offshore_own else [])

        def jurisdiction_zones(region):
            if region == 'NI':
                return ['NI']
            return IE_ZONES + (['OFFSHORE'] if 'OFFSHORE' in summary_zones else [])

        def jurisdiction_twh(run, kind, region):
            """Wind + solar energy (TWh/yr) of one kind (avail, con, curt) summed over a jurisdiction's zones."""
            return sum(run.get(f'z_{tech}_{kind}_{z}', 0.0)
                       for z in jurisdiction_zones(region) for tech in ('wind', 'solar'))

        def jurisdiction_pct(run, kind, region):
            """Constraint or curtailment as % of the jurisdiction's own available wind + solar energy."""
            av = jurisdiction_twh(run, 'avail', region)
            return 100.0 * jurisdiction_twh(run, kind, region) / av if av > 0 else 0.0

        def jurisdiction_surplus_pct(run, region):
            """System surplus shared by the jurisdiction's part of curtailment, % of its available energy."""
            curt_all = sum(jurisdiction_twh(run, 'curt', r) for r in REGIONS)
            av = jurisdiction_twh(run, 'avail', region)
            if curt_all <= 0 or av <= 0:
                return 0.0
            return 100.0 * run['sys_curt_surplus_twh'] * jurisdiction_twh(run, 'curt', region) / curt_all / av
        # Interconnectors (issues #5, #8, #9)
        celtic_year = float(sc.get('celtic_energised_year', DEFAULT_CELTIC_ENERGISED_YEAR))
        mares_year = float(sc.get('mares_energised_year', DEFAULT_MARES_ENERGISED_YEAR))
        ic_export_availability = float(sc.get('ic_export_availability', DEFAULT_IC_EXPORT_AVAILABILITY))
        ic_import_availability = float(sc.get('ic_import_availability', DEFAULT_IC_IMPORT_AVAILABILITY))
        ic_capacity_credit = float(sc.get('ic_capacity_credit', DEFAULT_IC_CAPACITY_CREDIT))

        def ic_links_for_year(year):
            """{link: MW in service, averaged over the year} for interconnectors to GB/France."""
            def in_service(energised):
                return float(np.clip(year + 1 - energised, 0.0, 1.0))
            return {'existing': EXISTING_INTERCONNECTOR_CAPACITY_MW,
                    'Celtic': CELTIC_INTERCONNECTOR_CAPACITY_MW * in_service(celtic_year),
                    'MaresConnect': MARES_INTERCONNECTOR_CAPACITY_MW * in_service(mares_year)}

        def ic_capacity_for_year(year):
            return sum(ic_links_for_year(year).values())

        def largest_infeed_mw(year):
            links = ic_links_for_year(year)
            single = [LARGEST_UNIT_INFEED_MW]
            single += [CELTIC_INTERCONNECTOR_CAPACITY_MW] if links['Celtic'] > 0 else []
            single += [MARES_INTERCONNECTOR_CAPACITY_MW] if links['MaresConnect'] > 0 else []
            return max(single)

        def ic_dispatch_caps(year):
            """Usable export and import MW. Zero unless INTERCONNECTOR_DISPATCH is True (reversed
            24 Oct 2026: interconnectors are shown only in the chart-only sensitivities)."""
            if not INTERCONNECTOR_DISPATCH:
                return 0.0, 0.0
            cap = ic_capacity_for_year(year)
            return cap * ic_export_availability, cap * ic_import_availability
        new_build_ie_share = bw_ie / annual_build_rate_gw if annual_build_rate_gw > 0 else base_ie_share
        solar_build_rate_gw = bs_ie + bs_ni
        solar_new_build_ie_share = bs_ie / solar_build_rate_gw if solar_build_rate_gw > 0 else base_solar_ie_share

        print(f"\n>> Baseline Demand (2026): {base_demand_twh:.2f} TWh")
        print(f">> 2026 Demand Increase over 2025: {demand_increase_2026_twh:.2f} TWh")
        print(f">> Background Demand Growth from 2027: {background_demand_growth_rate:.2f} TWh/year")
        print(f">> Heat-Sector Electricity Growth from 2027: {heat_demand_growth_rate:.2f} TWh/year")
        print(f">> Transport-Sector Electricity Growth from 2027: {transport_demand_growth_rate:.2f} TWh/year")
        print(f">> Total Scenario Demand Growth from 2027: {annual_demand_growth_rate:.2f} TWh/year")
        print(f">> Projected Total Demand in {final_year}: {tot_demand_final:.2f} TWh")
        print(f">> Wind build-out: IE onshore {bw_ie:.3f} + NI {bw_ni:.3f} + offshore {bw_off:.3f} GW/year")
        print(f">> Solar build-out: IE {bs_ie:.3f} + NI {bs_ni:.3f} = {solar_build_rate_gw:.3f} GW/year")
        print(f">> Capacity: {final_2026_wind_capacity_gw:.2f} GW onshore in 2026; offshore build from 2027")
        print(f">> Selected Forecast Operational SNSP Limit: {snsp_limit_pct:.1f}%")
        print(f">> MUON floor: IE {muon_units_ie} + NI {muon_units_ni} = {total_muon_units} units; "
              f"{total_muon_units} x {MUON_MIN_GEN_PER_UNIT_MW:.0f} MW = {muon_floor_mw:.0f} MW SEM")
        print(f">> Standalone storage in 2026: {storage_power_2026_mw:.0f} MW / {storage_energy_2026_mwh:.0f} MWh")
        print(f">> Storage build-out: {storage_power_build_rate_mw:.0f} MW/yr and {storage_energy_build_rate_mwh:.0f} MWh/yr")
        print(f">> Total storage in 2026: {storage_power_2026_mw:.0f} MW / {storage_energy_2026_mwh:.0f} MWh")
        print(f">> Storage fleet split: {pc_storage_hybrid:.1f}% hybrid/co-located and {100-pc_storage_hybrid:.1f}% standalone.")
        print(">> BESS charging is included in demand before SNSP/MUON curtailment is calculated.")
        print(f">> Headroom curve '{headroom_curve_name}' → {curve_path} "
              f"({headroom_years[0]}-{headroom_years[-1]}, scale={headroom_scale:.2f})")
        if not (is_reinforcement_curve(headroom_curve_name) or is_hybrid_tid_2035_curve(headroom_curve_name)):
            print(f">> ie/ni_reinforcement_pct not used (only with headroom_curve={REINFORCEMENT_CURVE} or {HYBRID_TID_2035_CURVE})")
        capacity_source = sc.get('capacity_source', DEFAULT_CAPACITY_SOURCE)
        use_pipeline = capacity_source == 'pipeline'
        if use_pipeline:
            target_year = int(sc['pipeline_target_year'])
            build_pct = float(sc['pipeline_build_pct'])
            complete_year = pipeline_complete_year(target_year, build_pct)
            built_2050 = min(1.0, (final_year - start_year) / (complete_year - start_year))
            print(f">> Capacity source: ECP-GSS-1 pipeline by zone at {build_pct:g}% of the normal build "
                  f"(normal = all online by {target_year}): added evenly from {PIPELINE_START_YEAR}, complete "
                  f"{complete_year:.1f}, {100 * built_2050:.0f}% online by {final_year}. Once complete the GW/yr "
                  f"and storage MW/yr rates above continue, split like the pipeline. NI uses its GW/yr rate.")
            print(f">> Offshore wind: {'own connection (headroom = installed offshore capacity)' if offshore_own else 'shares the headroom of its own ECP area zone'}; "
                  f"profile scale={OFFSHORE_PROFILE_SCALE}")
        else:
            target_year = complete_year = None
            print(f">> Capacity source: GW/yr build rates; OFFSHORE {'has its own connection' if offshore_own else 'shares SE headroom'}; "
                  f"profile scale={OFFSHORE_PROFILE_SCALE}")
        defaulted = [k for k in sc.get('defaulted', []) if k != 'description']
        print(f">> Inputs left blank (defaults used): {', '.join(defaulted) if defaulted else 'none'}")
        # Optional year-by-year path (Data_inputs/scenario_paths/<name>.csv); see load_scenario_path.
        scenario_path_df = load_scenario_path(sc.get('scenario_path', ''))
        if scenario_path_df is not None:
            print(f">> Scenario path '{sc['scenario_path']}': {', '.join(scenario_path_df.columns)} "
                  f"set for {', '.join(str(y) for y in scenario_path_df.index)}")

        def path_has(col):
            return scenario_path_df is not None and col in scenario_path_df.columns \
                and scenario_path_df[col].notna().any()

        def path_value(col, year, base_2026, rate_per_year=0.0):
            """Value of a path column in `year`: straight lines between the listed years, from the
            2026 model value before the first one, and the last value plus `rate_per_year` per
            year after the last one."""
            s_col = scenario_path_df[col].dropna()
            ys, vs = list(s_col.index), list(s_col.values)
            if ys[0] > start_year:
                ys, vs = [start_year] + ys, [base_2026] + vs
            if year >= ys[-1]:
                return float(vs[-1]) + rate_per_year * (year - ys[-1])
            return float(np.interp(year, ys, vs))
        print(f">> Solar: {solar_capacity_2026_gw:.2f} GW in 2026, adding {solar_build_rate_gw:.3f} GW each year "
              f"from 2027, capacity factor {100 * SOLAR_CAPACITY_FACTOR:.0f}%")

        # 4. Weather-Loop Simulation & Loss Scaling Forecast
        print("\n====================================================================")
        print(" 4. WEATHER-LOOP SIMULATION & LOSS SCALING FORECAST (2026 - 2050)")
        print("====================================================================")
        base_capacity_gw = final_2026_wind_capacity_gw
    
        simulation_years = list(range(start_year, final_year + 1))
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

        completed_2026 = pd.concat([actual_2026, missing_2026], ignore_index=True, sort=False)
        completed_2026 = completed_2026.sort_values('parsed_date').drop_duplicates('parsed_date', keep='first')
        merged['Weather_Data_Source'] = np.where(merged['year'] == 2026, '2026 SEM actual', 'Historical actual')
        merged = pd.concat([merged.loc[merged['year'] != 2026], completed_2026], ignore_index=True, sort=False)
        merged = merged.sort_values('parsed_date').reset_index(drop=True)

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
        # Solve the offshore yield factor k on the reference weather year (see OFFSHORE_CF_REFERENCE).
        global OFFSHORE_YIELD_K
        _ref = merged.loc[merged['year'] == OFFSHORE_CF_REFERENCE_YEAR, 'spec_avail_mw_per_gw'].clip(lower=0).to_numpy()
        if OFFSHORE_CF_REFERENCE > 0 and len(_ref):
            lo, hi = 0.5, 4.0
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if np.minimum(_ref * mid, 1000.0).mean() / 1000.0 < OFFSHORE_CF_REFERENCE:
                    lo = mid
                else:
                    hi = mid
            OFFSHORE_YIELD_K = 0.5 * (lo + hi)
        _cfs = {int(y): (round(g['spec_avail_mw_per_gw'].clip(lower=0).mean() / 10.0, 1),
                         round(np.minimum(g['spec_avail_mw_per_gw'].clip(lower=0).to_numpy() * OFFSHORE_YIELD_K,
                                          1000.0).mean() / 10.0, 1))
                for y, g in merged.loc[merged['year'] <= 2026].groupby('year')}
        print(f">> Offshore yield: k = {OFFSHORE_YIELD_K:.3f} (offshore available CF {OFFSHORE_CF_REFERENCE:.0%} "
              f"in weather year {OFFSHORE_CF_REFERENCE_YEAR}). Available CF % onshore / offshore by weather year: {_cfs}")
        print(f">> Offshore yield mean over weather years: onshore "
              f"{np.mean([v[0] for v in _cfs.values()]):.1f}%, offshore {np.mean([v[1] for v in _cfs.values()]):.1f}%")
        # Weather years used for the energy results after 2026 (scenario 'weather_years'; blank = all).
        # EirGrid's constraint studies use 2020 weather only, so the validation runs do too.
        scenario_weather_years = parse_weather_years(sc.get('weather_years', ''), complete_weather_years)
        if scenario_weather_years != complete_weather_years:
            print(f">> Weather years for results after 2026: {scenario_weather_years}")

        # The forecast model is all-island SEM: demand, wind generation, wind
        # availability, installed capacity, wind share and fleet CF all use SEM totals.
        # Pipeline phasing: share of the due-to-connect MW online in a year (0 in 2026, 1 once the
        # pipeline is complete), and the years after completion in which the GW/yr rates apply.
        def pipeline_fraction(year):
            if not use_pipeline:
                return 0.0
            return float(np.clip((year - start_year) / (complete_year - start_year), 0.0, 1.0))

        def years_after_pipeline(year):
            return max(0.0, year - complete_year) if use_pipeline else 0

        def zone_split(mw_by_zone):
            total = sum(mw_by_zone.values())
            return {z: (mw_by_zone.get(z, 0.0) / total if total > 0 else 0.0) for z in IE_ZONES}

        if use_pipeline:
            pipe_share = {t: zone_split(pipe_mw[t]) for t in pipe_mw}
            # The 2026 IE solar base is split like the 2026 IE onshore wind fleet, as in rates mode
            base_ie_on = sum(zone_shares[z]['share_of_onshore'] for z in IE_ZONES)
            base_solar_zone_w = {z: zone_shares[z]['share_of_onshore'] / base_ie_on for z in IE_ZONES}

        base_ie_onshore_gw = base_capacity_gw * sum(zone_shares[z]['share_of_onshore'] for z in IE_ZONES)
        base_ni_onshore_gw = base_capacity_gw * zone_shares['NI']['share_of_onshore']
        ie_onshore_weights = (pipe_share['wind'] if use_pipeline
                              else {z: zone_shares[z]['share_of_ie_onshore'] for z in IE_ZONES})

        def zone_caps_for_year(year):
            """Onshore GW by zone, plus separate offshore GW. Existing fleet by zone shares.
            Rates: new IE onshore by IE zone weights. Pipeline: due-to-connect MW by zone, then the
            IE rate split like the pipeline. New NI to NI in both. A scenario path, where given,
            sets the IE and NI onshore totals; new IE onshore is split as above."""
            elapsed = max(0, year - start_year)
            frac, after = pipeline_fraction(year), years_after_pipeline(year)
            caps = {}
            for z in HEADROOM_ZONES:
                base_z = base_capacity_gw * zone_shares[z]['share_of_onshore']
                if z == 'NI':
                    new_z = (path_value('ni_onshore_gw', year, base_ni_onshore_gw, bw_ni) - base_ni_onshore_gw
                             if path_has('ni_onshore_gw') else elapsed * bw_ni)
                    new_z = max(-base_z, new_z)
                elif path_has('ie_onshore_gw'):
                    new_ie = max(0.0, path_value('ie_onshore_gw', year, base_ie_onshore_gw, bw_ie) - base_ie_onshore_gw)
                    new_z = new_ie * ie_onshore_weights[z]
                elif use_pipeline:
                    new_z = frac * pipe_mw['wind'][z] / 1000.0 + after * bw_ie * pipe_share['wind'][z]
                else:
                    new_z = elapsed * bw_ie * zone_shares[z]['share_of_ie_onshore']
                caps[z] = base_z + new_z
            offshore_gw = sum(offshore_caps_for_year(year).values())
            onshore_gw = sum(caps.values())
            return onshore_gw, offshore_gw, caps

        def offshore_caps_for_year(year):
            """Offshore GW by the zone whose headroom it shares (rates: all SE). A scenario path, where
            given, sets the offshore total (dated projects); after its last year the offshore GW/yr
            rate applies. With its own connection the zone only matters for reporting."""
            if path_has('offshore_gw'):
                total = max(0.0, path_value('offshore_gw', year, 0.0, bw_off))
                if use_pipeline:
                    return {z: total * pipe_share['offshore'][z] for z in IE_ZONES}
                return {'SE': total}
            if not use_pipeline:
                return {'SE': max(0, year - start_year) * bw_off}
            frac, after = pipeline_fraction(year), years_after_pipeline(year)
            return {z: frac * pipe_mw['offshore'][z] / 1000.0 + after * bw_off * pipe_share['offshore'][z]
                    for z in IE_ZONES}

        def capacity_for_year(year):
            """Total installed wind GW (onshore + offshore)."""
            onshore_gw, offshore_gw, _ = zone_caps_for_year(year)
            return onshore_gw + offshore_gw

        def ie_share_for_year(year):
            onshore_gw, offshore_gw, caps = zone_caps_for_year(year)
            total = onshore_gw + offshore_gw
            if total <= 0:
                return base_ie_share
            ie_on = sum(caps[z] for z in IE_ZONES)
            return (ie_on + offshore_gw) / total

        def solar_capacity_for_year(year):
            if use_pipeline or path_has('ie_solar_gw') or path_has('ni_solar_gw'):
                return sum(solar_caps_for_year(year).values())
            return solar_capacity_2026_gw + max(0, year - start_year) * solar_build_rate_gw

        def solar_caps_for_year(year):
            """Solar GW by zone. Rates: IE share split by that year's onshore wind weights, as V9 did.
            Pipeline: 2026 base split like the 2026 wind fleet, plus due-to-connect solar by zone."""
            elapsed = max(0, year - start_year)
            if path_has('ie_solar_gw') or path_has('ni_solar_gw'):
                base_ie = solar_capacity_2026_gw * base_solar_ie_share
                base_ni = solar_capacity_2026_gw - base_ie
                ie_tot = (path_value('ie_solar_gw', year, base_ie, bs_ie) if path_has('ie_solar_gw')
                          else base_ie + elapsed * bs_ie)
                ni_tot = (path_value('ni_solar_gw', year, base_ni, bs_ni) if path_has('ni_solar_gw')
                          else base_ni + elapsed * bs_ni)
                if use_pipeline:
                    new_ie = max(0.0, ie_tot - base_ie)
                    caps = {z: base_ie * base_solar_zone_w[z] + new_ie * pipe_share['solar'][z] for z in IE_ZONES}
                else:
                    _, _, wind_caps = zone_caps_for_year(year)
                    ie_on_gw = sum(wind_caps[z] for z in IE_ZONES) or 1e-9
                    caps = {z: ie_tot * wind_caps[z] / ie_on_gw for z in IE_ZONES}
                caps['NI'] = max(0.0, ni_tot)
                return caps
            if use_pipeline:
                frac, after = pipeline_fraction(year), years_after_pipeline(year)
                base_ie = solar_capacity_2026_gw * base_solar_ie_share
                caps = {z: base_ie * base_solar_zone_w[z] + frac * pipe_mw['solar'][z] / 1000.0
                           + after * bs_ie * pipe_share['solar'][z] for z in IE_ZONES}
                caps['NI'] = solar_capacity_2026_gw * (1.0 - base_solar_ie_share) + elapsed * bs_ni
                return caps
            solar_gw = solar_capacity_for_year(year)
            s_ie = solar_ie_share_for_capacity(solar_gw)
            _, _, wind_caps = zone_caps_for_year(year)
            ie_on_gw = sum(wind_caps[z] for z in IE_ZONES) or 1e-9
            caps = {z: solar_gw * s_ie * wind_caps[z] / ie_on_gw for z in IE_ZONES}
            caps['NI'] = solar_gw * (1.0 - s_ie)
            return caps

        battery_hours_target = max(0.0, float(sc.get('battery_hours_target', 0.0) or 0.0))
        battery_hours_target_year = int(sc.get('battery_hours_target_year', 2035) or 2035)

        def storage_for_year(year):
            """Fleet MW and MWh. With battery_hours_target set (e.g. 4), the MW build is unchanged and the
            fleet's average duration rises linearly from its 2026 value to the target by
            battery_hours_target_year, then holds; MWh never falls below the build path."""
            power, energy = _storage_for_year_built(year)
            if battery_hours_target > 0 and power > 0:
                h0 = storage_energy_2026_mwh / storage_power_2026_mw if storage_power_2026_mw > 0 else battery_hours_target
                f = min(1.0, max(0.0, (year - start_year) / max(1, battery_hours_target_year - start_year)))
                energy = max(energy, power * (h0 + f * (battery_hours_target - h0)))
            return power, energy

        def _storage_for_year_built(year):
            elapsed = max(0, year - start_year)
            if path_has('storage_mw'):
                power = max(0.0, path_value('storage_mw', year, storage_power_2026_mw, storage_power_build_rate_mw))
                if path_has('storage_mwh'):
                    energy = path_value('storage_mwh', year, storage_energy_2026_mwh, storage_energy_build_rate_mwh)
                else:
                    energy = storage_energy_2026_mwh + (power - storage_power_2026_mw) * PIPELINE_BATTERY_HOURS
                return power, max(0.0, energy)
            if use_pipeline:
                frac, after = pipeline_fraction(year), years_after_pipeline(year)
                return (storage_power_2026_mw + frac * sum(pipe_mw['battery'].values())
                        + after * storage_power_build_rate_mw,
                        storage_energy_2026_mwh + frac * sum(pipe_mwh.values())
                        + after * storage_energy_build_rate_mwh)
            return (storage_power_2026_mw + elapsed * storage_power_build_rate_mw,
                    storage_energy_2026_mwh + elapsed * storage_energy_build_rate_mwh)

        def battery_caps_for_year(year):
            """Battery MW / MWh by zone, for reporting only (dispatch is all-island).
            The scenario's 2026 storage and, in rates mode, its MW/yr build have no zone (UNZONED)."""
            power, energy = storage_for_year(year)
            out = {}
            if path_has('storage_mw'):
                return {'UNZONED': (power, energy)}
            if use_pipeline:
                frac, after = pipeline_fraction(year), years_after_pipeline(year)
                bshare = pipe_share['battery']
                for z in IE_ZONES:
                    out[z] = (frac * pipe_mw['battery'][z] + after * storage_power_build_rate_mw * bshare[z],
                              frac * pipe_mwh[z] + after * storage_energy_build_rate_mwh * bshare[z])
            built_e = _storage_for_year_built(year)[1]
            if built_e > 0 and energy > built_e:       # duration rule: extra MWh spread pro rata
                out = {z: (p_, e_ * energy / built_e) for z, (p_, e_) in out.items()}
            zoned_p = sum(v[0] for v in out.values())
            zoned_e = sum(v[1] for v in out.values())
            out['UNZONED'] = (power - zoned_p, energy - zoned_e)
            return out

        def solar_ie_share_for_capacity(cap_gw):
            if cap_gw <= 0:
                return base_solar_ie_share
            added = max(0.0, cap_gw - solar_capacity_2026_gw)
            return (base_solar_ie_share * solar_capacity_2026_gw + solar_new_build_ie_share * added) / cap_gw

        def solar_ie_share_for_year(year):
            caps = solar_caps_for_year(year)
            total = sum(caps.values())
            return sum(caps[z] for z in IE_ZONES) / total if total > 0 else base_solar_ie_share

        def wind_avail_for_year(spec_mw_per_gw, year):
            onshore_gw, offshore_gw, zone_caps = zone_caps_for_year(year)
            wind_on = np.asarray(spec_mw_per_gw, dtype=float) * onshore_gw
            wind_off = (np.minimum(np.clip(np.asarray(spec_mw_per_gw, dtype=float), 0.0, None) * OFFSHORE_YIELD_K,
                                   1000.0) * offshore_gw * OFFSHORE_PROFILE_SCALE)
            return wind_on, wind_off, onshore_gw, offshore_gw, zone_caps

        # Optional sensitivity (headroom_pipeline_cover_pct, default 0): each IE zone's headroom also
        # grows by this % of the onshore wind + solar MW connected in that zone since 2026. It stands
        # for reinforcement built alongside new connections. About 40% reproduces Ireland's constraint
        # in EirGrid's GSS-1 2030 and 2035 cases (about 6%), so it measures the reinforcement EirGrid's
        # results imply. It is fitted to EirGrid, so it is never used in the validation runs.
        headroom_cover = float(sc.get('headroom_pipeline_cover_pct', 0.0) or 0.0) / 100.0
        if headroom_cover > 0:
            _, _, wind_2026 = zone_caps_for_year(start_year)
            solar_2026 = solar_caps_for_year(start_year)
            headroom_table = dict(headroom_table)
            for (y, z) in list(headroom_table):
                if z in IE_ZONES and y > start_year:
                    _, _, wind_y = zone_caps_for_year(y)
                    solar_y = solar_caps_for_year(y)
                    new_mw = 1000.0 * max(0.0, wind_y[z] - wind_2026[z] + solar_y.get(z, 0.0) - solar_2026.get(z, 0.0))
                    headroom_table[(y, z)] += headroom_cover * new_mw
            added = sum(headroom_table[(min(final_year, max(y for y, _ in headroom_table)), z)]
                        for z in IE_ZONES) - sum(headroom_for_year(headroom_table, start_year, 1.0)[z] for z in IE_ZONES)
            print(f">> Headroom sensitivity: IE zones also gain {100 * headroom_cover:g}% of new onshore wind + "
                  f"solar MW; IE headroom up {added:,.0f} MW by {final_year}")

        def demand_for_year(year):
            """All-island demand (TWh): background demand plus heat and transport electricity.

            Background is the path (or 2026 anchor plus growth) less the heat and transport growth
            the path was built with. Heat and transport are then added at this scenario's own
            rates, each stopped at full electrification, since electricity beyond the caps would
            displace no fossil fuel. With the path rates equal to the scenario's own rates this is
            the path less any growth beyond the caps, as before 22 November 2026. Before then a
            sensitivity that changed the rates kept total demand on the path to its last year,
            so faster electrification displaced background demand."""
            if year <= start_year:
                return base_demand_twh
            n = year - start_year
            if path_has('demand_twh'):
                ref_rate = (background_demand_growth_rate + path_heat_growth_rate
                            + path_transport_growth_rate)
                d = path_value('demand_twh', year, base_demand_twh, ref_rate)
                background = d - n * (path_heat_growth_rate + path_transport_growth_rate)
            else:
                background = base_demand_twh + n * background_demand_growth_rate
            heat_0 = BASE_HEAT_ELECTRICITY_TWH_2025 + DEFAULT_HEAT_DEMAND_GROWTH_TWH_PER_YEAR
            trans_0 = BASE_TRANSPORT_ELECTRICITY_TWH_2025 + DEFAULT_TRANSPORT_DEMAND_GROWTH_TWH_PER_YEAR
            heat_cap = ALL_ISLAND_HEAT_DEMAND_TWH / HEAT_COP
            trans_cap = ALL_ISLAND_TRANSPORT_DEMAND_TWH / TRANSPORT_DISPLACEMENT_FACTOR
            heat_inc = max(0.0, min(heat_cap, heat_0 + n * heat_demand_growth_rate) - heat_0)
            trans_inc = max(0.0, min(trans_cap, trans_0 + n * transport_demand_growth_rate) - trans_0)
            return background + heat_inc + trans_inc

        def snsp_fraction_for_year(year):
            """SNSP limit: the 2026 limit in the anchor year, then the path or the scenario value."""
            if year <= start_year:
                return HISTORICAL_SNSP_PCT / 100.0
            if path_has('snsp_pct'):
                return min(1.0, path_value('snsp_pct', year, HISTORICAL_SNSP_PCT) / 100.0)
            return snsp_limit_fraction

        def muon_units_for_year(year):
            ie = path_value('muon_units_ie', year, muon_units_ie) if path_has('muon_units_ie') else muon_units_ie
            ni = path_value('muon_units_ni', year, muon_units_ni) if path_has('muon_units_ni') else muon_units_ni
            return max(0.0, ie), max(0.0, ni)

        def muon_floor_for_year(year):
            return sum(muon_units_for_year(year)) * MUON_MIN_GEN_PER_UNIT_MW

        def snsp_muon_label(year):
            return (f"SNSP: {100 * snsp_fraction_for_year(year):.0f}% | "
                    f"MUON: {muon_floor_for_year(year):.0f} MW")

        if scenario_path_df is not None:
            print(f">> With the path: demand {demand_for_year(final_year):.1f} TWh, SNSP "
                  f"{100 * snsp_fraction_for_year(final_year):.0f}% and minimum units "
                  f"{sum(muon_units_for_year(final_year)):.1f} in {final_year}")

        def dispatch_year(spec_mw_per_gw, solar, demand, year, snsp_fraction,
                          storage_power_mw, storage_energy_mwh):
            wind_on, wind_off, _, _, zone_caps = wind_avail_for_year(spec_mw_per_gw, year)
            headrooms = headroom_for_year(headroom_table, year, headroom_scale)
            return dispatch(wind_on, wind_off, solar, demand, headrooms, zone_caps,
                            offshore_caps_for_year(year), solar_caps_for_year(year),
                            snsp_fraction, storage_power_mw, storage_energy_mwh,
                            storage_charge_efficiency, storage_discharge_efficiency,
                            storage_initial_soc_pct, pc_storage_hybrid, muon_floor_mw=muon_floor_for_year(year),
                            offshore_own=offshore_own, export_cap_mw=ic_dispatch_caps(year)[0],
                            import_cap_mw=ic_dispatch_caps(year)[1])

        heat_base_2026_twh = BASE_HEAT_ELECTRICITY_TWH_2025 + DEFAULT_HEAT_DEMAND_GROWTH_TWH_PER_YEAR

        def heat_extra_twh(year):
            """Heat-pump electricity added since 2026 (TWh/yr), capped at full electrification."""
            full = ALL_ISLAND_HEAT_DEMAND_TWH / HEAT_COP
            now = min(full, heat_base_2026_twh + max(0, year - start_year) * heat_demand_growth_rate)
            return max(0.0, now - heat_base_2026_twh)

        def scenario_demand_mw(df_wy, demand_twh, year):
            """15-minute demand for a weather year: today's demand shape scaled to the demand less the
            added heat-pump load, plus that load shaped by heating degree hours / COP(T) where
            temperature is available (otherwise by the demand shape)."""
            shape = df_wy['sem_demand'].to_numpy(dtype=float)
            n = len(shape)
            if n == 0 or shape.mean() <= 0:
                return shape
            extra = min(heat_extra_twh(year), 0.9 * demand_twh)
            flat_twh = 0.0
            if FLAT_UNDERLYING_GROWTH and year > start_year:
                n_yr = year - start_year
                trans_cap = ALL_ISLAND_TRANSPORT_DEMAND_TWH / TRANSPORT_DISPLACEMENT_FACTOR
                trans_0 = BASE_TRANSPORT_ELECTRICITY_TWH_2025 + DEFAULT_TRANSPORT_DEMAND_GROWTH_TWH_PER_YEAR
                trans_extra = max(0.0, min(trans_cap, trans_0 + n_yr * transport_demand_growth_rate) - trans_0)
                flat_twh = max(0.0, demand_twh - base_demand_twh - extra - trans_extra)
            base = shape * ((demand_twh - extra - flat_twh) * 1e6 / 8760.0) / shape.mean()
            base = base + flat_twh * 1e6 / 8760.0
            w = df_wy['heat_weight'].to_numpy(dtype=float) if 'heat_weight' in df_wy else np.full(n, np.nan)
            if extra > 0 and np.isfinite(w).all() and w.sum() > 0:
                sample_mwh = extra * 1e6 * (n * INTERVAL_HOURS / 8760.0)
                heat = w / w.sum() * sample_mwh / INTERVAL_HOURS
            else:
                heat = shape * (extra * 1e6 / 8760.0) / shape.mean()
            return base + heat

        # Gas supply check: daily mean temperature by calendar day, used where a weather year has
        # no temperature record (2026), and the share of fossil heat left in each year.
        _tc = merged[['parsed_date', 'temp_c']].dropna()
        temp_clim = (_tc.groupby([_tc['parsed_date'].dt.month, _tc['parsed_date'].dt.day])['temp_c'].mean()
                     if len(_tc) else pd.Series(dtype=float))
        heat_full_twh = ALL_ISLAND_HEAT_DEMAND_TWH / HEAT_COP

        def fossil_heat_left(year):
            """Share of 2026 fossil heat still on fuel in this year (1 in 2026, 0 at full electrification)."""
            now = min(heat_full_twh, heat_base_2026_twh + max(0, year - start_year) * heat_demand_growth_rate)
            return max(0.0, heat_full_twh - now) / max(1e-9, heat_full_twh - heat_base_2026_twh)

        gas_records = {}   # (scenario year, weather year) -> daily DataFrame; later runs overwrite

        def gas_daily(df_wy, firm_mw, year, wy):
            """Daily gas demand (GWh/d, GCV) for one weather year, stored in gas_records."""
            fuel_mw, oil_mw = gas_power_fuel_mw(firm_mw, year)
            dates = df_wy['parsed_date'].dt.normalize().to_numpy()
            t = df_wy['temp_c'].to_numpy(dtype=float) if 'temp_c' in df_wy else np.full(len(df_wy), np.nan)
            g = pd.DataFrame({'date': dates, 'power': fuel_mw * INTERVAL_HOURS / 1000.0,
                              'oil': oil_mw * INTERVAL_HOURS / 1000.0, 'peak': fuel_mw / 1000.0, 't': t})
            day = g.groupby('date').agg(power_gwh=('power', 'sum'), oil_gwh_e=('oil', 'sum'),
                                        power_peak_gw=('peak', 'max'), temp_c=('t', 'mean'),
                                        n=('power', 'size'))
            day = day[day['n'] >= 92]   # complete days only
            idx = pd.to_datetime(day.index)
            clim = pd.Series([temp_clim.get((m, d_), np.nan) for m, d_ in zip(idx.month, idx.day)],
                             index=day.index)
            day['temp_c'] = day['temp_c'].fillna(clim).fillna(6.0)
            hdd = np.maximum(0.0, HEATING_BASE_TEMP_C - day['temp_c'])
            day['nonpower_gwh'] = ((GAS_NONPOWER_BASE_GWH_PER_DAY + GAS_NONPOWER_GWH_PER_HDD * hdd)
                                   * fossil_heat_left(year) + GAS_IOM_GWH_PER_DAY)
            day['total_gwh'] = day['power_gwh'] + day['nonpower_gwh']
            day['supply_gwh'] = gas_supply_gwh_per_day(year)
            day['shortfall_gwh'] = (day['total_gwh'] - day['supply_gwh']).clip(lower=0)
            day = day.drop(columns='n').reset_index()
            day.insert(0, 'weather_year', wy)
            day.insert(0, 'year', year)
            gas_records[(year, wy)] = day
            return day

        def run_weather_years(year, demand_twh, snsp_fraction, solar_gw,
                              storage_power_mw, storage_energy_mwh, weather_years=None):
            """Run selected SEM weather years and average their annual results (V9 zonal)."""
            onshore_gw, offshore_gw, zone_caps = zone_caps_for_year(year)
            cap_gw = onshore_gw + offshore_gw
            ie_share = ie_share_for_year(year)
            s_ie = solar_ie_share_for_year(year)
            offshore_caps = offshore_caps_for_year(year)
            solar_caps = solar_caps_for_year(year)
            headrooms = headroom_for_year(headroom_table, year, headroom_scale)
            # The 2026 anchor year runs without interconnector flows, as the calibration did.
            export_cap_mw, import_cap_mw = ic_dispatch_caps(year)
            rows = []
            selected_weather_years = complete_weather_years if weather_years is None else list(weather_years)
            for wy in selected_weather_years:
                df_wy = merged[merged['year'] == wy]
                wind_on, wind_off, _, _, _ = wind_avail_for_year(df_wy['spec_avail_mw_per_gw'].values, year)
                avail = wind_on + wind_off
                solar = df_wy['solar_avail_mw_per_gw'].values * solar_gw
                demand = scenario_demand_mw(df_wy, demand_twh, year)

                d = dispatch(wind_on, wind_off, solar, demand, headrooms, zone_caps, offshore_caps, solar_caps,
                             snsp_fraction,
                             storage_power_mw, storage_energy_mwh,
                             storage_charge_efficiency, storage_discharge_efficiency,
                             storage_initial_soc_pct, pc_storage_hybrid, muon_floor_mw=muon_floor_for_year(year),
                             offshore_own=offshore_own, export_cap_mw=export_cap_mw,
                             import_cap_mw=import_cap_mw)
                reg_w = {r: d['reg'][r]['wind'] for r in REGIONS}
                reg_s = {r: d['reg'][r]['solar'] for r in REGIONS}
                zone_w = {z: d['zones'][z]['wind'] for z in ALL_GEN_ZONES}

                tot_av = avail.sum()
                tot_sv = solar.sum()
                if tot_av <= 0:
                    continue
                to_annual_twh = 0.25 / 1e6 * (365.25 / (len(avail) / 96.0))
                sv = tot_sv if tot_sv > 0 else np.nan
                # Zone own-%: constraint / that zone's availability share of total wind
                onshore_share = {z: float(zone_caps.get(z, 0.0)) / onshore_gw if onshore_gw > 0 else 0.0
                                 for z in HEADROOM_ZONES}
                off_frac = offshore_gw / cap_gw if cap_gw > 0 else 0.0
                on_frac = 1.0 - off_frac
                # 15-minute firm (synchronous) output: residual after domestic wind/solar, BESS
                # and imports, plus the synchronous share of export flows when SNSP binds.
                firm_mw = np.maximum(
                    0.0, demand - d['domestic_vre_mw'] - d['discharge_mw'] - d['import_mw']
                ) + d['export_sync_mw']
                win = None
                if year == start_year and wy == start_year and anchor_record_last_month:
                    win = (df_wy['parsed_date'].dt.month <= anchor_record_last_month).to_numpy(dtype=float)
                gd = gas_daily(df_wy, firm_mw, year, wy)
                row = {
                    'gas_worst_day_gwh': float(gd['total_gwh'].max()) if len(gd) else 0.0,
                    'gas_worst_power_gwh': float(gd['power_gwh'].max()) if len(gd) else 0.0,
                    'gas_days_short': float((gd['shortfall_gwh'] > 0).sum()),
                    'gas_shortfall_gwh': float(gd['shortfall_gwh'].sum()),
                    'gas_power_twh': float(gd['power_gwh'].sum()) / 1000.0 * 365.25 / max(1, len(gd)),
                    'gas_nonpower_twh': float(gd['nonpower_gwh'].sum()) / 1000.0 * 365.25 / max(1, len(gd)),
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
                    # Firm generation is the chronological residual after usable wind,
                    # usable solar and battery discharge. Calculating interval by interval
                    # prevents annual renewable surplus from cancelling Dunkelflaute deficits.
                    # Firm (synchronous) generation: residual after domestic wind/solar, BESS and
                    # imports, plus the synchronous share of export flows when SNSP binds.
                    'firm_generation_twh': firm_mw.sum() * to_annual_twh,
                    'firm_peaking_twh': firm_tranche_split(firm_mw)[1] * to_annual_twh,
                    # Firm residual before imports (MW): the 15-minute series is kept so the peak
                    # and a high percentile can be taken over all weather years together.
                    'firm_residual_series': np.maximum(
                        0.0, demand - d['domestic_vre_mw'] - d['discharge_mw']),
                    'import_twh': d['import_mw'].sum() * to_annual_twh,
                    'export_twh': d['export_mw'].sum() * to_annual_twh,
                    'export_vre_twh': d['export_vre_mw'].sum() * to_annual_twh,
                    'export_sync_twh': d['export_sync_mw'].sum() * to_annual_twh,
                    'storage_end_soc_mwh': d['soc_mwh'][-1] if len(d['soc_mwh']) else 0.0,
                    'remaining_curt_combined_pct': 100 * (d['curt_w'].sum() + d['curt_s'].sum()) / (tot_av + tot_sv),
                    'recoverable_grid_constraint_twh': d['recoverable_grid_constraint_mw'].sum() * to_annual_twh,
                    'grid_constrained_oversupply_twh': d['grid_constrained_oversupply_mw'].sum() * to_annual_twh,
                    'operational_curtailment_oversupply_twh': d['operational_curtailment_oversupply_mw'].sum() * to_annual_twh,
                    # Matched window: anchor year on its own weather, months covered by the record.
                    'window_avail_mwh': (float(((avail + solar) * win).sum()) * INTERVAL_HOURS
                                         if win is not None else np.nan),
                    'window_dd_mwh': (float(((d['con_w'] + d['con_s'] + d['curt_w'] + d['curt_s']) * win).sum())
                                      * INTERVAL_HOURS if win is not None else np.nan),
                    'IE_comb_pct': 100 * (reg_w['IE'].sum() + reg_s['IE'].sum())
                                   / (tot_av * ie_share + tot_sv * s_ie),
                    'NI_comb_pct': 100 * (reg_w['NI'].sum() + reg_s['NI'].sum())
                                   / (tot_av * (1 - ie_share) + tot_sv * (1 - s_ie)),
                    # Energy balance: available = usable + constrained + curtailed + stored, every interval
                    'balance_err_pct': 100 * np.abs(avail + solar - (d['usable_w'] + d['usable_s'] + d['con_w']
                                                     + d['con_s'] + d['curt_w'] + d['curt_s']
                                                     + d['charge_mw'])).sum() / (tot_av + tot_sv),
                }
                for z in HEADROOM_ZONES:
                    z_avail = tot_av * on_frac * onshore_share[z]
                    row[f'Con_{z}_%'] = (100 * zone_w[z].sum() / z_avail) if z_avail > 0 else 0.0
                off_avail = tot_av * off_frac
                row['Con_OFFSHORE_%'] = (100 * zone_w['OFFSHORE'].sum() / off_avail) if off_avail > 0 else 0.0
                # Zone energy by technology (TWh/yr) for the readable summaries. Wind = onshore + the
                # offshore that shares the zone's headroom. SNSP curtailment is system-wide: each interval
                # it is shared over zones in proportion to their output left after constraint (the same
                # rule that splits it between wind and solar), so the zones add up to the all-island total.
                off_tot, sol_tot = sum(offshore_caps.values()), sum(solar_caps.values())
                zav, zcon, zpost = {}, {}, {}
                for z in summary_zones:
                    if z == 'OFFSHORE':           # own connection: offshore reported as its own zone
                        w_av, s_av = wind_off, 0.0 * solar
                        w_con, s_con = d['zones']['OFFSHORE']['wind'], 0.0 * solar
                    else:
                        w_av = wind_on * (float(zone_caps.get(z, 0.0)) / onshore_gw if onshore_gw > 0 else 0.0)
                        if off_tot > 0 and not offshore_own:
                            w_av = w_av + wind_off * (float(offshore_caps.get(z, 0.0)) / off_tot)
                        s_av = solar * (float(solar_caps.get(z, 0.0)) / sol_tot) if sol_tot > 0 else 0.0 * solar
                        w_con = d['zones'][z]['wind'] + d['zones'][z].get('offshore', 0.0)
                        s_con = d['zones'][z]['solar']
                    zav[z], zcon[z] = (w_av, s_av), (w_con, s_con)
                    zpost[z] = (np.maximum(w_av - w_con, 0.0), np.maximum(s_av - s_con, 0.0))
                post_w_sum = sum(zpost[z][0] for z in summary_zones)
                post_s_sum = sum(zpost[z][1] for z in summary_zones)
                for z in summary_zones:
                    w_curt = d['curt_w'] * np.divide(zpost[z][0], post_w_sum, out=np.zeros_like(post_w_sum), where=post_w_sum > 0)
                    s_curt = d['curt_s'] * np.divide(zpost[z][1], post_s_sum, out=np.zeros_like(post_s_sum), where=post_s_sum > 0)
                    for tech, i, curt in (('wind', 0, w_curt), ('solar', 1, s_curt)):
                        row[f'z_{tech}_avail_{z}'] = np.sum(zav[z][i]) * to_annual_twh
                        row[f'z_{tech}_con_{z}'] = np.sum(zcon[z][i]) * to_annual_twh
                        row[f'z_{tech}_curt_{z}'] = np.sum(curt) * to_annual_twh
                # Curtailment reason each interval: whichever system ceiling binds (min gen = MUON floor)
                curt_all = d['curt_w'] + d['curt_s']
                muon_binds = d['muon_ceiling_mw'] < d['snsp_ceiling_mw']
                to_hours = 0.25 * (365.25 / (len(avail) / 96.0))
                row['sys_curt_snsp_twh'] = curt_all[~muon_binds].sum() * to_annual_twh
                row['sys_curt_surplus_twh'] = d['surplus_mw'].sum() * to_annual_twh
                row['sys_surplus_pre_twh'] = d['surplus_pre_mw'].sum() * to_annual_twh
                for tech, key in (('w', 'wind'), ('s', 'solar')):
                    row[f'{key}_curt_snsp_twh'] = d[f'curt_{tech}'][~muon_binds].sum() * to_annual_twh
                    row[f'{key}_curt_mingen_twh'] = d[f'curt_{tech}'][muon_binds].sum() * to_annual_twh
                share_w = np.divide(d['usable_w'], d['usable_w'] + d['usable_s'],
                                    out=np.ones_like(d['usable_w']), where=(d['usable_w'] + d['usable_s']) > 0)
                row['wind_export_twh'] = (d['export_vre_mw'] * share_w).sum() * to_annual_twh
                row['solar_export_twh'] = (d['export_vre_mw'] * (1 - share_w)).sum() * to_annual_twh
                row['sys_curt_mingen_twh'] = curt_all[muon_binds].sum() * to_annual_twh
                row['sys_hours_snsp'] = np.count_nonzero((curt_all > 1e-6) & ~muon_binds) * to_hours
                row['sys_hours_mingen'] = np.count_nonzero((curt_all > 1e-6) & muon_binds) * to_hours
                row['sys_recovered_twh'] = d['recovered_constraint_mw'].sum() * to_annual_twh
                for tech, key in (('w', 'wind'), ('s', 'solar')):
                    row[f'all_{key}_con_twh'] = d[f'con_{tech}'].sum() * to_annual_twh
                    row[f'all_{key}_curt_twh'] = d[f'curt_{tech}'].sum() * to_annual_twh
                rows.append(row)
            residuals = np.concatenate([r.pop('firm_residual_series') for r in rows])
            out = pd.DataFrame(rows).mean().to_dict()
            # Peak firm residual is the worst interval over all weather years, not the average.
            out['firm_peak_mw'] = float(residuals.max()) if len(residuals) else 0.0
            # Gas: worst day over all weather years; days short is the weather-year mean.
            out['gas_worst_day_gwh'] = max(r['gas_worst_day_gwh'] for r in rows) if rows else 0.0
            out['gas_worst_power_gwh'] = max(r['gas_worst_power_gwh'] for r in rows) if rows else 0.0
            out['firm_p_mw'] = (float(np.percentile(residuals, FIRM_RESIDUAL_PERCENTILE))
                                if len(residuals) else 0.0)
            out['ie_share'] = ie_share
            out['solar_ie_share'] = s_ie
            out['onshore_gw'] = onshore_gw
            out['offshore_gw'] = offshore_gw
            out['headrooms'] = headrooms
            return out



        # HISTORICAL CURTAILMENT TEST - Gamma's real dispatch engine
        # Uses actual wind, solar, demand and recorded network constraint.
        # No residual correction. Batteries disabled for this test.

        # Save interval-level backcast comparisons for daily and monthly plots.
        historical_curtailment_intervals = []

        for test_year in (2020, 2021, 2022, 2023, 2024, 2025):
            hist = merged.loc[
                merged['year'] == test_year
            ].sort_values('parsed_date').copy()

            times = hist['parsed_date'].dt.floor('h')
            series = {}

            for tech in ('Wind', 'Solar'):
                df = pd.read_csv(
                    input_path(DD_ALL_ISLAND_FILES[tech]),
                    parse_dates=['datetime']
                ).set_index('datetime')

                df = df.loc[df['hh_count'] > 0].copy()
                df = df[~df.index.duplicated(keep='first')]
                factor = 2.0 / df['hh_count']

                # Actual output remaining after grid constraint
                post = (
                    (df['av_mwh'] - df['constraint_mwh'])
                    .clip(lower=0) * factor
                )

                series[tech] = post.reindex(times).to_numpy()
                if tech == 'Wind':
                    actual = df['curtailment_mwh'].reindex(times).to_numpy()
                    available = df['av_mwh'].reindex(times).to_numpy()

            demand = hist['sem_demand'].to_numpy(dtype=float)
            valid = (
                np.isfinite(demand)
                & np.isfinite(series['Wind'])
                & np.isfinite(series['Solar'])
                & np.isfinite(actual)
                & np.isfinite(available)
            )

            # Run Gamma's actual 15-minute dispatch calculation.
            # Grid constraint has already been removed using records.
            no_constraint = {z: 1e12 for z in HEADROOM_ZONES}
            caps = {'NI': 1.0}

            # Historical MUON requirements (150 MW per unit assumed).
            dates = hist.loc[valid, 'parsed_date'].to_numpy()

            if test_year == 2020:
                muon = np.full(valid.sum(), 900.0)
            elif test_year <= 2023:
                muon = np.full(valid.sum(), 1200.0)
            elif test_year == 2024:
                muon = np.where(
                    dates < np.datetime64('2024-04-07'),
                    1200.0,
                    1050.0
                )
            else:
                muon = np.full(valid.sum(), 1050.0)

            predicted_wind = np.zeros(valid.sum())

            for floor in np.unique(muon):
                mask = muon == floor

                segment = dispatch(
                    series['Wind'][valid][mask],
                    np.zeros(mask.sum()),
                    series['Solar'][valid][mask],
                    demand[valid][mask],
                    no_constraint,
                    caps, {}, caps,
                    HISTORICAL_SNSP_PCT / 100.0,
                    storage_power_mw=0.0,
                    storage_energy_mwh=0.0,
                    muon_floor_mw=float(floor)
                )

                predicted_wind[mask] = segment['curt_w']

            result = {'curt_w': predicted_wind}

            # Actual curtailment / availability are HOURLY MWh values repeated
            # across four quarter-hour rows; allocate each hour equally to
            # the four rows. Gamma's output is MW over each 15-minute row.
            if test_year >= 2021 and valid.any():
                historical_curtailment_intervals.append(pd.DataFrame({
                    'DateTime': hist.loc[valid, 'parsed_date'].to_numpy(),
                    'Actual_MWh': actual[valid] / 4.0,
                    'Gamma_MWh': np.asarray(result['curt_w']) * INTERVAL_HOURS,
                    'Available_MWh': available[valid] / 4.0,
                    'Demand_MW': demand[valid],
                    'Wind_Post_MW': series['Wind'][valid],
                    'Solar_Post_MW': series['Solar'][valid],
                }))

            predicted_pct = (
                100 * result['curt_w'].sum()
                / available[valid].sum()
            )
            actual_pct = (
                100 * actual[valid].sum()
                / available[valid].sum()
            )

            say(
                f"CURTAILMENT {test_year}: "
                f"Actual {actual_pct:.2f}% | "
                f"Gamma {predicted_pct:.2f}% | "
                f"Difference {predicted_pct-actual_pct:+.2f} pts"
            )


        # Daily / monthly wind-curtailment backcast comparisons (2021-2025)
        if historical_curtailment_intervals:
            comparison_intervals = pd.concat(
                historical_curtailment_intervals, ignore_index=True
            )
            comparison_intervals['DateTime'] = pd.to_datetime(
                comparison_intervals['DateTime']
            )
            os.makedirs(SCENARIO_OUTPUT_DIR, exist_ok=True)

            for freq, name, graph_title in (
                ('D', 'daily', 'Daily'),
                ('MS', 'monthly', 'Monthly'),
            ):
                comparison = (
                    comparison_intervals.set_index('DateTime')
                    .resample(freq)[['Actual_MWh', 'Gamma_MWh', 'Available_MWh']]
                    .sum()
                )
                comparison = comparison.loc[
                    comparison['Available_MWh'] > 0
                ].copy()
                comparison['Actual_Pct'] = (
                    100.0 * comparison['Actual_MWh']
                    / comparison['Available_MWh']
                )
                comparison['Gamma_Pct'] = (
                    100.0 * comparison['Gamma_MWh']
                    / comparison['Available_MWh']
                )
                comparison['Error_pp'] = (
                    comparison['Gamma_Pct'] - comparison['Actual_Pct']
                )
                csv_path = os.path.join(
                    SCENARIO_OUTPUT_DIR, f'backcast_wind_curtailment_{name}.csv'
                )
                png_path = os.path.join(
                    SCENARIO_OUTPUT_DIR, f'backcast_wind_curtailment_{name}.png'
                )
                comparison.to_csv(csv_path, float_format='%.5f')

                fig, ax = plt.subplots(figsize=(15, 5))
                ax.plot(comparison.index, comparison['Actual_Pct'],
                        label='Recorded', linewidth=1.4)
                ax.plot(comparison.index, comparison['Gamma_Pct'],
                        label='Gamma backcast', linewidth=1.2, alpha=0.85)
                ax.set(title=f'{graph_title} wind curtailment: recorded vs Gamma (2021-2025)',
                       xlabel='Date', ylabel='Curtailment (% of available wind energy)')
                ax.set_ylim(bottom=0)
                ax.grid(alpha=0.25)
                ax.legend()
                fig.tight_layout()
                try:
                    fig.savefig(png_path, dpi=200)
                    say(f'  Saved {name} backcast graph: {png_path}')
                except OSError as exc:
                    say(f'  WARNING: Could not save {name} backcast graph: {exc}')
                finally:
                    plt.close(fig)
                say(f'  Saved {name} backcast data: {csv_path}')
        else:
            say('  No matched historical curtailment intervals for comparison plots.')

        # 2024 HISTORICAL INTERCONNECTOR SENSITIVITY — SAME dispatch() ENGINE
        # Recorded Moyle and EWIC MW are treated as fixed external flows.
        # Historical 8 -> 7 MUON rule is applied in both test cases.
        # This diagnostic does not change any forward scenario assumptions.
        flow_xlsx = input_path('System-Data-Qtr-Hourly-2024.xlsx')
        if historical_curtailment_intervals and os.path.isfile(flow_xlsx):
            import openpyxl
            wb = openpyxl.load_workbook(flow_xlsx, read_only=True, data_only=True)
            ws = wb.active
            # Read headers rather than relying on fixed numeric column positions.
            header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            lookup = {str(v).strip(): j for j, v in enumerate(header) if v is not None}
            required = ('DateTime', 'Moyle I/C', 'EWIC I/C')
            if not all(k in lookup for k in required):
                wb.close()
                raise ValueError(f'2024 interconnector workbook missing columns: {required}')
            flow_rows = [
                (r[lookup['DateTime']], r[lookup['Moyle I/C']], r[lookup['EWIC I/C']])
                for r in ws.iter_rows(min_row=2, values_only=True)
                if r[lookup['DateTime']] is not None
            ]
            wb.close()
            flows = pd.DataFrame(flow_rows, columns=['DateTime', 'Moyle_MW', 'EWIC_MW'])
            flows['DateTime'] = pd.to_datetime(flows['DateTime'], errors='coerce')
            for col in ('Moyle_MW', 'EWIC_MW'):
                flows[col] = pd.to_numeric(flows[col], errors='coerce')
            flows = (flows.dropna(subset=['DateTime', 'Moyle_MW', 'EWIC_MW'])
                     .drop_duplicates('DateTime').set_index('DateTime').sort_index())
            # Source convention: positive = imports; negative = exports.
            # Preserve opposite-direction flows on the two links separately.
            flows['Recorded_Import_MW'] = (
                flows[['Moyle_MW', 'EWIC_MW']].clip(lower=0).sum(axis=1))
            flows['Recorded_Export_MW'] = (
                -flows[['Moyle_MW', 'EWIC_MW']].clip(upper=0).sum(axis=1))

            diag = comparison_intervals.loc[
                comparison_intervals['DateTime'].dt.year == 2024
            ].set_index('DateTime').join(
                flows[['Recorded_Import_MW', 'Recorded_Export_MW']], how='inner'
            ).sort_index()
            if diag.empty:
                say('  2024 import sensitivity skipped: no overlapping timestamps.')
            else:
                dates = diag.index.to_numpy(dtype='datetime64[ns]')
                floors = np.where(dates < np.datetime64('2024-04-07'), 1200.0, 1050.0)
                wind = diag['Wind_Post_MW'].to_numpy(dtype=float)
                solar = diag['Solar_Post_MW'].to_numpy(dtype=float)
                demand = diag['Demand_MW'].to_numpy(dtype=float)
                imp = diag['Recorded_Import_MW'].to_numpy(dtype=float)
                exp = diag['Recorded_Export_MW'].to_numpy(dtype=float)
                no_constraint = {z: 1e12 for z in HEADROOM_ZONES}
                caps = {'NI': 1.0}
                for name, use_observed in (
                    ('No_Flows', False), ('Imports_Only', True), ('Recorded_Flows', True)
                ):
                    predicted_mw = np.zeros(len(diag), dtype=float)
                    # No BESS in historical diagnostic: safe to process MUON
                    # segments separately through full dispatch().
                    for floor in np.unique(floors):
                        mask = floors == floor
                        seg = dispatch(
                            wind[mask], np.zeros(mask.sum()), solar[mask],
                            demand[mask], no_constraint, caps, {}, caps,
                            HISTORICAL_SNSP_PCT / 100.0,
                            storage_power_mw=0.0, storage_energy_mwh=0.0,
                            muon_floor_mw=float(floor),
                            historical_import_mw=(imp[mask] if use_observed else None),
                            historical_export_mw=(exp[mask] if name == 'Recorded_Flows' else None),
                        )
                        predicted_mw[mask] = seg['curt_w']
                    diag[name + '_MWh'] = predicted_mw * INTERVAL_HOURS

                # Check no-flow full-dispatch calculation matches main backcast.
                delta = (diag['No_Flows_MWh'] - diag['Gamma_MWh']).abs()
                max_delta = float(delta.max())
                if max_delta > 1e-5:
                    raise AssertionError(
                        f'2024 no-flow test does not reproduce baseline: max {max_delta:.6f} MWh')

                cols = ['Actual_MWh', 'Available_MWh',
                        'No_Flows_MWh', 'Imports_Only_MWh', 'Recorded_Flows_MWh']
                for frequency, kind in (('D', 'daily'), ('MS', 'monthly')):
                    comp = diag[cols].resample(frequency).sum()
                    comp = comp.loc[comp['Available_MWh'] > 0].copy()
                    for label in ('Actual', 'No_Flows', 'Imports_Only', 'Recorded_Flows'):
                        comp[label + '_Pct'] = (
                            100 * comp[label + '_MWh'] / comp['Available_MWh'])
                    comp['No_Flows_Error_pp'] = comp['No_Flows_Pct'] - comp['Actual_Pct']
                    comp['Imports_Only_Error_pp'] = comp['Imports_Only_Pct'] - comp['Actual_Pct']
                    comp['Recorded_Flows_Error_pp'] = (
                        comp['Recorded_Flows_Pct'] - comp['Actual_Pct'])
                    csv_path = os.path.join(
                        SCENARIO_OUTPUT_DIR, f'historical_import_full_dispatch_2024_{kind}.csv')
                    comp.to_csv(csv_path, float_format='%.5f')
                    fig, ax = plt.subplots(figsize=(15, 5))
                    for label, legend in (
                        ('Actual', 'Recorded curtailment'),
                        ('No_Flows', 'Gamma, no interconnector flows'),
                        ('Imports_Only', 'Gamma, recorded imports only'),
                        ('Recorded_Flows', 'Gamma, observed imports and exports'),
                    ):
                        ax.plot(comp.index, comp[label + '_Pct'], label=legend, alpha=0.85)
                    ax.set(title=f'2024 wind curtailment: Gamma full dispatch ({kind})',
                           xlabel='Date', ylabel='Curtailment (% of available wind energy)')
                    ax.set_ylim(bottom=0)
                    ax.grid(alpha=0.25)
                    ax.legend()
                    fig.tight_layout()
                    png_path = os.path.join(
                        SCENARIO_OUTPUT_DIR, f'historical_import_full_dispatch_2024_{kind}.png')
                    try:
                        fig.savefig(png_path, dpi=200)
                    except OSError as exc:
                        say(f'  WARNING: 2024 sensitivity graph could not be saved: {exc}')
                    finally:
                        plt.close(fig)
                    say(f'  Saved full-dispatch 2024 sensitivity ({kind}): {csv_path}')

                weight = diag['Available_MWh'].sum()
                say(f'  2024 recorded curtailment: {100 * diag["Actual_MWh"].sum() / weight:.2f}%')
                for label in ('No_Flows', 'Imports_Only', 'Recorded_Flows'):
                    score = 100 * diag[label + '_MWh'].sum() / weight
                    daily = diag[['Actual_MWh', 'Available_MWh', label + '_MWh']].resample('D').sum()
                    daily = daily[daily['Available_MWh'] > 0]
                    daily_actual = 100 * daily['Actual_MWh'] / daily['Available_MWh']
                    daily_model = 100 * daily[label + '_MWh'] / daily['Available_MWh']
                    corr = daily_actual.corr(daily_model)
                    say(f'    {label}: {score:.2f}%  |  daily correlation {corr:.3f}')
        elif not os.path.isfile(flow_xlsx):
            say('  2024 full-dispatch import sensitivity skipped: 2024 EirGrid workbook not present.')

        base_run = run_weather_years(start_year, base_demand_twh,
                                     HISTORICAL_SNSP_PCT / 100.0, solar_capacity_2026_gw,
                                     *storage_for_year(start_year), weather_years=[2026])


                                     
        base_weather_oversupply_2026 = base_run['curt_pct']
        print(f">> 2026 curtailment: recorded {base_2026_curt:.2f}%, modelled SNSP and minimum generation "
              f"{base_weather_oversupply_2026:.2f}% (at {HISTORICAL_SNSP_PCT:.0f}%); no residual is added")
        base_model_cons_2026 = base_run['cons_pct']
        print(f">> Modelled 2026 constraint: {base_model_cons_2026:.2f}% of all-island available wind "
              f"(IE {base_run['IE_own_pct']:.2f}% of IE wind, NI {base_run['NI_own_pct']:.2f}% of NI wind); "
              f"spreadsheet 2026 figure: {base_2026_cons:.2f}%")
        capacity_rows, balance_err_by_year = [], {}
        evaluation_rows = []
        summary_rows_by_kind = {'wind': [], 'solar': [], 'total': [], 'system': []}
        summary_gap = 0.0          # largest gap between zone sums and the all-island figures (% pts)
        for yr in simulation_years:
            say(str(yr) if yr in (2026, 2030, 2040, 2050) else '.', end='')     # progress on the console
            years_elapsed = yr - start_year
            onshore_gw, offshore_gw, zone_caps = zone_caps_for_year(yr)
            cap = onshore_gw + offshore_gw
            headrooms_yr = headroom_for_year(headroom_table, yr, headroom_scale)

            yr_demand = demand_for_year(yr)
            # 2026 is the anchor year, so it uses the SNSP limit in force then; the scenario's
            # SNSP limit (or its path) applies from 2027.
            snsp_yr = snsp_fraction_for_year(yr)
            solar_cap = solar_capacity_for_year(yr)
            storage_power_mw, storage_energy_mwh = storage_for_year(yr)
            selected_weather_years = [2026] if yr == 2026 else scenario_weather_years
            run = run_weather_years(yr, yr_demand, snsp_yr, solar_cap,
                                    storage_power_mw, storage_energy_mwh,
                                    weather_years=selected_weather_years)
            # Firm capacity is an adequacy measure, so its peak is taken over every weather year,
            # including 2026 (whose energy results use 2026 weather only). Without this the 2026
            # requirement missed the January 2025 cold, calm peak (7.49 GW demand, ~0.2-0.8 GW wind).
            if yr == start_year and len(complete_weather_years) > 1:
                peak_run = run_weather_years(yr, yr_demand, snsp_yr, solar_cap,
                                             storage_power_mw, storage_energy_mwh,
                                             weather_years=complete_weather_years)
                run['firm_peak_mw'], run['firm_p_mw'] = peak_run['firm_peak_mw'], peak_run['firm_p_mw']
                # The gas check is also an adequacy test, so 2026 uses every weather year too.
                for k in ('gas_worst_day_gwh', 'gas_worst_power_gwh', 'gas_days_short', 'gas_shortfall_gwh'):
                    run[k] = peak_run[k]

            avg_raw_curt_pct = run['curt_pct']
            sim_constraint_pct = run['cons_pct']
            total_loss_pct = min(100.0, avg_raw_curt_pct + sim_constraint_pct)

            implied_gen_twh = run['dispatch_twh']
            sim_cf = implied_gen_twh * 1000.0 / (cap * 8760.0) if cap > 0 else 0.0

            wind_pct_of_demand = (implied_gen_twh / yr_demand) * 100.0

            solar_curt = run['solar_curt_pct'] if solar_cap > 0 else 0.0
            solar_con = run['solar_cons_pct'] if solar_cap > 0 else 0.0
            solar_gen_twh = run['solar_dispatch_twh']
            solar_cf = solar_gen_twh * 1000.0 / (solar_cap * 8760.0) if solar_cap > 0 else 0.0
            solar_pct_of_demand = 100.0 * solar_gen_twh / yr_demand

            # Three-component demand and whole-energy transition indicators.
            # Existing 2025 electrified loads are advanced once to the 2026 anchor;
            # scenario growth applies from 2027. Heat/transport progress is capped
            # at the corresponding all-island sector demand.
            base_heat_electricity_2026 = BASE_HEAT_ELECTRICITY_TWH_2025 + DEFAULT_HEAT_DEMAND_GROWTH_TWH_PER_YEAR
            base_transport_electricity_2026 = BASE_TRANSPORT_ELECTRICITY_TWH_2025 + DEFAULT_TRANSPORT_DEMAND_GROWTH_TWH_PER_YEAR
            heat_electricity_twh = min(ALL_ISLAND_HEAT_DEMAND_TWH / HEAT_COP,
                base_heat_electricity_2026 + years_elapsed * heat_demand_growth_rate)
            transport_electricity_twh = min(ALL_ISLAND_TRANSPORT_DEMAND_TWH / TRANSPORT_DISPLACEMENT_FACTOR,
                base_transport_electricity_2026 + years_elapsed * transport_demand_growth_rate)
            heat_electrified_twh = min(ALL_ISLAND_HEAT_DEMAND_TWH, heat_electricity_twh * HEAT_COP)
            transport_electrified_twh = min(ALL_ISLAND_TRANSPORT_DEMAND_TWH, transport_electricity_twh * TRANSPORT_DISPLACEMENT_FACTOR)
            remaining_heat_twh = max(0.0, ALL_ISLAND_HEAT_DEMAND_TWH - heat_electrified_twh)
            remaining_transport_twh = max(0.0, ALL_ISLAND_TRANSPORT_DEMAND_TWH - transport_electrified_twh)
            # The dispatch residual already includes weather lulls, SNSP/MUON limits
            # and battery discharge. Cap at annual electricity demand.
            firm_generation_twh = min(yr_demand, max(0.0, run['firm_generation_twh']))
            # Peaking share of firm output from the 15-minute screening split (weather-year mean);
            firm_peaking_share = (run['firm_peaking_twh'] / run['firm_generation_twh']
                                  if run['firm_generation_twh'] > 0 else 0.0)
            firm_fleet_eff = float(fleet_efficiency(firm_peaking_share))
            # Firm capacity (issue #8): the largest 15-minute firm residual over all weather years
            # (demand less domestic wind, solar and battery discharge, before imports), plus the
            # largest single infeed as reserve. Interconnectors get no credit in the headline
            # figure (GB is often short at the same time); the figure net of a de-rated
            # interconnector credit is reported separately. The previous formula,
            # 0.9 x average demand / 0.68, is kept for comparison.
            firm_capacity_legacy_gw = (yr_demand / (8760.0 * 0.68 / 1000.0)) * 0.90
            firm_capacity_peak_residual_gw = run['firm_peak_mw'] / 1000.0
            firm_capacity_p_residual_gw = run['firm_p_mw'] / 1000.0
            ic_cap_yr_mw = ic_capacity_for_year(yr)
            reserve_mw = largest_infeed_mw(yr) + OPERATING_RESERVE_MW
            ic_credit_mw = ic_capacity_credit * ic_cap_yr_mw
            firm_capacity_required_gw = (run['firm_peak_mw'] + reserve_mw) / 1000.0
            firm_capacity_net_ic_gw = max(0.0, firm_capacity_required_gw - ic_credit_mw / 1000.0)
            row_out = {
                'Year': yr,
                'Gas_Worst_Day_GWh': round(run['gas_worst_day_gwh'], 1),
                'Gas_Worst_Day_Power_GWh': round(run['gas_worst_power_gwh'], 1),
                'Gas_Supply_GWh_per_Day': round(gas_supply_gwh_per_day(yr), 1),
                'Gas_Days_Short_per_Year': round(run['gas_days_short'], 2),
                'Gas_Shortfall_GWh_per_Year': round(run['gas_shortfall_gwh'], 1),
                'Gas_Power_TWh_GCV': round(run['gas_power_twh'], 2),
                'Gas_NonPower_TWh_GCV': round(run['gas_nonpower_twh'], 2),
                'Wind_Cap_GW': round(cap, 2),
                'Wind_Onshore_GW': round(onshore_gw, 2),
                'Wind_Offshore_GW': round(offshore_gw, 2),
                'Dem_TWh': round(yr_demand, 2),
                'SNSP_Limit_%': round(100 * snsp_yr, 1),
                'MUON_Floor_MW': round(muon_floor_for_year(yr)),
                'Background_Demand_Growth_TWh_per_Year': round(background_demand_growth_rate, 3),
                'Heat_Demand_Growth_TWh_per_Year': round(heat_demand_growth_rate, 3),
                'Transport_Demand_Growth_TWh_per_Year': round(transport_demand_growth_rate, 3),
                'Total_Demand_Growth_TWh_per_Year': round(annual_demand_growth_rate, 3),
                'Heat_Electricity_Demand_TWh': round(heat_electricity_twh, 3),
                'Transport_Electricity_Demand_TWh': round(transport_electricity_twh, 3),
                'Heat_Energy_Electrified_TWh': round(heat_electrified_twh, 3),
                'Transport_Energy_Electrified_TWh': round(transport_electrified_twh, 3),
                'Remaining_Heat_Energy_TWh': round(remaining_heat_twh, 3),
                'Remaining_Transport_Energy_TWh': round(remaining_transport_twh, 3),
                'Firm_Generation_TWh': round(firm_generation_twh, 3),
                'Fossil_Firm_Generation_TWh': round(firm_generation_twh, 3),
                'Firm_Peaking_Share_%': round(100 * firm_peaking_share, 1),
                'Firm_Fleet_Efficiency_%': round(100 * firm_fleet_eff, 1),
                'Firm_Capacity_Required_GW': round(firm_capacity_required_gw, 3),
                'Firm_Capacity_Peak_Residual_GW': round(firm_capacity_peak_residual_gw, 3),
                f'Firm_Residual_P{FIRM_RESIDUAL_PERCENTILE:g}_GW': round(firm_capacity_p_residual_gw, 3),
                'Firm_Reserve_GW': round(reserve_mw / 1000.0, 3),
                'Interconnector_Capacity_GW': round(ic_cap_yr_mw / 1000.0, 3),
                'Interconnector_Capacity_Credit_GW': round(ic_credit_mw / 1000.0, 3),
                'Firm_Capacity_Net_of_IC_Credit_GW': round(firm_capacity_net_ic_gw, 3),
                'Firm_Capacity_Legacy_Formula_GW': round(firm_capacity_legacy_gw, 3),
                'Import_TWh': round(run['import_twh'], 3),
                'Export_TWh': round(run['export_twh'], 3),
                'Export_Wind_Solar_TWh': round(run['export_vre_twh'], 3),
                'Export_Synchronous_TWh': round(run['export_sync_twh'], 3),
                'Net_Import_TWh': round(run['import_twh'] - run['export_twh'], 3),
                'RawCurt_%': round(avg_raw_curt_pct, 2),
                'GridCon_%': round(sim_constraint_pct, 2),
                'TotLoss_%': round(total_loss_pct, 2),
                'Wind_Fleet_CF_%_SEM': round(sim_cf * 100, 2),
                'Wind_%_SEM': round(wind_pct_of_demand, 2),
                'IE_Share_%': round(100 * run['ie_share'], 1),
                'Headroom_SE_MW': round(headrooms_yr['SE']),
                'Headroom_NI_MW': round(headrooms_yr['NI']),
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
                'Recoverable_Grid_Constraint_TWh': round(run['recoverable_grid_constraint_twh'], 3),
                'Grid_Constrained_Oversupply_TWh': round(run['grid_constrained_oversupply_twh'], 3),
                'Operational_Curtailment_Oversupply_TWh': round(run['operational_curtailment_oversupply_twh'], 3),
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
                # Jurisdiction shares from zone energies (22 November 2026): IE is the six onshore
                # zones plus offshore, each with its own availability. Before, IE availability was
                # all-island availability split by installed capacity, which understated offshore.
                'Con_WS_IE_%': round(jurisdiction_pct(run, 'con', 'IE'), 2),
                'Con_WS_NI_%': round(jurisdiction_pct(run, 'con', 'NI'), 2),
                'IE_Avail_WS_TWh': round(jurisdiction_twh(run, 'avail', 'IE'), 3),
                'IE_Curt_WS_%': round(jurisdiction_pct(run, 'curt', 'IE'), 2),
                'IE_Surplus_WS_%': round(jurisdiction_surplus_pct(run, 'IE'), 2),
                'IE_Total_DD_WS_%': round(jurisdiction_pct(run, 'con', 'IE')
                                          + jurisdiction_pct(run, 'curt', 'IE'), 2),
                # Anchor year only: modelled all-island wind + solar dispatch down over the months the
                # part-year record covers (January to Recorded_Window_Last_Month), % of available.
                'Recorded_Window_Last_Month': (anchor_record_last_month
                                               if np.isfinite(run.get('window_avail_mwh', np.nan)) else np.nan),
                'WS_DD_Recorded_Window_%': (round(100.0 * run['window_dd_mwh'] / run['window_avail_mwh'], 2)
                                            if run.get('window_avail_mwh', 0) and np.isfinite(run['window_avail_mwh'])
                                            else np.nan),
            }
            for z in HEADROOM_ZONES:
                row_out[f'Con_{z}_%'] = round(run.get(f'Con_{z}_%', 0.0), 2)
                row_out[f'Headroom_{z}_MW'] = round(headrooms_yr[z])
            row_out['Con_OFFSHORE_%'] = round(run.get('Con_OFFSHORE_%', 0.0), 2)
            sim_results.append(row_out)

            # Curtailment and capacity-factor tracking (EVALUATION_CSV). Available CF is the weather
            # resource before any dispatch-down; delivered CF is after constraint and curtailment.
            # Curtailment is split by the ceiling that bound (SNSP or min gen).
            def tech_eval(prefix, cap_gw, avail, gen, con, c_snsp, c_mingen, exported):
                hours = 8760.0
                pct = lambda x: 100.0 * x / avail if avail > 0 else np.nan
                curt = c_snsp + c_mingen
                return {f'{prefix}_Capacity_GW': round(cap_gw, 3),
                        f'{prefix}_Available_TWh': round(avail, 3),
                        f'{prefix}_Generation_TWh': round(gen, 3),
                        f'{prefix}_Exported_TWh': round(exported, 3),
                        f'{prefix}_Available_CF_%': round(100 * avail * 1000 / (cap_gw * hours), 2) if cap_gw > 0 else np.nan,
                        f'{prefix}_Delivered_CF_%': round(100 * gen * 1000 / (cap_gw * hours), 2) if cap_gw > 0 else np.nan,
                        f'{prefix}_Constraint_%': round(pct(con), 2),
                        f'{prefix}_Curtail_SNSP_%': round(pct(c_snsp), 2),
                        f'{prefix}_Curtail_MinGen_%': round(pct(c_mingen), 2),
                        f'{prefix}_Curtailment_%': round(pct(curt), 2),
                        f'{prefix}_Dispatch_Down_%': round(pct(con + curt), 2),
                        f'{prefix}_Constrained_TWh': round(con, 3),
                        f'{prefix}_Curtailed_TWh': round(curt, 3)}
            ev = {'Scenario': scenario_name, 'Data_Type': 'Forecast', 'Year': yr,
                  'Demand_TWh': round(yr_demand, 2), 'SNSP_Limit_%': round(100 * snsp_yr, 1),
                  'MUON_Floor_MW': round(muon_floor_for_year(yr))}
            ev.update(tech_eval('Wind', cap, run['avail_twh'], implied_gen_twh, run['all_wind_con_twh'],
                                run['wind_curt_snsp_twh'], run['wind_curt_mingen_twh'], run['wind_export_twh']))
            ev.update(tech_eval('Solar', solar_cap, run['solar_avail_twh'], solar_gen_twh, run['all_solar_con_twh'],
                                run['solar_curt_snsp_twh'], run['solar_curt_mingen_twh'], run['solar_export_twh']))
            ws_av = run['avail_twh'] + run['solar_avail_twh']
            ev['WindSolar_Curtailment_%'] = round(100 * (ev['Wind_Curtailed_TWh'] + ev['Solar_Curtailed_TWh']) / ws_av, 2) if ws_av > 0 else np.nan
            ev['WindSolar_Dispatch_Down_%'] = round(100 * (ev['Wind_Curtailed_TWh'] + ev['Solar_Curtailed_TWh']
                                                          + ev['Wind_Constrained_TWh'] + ev['Solar_Constrained_TWh']) / ws_av, 2) if ws_av > 0 else np.nan
            ev['Storage_Charged_From_Surplus_TWh'] = round(run['storage_charge_twh'], 3)
            evaluation_rows.append(ev)
            balance_err_by_year[yr] = run.get('balance_err_pct', 0.0)

            # Installed capacity by zone this year (MW), for capacity_by_zone_year.csv
            off_caps, sol_caps, bat_caps = offshore_caps_for_year(yr), solar_caps_for_year(yr), battery_caps_for_year(yr)
            for z in HEADROOM_ZONES + ['UNZONED']:
                capacity_rows.append({
                    'Scenario': scenario_name, 'Year': yr, 'Zone': z,
                    'Wind_Onshore_MW': 1000 * zone_caps.get(z, 0.0),
                    'Wind_Offshore_MW': 1000 * off_caps.get(z, 0.0),
                    'Solar_MW': 1000 * sol_caps.get(z, 0.0),
                    'Battery_MW': bat_caps.get(z, (0.0, 0.0))[0],
                    'Battery_MWh': bat_caps.get(z, (0.0, 0.0))[1],
                    'Headroom_MW': headrooms_yr.get(z, np.nan),
                    'Con_Onshore_Wind_%': row_out.get(f'Con_{z}_%', np.nan),
                })

            # Readable summaries: all-island figures first, then each metric for every zone side by side
            Z = summary_zones
            off_total_gw = sum(off_caps.values())

            def wind_zone_gw(z):
                if z == 'OFFSHORE':
                    return off_total_gw
                return zone_caps.get(z, 0.0) + (0.0 if offshore_own else off_caps.get(z, 0.0))

            def zone_limit_mw(z):
                return OFFSHORE_CONNECTION_RATIO * off_total_gw * 1000.0 if z == 'OFFSHORE' else headrooms_yr[z]
            pct = lambda num, den: round(100.0 * num / den, 2) if den > 0 else np.nan
            zw = {z: (run[f'z_wind_avail_{z}'], run[f'z_wind_con_{z}'], run[f'z_wind_curt_{z}']) for z in Z}
            zs = {z: (run[f'z_solar_avail_{z}'], run[f'z_solar_con_{z}'], run[f'z_solar_curt_{z}']) for z in Z}
            # All percentages in the summaries are energy over energy (TWh constrained / TWh available,
            # summed over the weather years), so zones add up exactly to the all-island figure.
            w_con, w_curt = sum(zw[z][1] for z in Z), sum(zw[z][2] for z in Z)
            s_con, s_curt = sum(zs[z][1] for z in Z), sum(zs[z][2] for z in Z)
            w_row = {'Year': yr, 'Capacity_GW': row_out['Wind_Cap_GW'], 'Offshore_Capacity_GW': row_out['Wind_Offshore_GW'],
                     'Available_TWh': round(run['avail_twh'], 2), 'Generation_TWh': row_out['Wind_Gen_TWh'],
                     'Constraint_%': pct(w_con, run['avail_twh']), 'Curtailment_%': pct(w_curt, run['avail_twh']),
                     'Total_Loss_%': pct(w_con + w_curt, run['avail_twh']),
                     'Share_of_Demand_%': row_out['Wind_%_SEM'],
                     'Offshore_Constraint_%': row_out['Con_OFFSHORE_%']}
            w_row.update({f'{z}_capacity_MW': round(1000 * wind_zone_gw(z)) for z in Z})
            w_row.update({f'{z}_constraint_%': pct(zw[z][1], zw[z][0]) for z in Z})
            w_row.update({f'{z}_curtailment_%': pct(zw[z][2], zw[z][0]) for z in Z})
            s_av = run['solar_avail_twh']
            s_row = {'Year': yr, 'Capacity_GW': row_out['Solar_Cap_GW'], 'Available_TWh': row_out['Solar_Avail_TWh'],
                     'Generation_TWh': row_out['Solar_Gen_TWh'], 'Constraint_%': pct(s_con, s_av),
                     'Curtailment_%': pct(s_curt, s_av) if s_av > 0 else np.nan,
                     'Total_Loss_%': pct(s_con + s_curt, s_av) if s_av > 0 else np.nan,
                     'Share_of_Demand_%': row_out['Solar_%']}
            s_row.update({f'{z}_capacity_MW': round(1000 * sol_caps.get(z, 0.0)) for z in Z})
            s_row.update({f'{z}_constraint_%': pct(zs[z][1], zs[z][0]) for z in Z})
            s_row.update({f'{z}_curtailment_%': pct(zs[z][2], zs[z][0]) for z in Z})
            av_ws = run['avail_twh'] + run['solar_avail_twh']
            con_ws, curt_ws = w_con + s_con, w_curt + s_curt
            t_row = {'Year': yr, 'Demand_TWh': row_out['Dem_TWh'],
                     'Capacity_GW': round(row_out['Wind_Cap_GW'] + row_out['Solar_Cap_GW'], 2),
                     'Available_TWh': round(av_ws, 2),
                     'Generation_TWh': round(row_out['Wind_Gen_TWh'] + row_out['Solar_Gen_TWh'], 2),
                     'Constraint_%': pct(con_ws, av_ws), 'Curtailment_%': pct(curt_ws, av_ws),
                     'Surplus_%': pct(run['sys_curt_surplus_twh'], av_ws),
                     'Total_Loss_%': pct(con_ws + curt_ws, av_ws),
                     'Share_of_Demand_%': row_out['Wind+Solar_%'],
                     'Storage_Power_MW': row_out['Storage_Power_MW'], 'Storage_Energy_MWh': row_out['Storage_Energy_MWh'],
                     'Storage_Discharge_TWh': row_out['Storage_Discharge_TWh'],
                     'Firm_Capacity_Required_GW': row_out['Firm_Capacity_Required_GW'],
                     'Overall_Fossil_Fuel_Pct': row_out.get('Overall_Fossil_Fuel_Pct', np.nan),
                     'Overall_Renewables_Pct': row_out.get('Overall_Renewables_Pct', np.nan),
                     'Overall_Imported_Electricity_Pct': row_out.get('Overall_Imported_Electricity_Pct', np.nan)}
            t_row.update({f'{z}_limit_MW': round(zone_limit_mw(z)) for z in Z})
            t_row.update({f'{z}_capacity_MW': round(1000 * (wind_zone_gw(z) + sol_caps.get(z, 0.0))) for z in Z})
            t_row.update({f'{z}_constraint_%': pct(zw[z][1] + zs[z][1], zw[z][0] + zs[z][0]) for z in Z})
            t_row.update({f'{z}_curtailment_%': pct(zw[z][2] + zs[z][2], zw[z][0] + zs[z][0]) for z in Z})
            # System summary: wind + solar dispatch-down by reason, % of available wind + solar
            sys_row = {'Year': yr, 'Demand_TWh': row_out['Dem_TWh'], 'Available_TWh': round(av_ws, 2),
                       'SNSP_Limit_%': round(100 * snsp_yr, 1), 'MUON_Floor_MW': round(muon_floor_for_year(yr)),
                       'Constraint_%': pct(con_ws, av_ws),
                       'Recoverable_Grid_Constraint_%': pct(run['recoverable_grid_constraint_twh'], av_ws),
                       'Grid_Constrained_Oversupply_%': pct(run['grid_constrained_oversupply_twh'], av_ws),
                       'Operational_Curtailment_Oversupply_%': pct(run['operational_curtailment_oversupply_twh'], av_ws),
                       'SNSP_Curtailment_%': pct(run['sys_curt_snsp_twh'], av_ws),
                       'MinGen_Curtailment_%': pct(run['sys_curt_mingen_twh'], av_ws),
                       # EirGrid's three-way split: surplus is inside SNSP/MinGen above; operational
                       # curtailment is everything in curtailment that is not surplus.
                       'Surplus_%': pct(run['sys_curt_surplus_twh'], av_ws),
                       'Operational_Curtailment_%': pct(run['sys_curt_snsp_twh'] + run['sys_curt_mingen_twh']
                                                        - run['sys_curt_surplus_twh'], av_ws),
                       'Surplus_Before_Constraint_%': pct(run['sys_surplus_pre_twh'], av_ws),
                       'Total_Dispatch_Down_%': pct(con_ws + curt_ws, av_ws),
                       'SNSP_Binding_Hours': round(run['sys_hours_snsp']),
                       'MinGen_Binding_Hours': round(run['sys_hours_mingen']),
                       'Storage_Recovered_Constraint_TWh': round(run['sys_recovered_twh'], 3),
                       'Storage_Discharge_TWh': row_out['Storage_Discharge_TWh'],
                     'Firm_Capacity_Required_GW': row_out['Firm_Capacity_Required_GW'],
                     'Overall_Fossil_Fuel_Pct': row_out.get('Overall_Fossil_Fuel_Pct', np.nan),
                     'Overall_Renewables_Pct': row_out.get('Overall_Renewables_Pct', np.nan),
                     'Overall_Imported_Electricity_Pct': row_out.get('Overall_Imported_Electricity_Pct', np.nan)}
            for key, r in (('wind', w_row), ('solar', s_row), ('total', t_row), ('system', sys_row)):
                summary_rows_by_kind[key].append(r)
            summary_gap = max(summary_gap, *(100 * abs(a - b) / av_ws for a, b in (
                (w_con, run['all_wind_con_twh']), (s_con, run['all_solar_con_twh']),
                (w_curt, run['all_wind_curt_twh']), (s_curt, run['all_solar_curt_twh'])))) if av_ws > 0 else summary_gap

        sim_df = pd.DataFrame(sim_results)


        # Monthly demand extremes across scenario weather years
        monthly_rows = []

        for yr in simulation_years:
            weather_years = [2026] if yr == start_year else scenario_weather_years

            for wy in weather_years:
                df_wy = merged[merged['year'] == wy]
                demand = scenario_demand_mw(
                    df_wy, demand_for_year(yr), yr
                ) / 1000.0  # MW to GW

                monthly = pd.DataFrame({
                    'Month': df_wy['parsed_date'].dt.month.to_numpy(),
                    'Demand_GW': demand
                }).groupby('Month')['Demand_GW'].agg(['min', 'max', 'mean'])

                for month, r in monthly.iterrows():
                    monthly_rows.append({
                        'Year': yr,
                        'Month': month,
                        'Min_GW': r['min'],
                        'Max_GW': r['max'],
                        'Mean_GW': r['mean']
                    })

        monthly_df = pd.DataFrame(monthly_rows)
        monthly_df = monthly_df.groupby(
            ['Year', 'Month'], as_index=False
        ).agg(
            Min_Demand_GW=('Min_GW', 'min'),
            Max_Demand_GW=('Max_GW', 'max'),
            Mean_Demand_GW=('Mean_GW', 'mean')
        )

        monthly_df['IC_Capacity_GW'] = 2.9
        monthly_df['Peak_Demand_Above_IC_GW'] = (
            monthly_df['Max_Demand_GW'] - 2.9
        ).clip(lower=0)

        monthly_df.round(3).to_csv(
            os.path.join(out_dir, 'monthly_demand_extremes.csv'),
            index=False
        )
        say("      Monthly demand extremes saved to monthly_demand_extremes.csv")


        # Gas supply check outputs (daily energy, GCV). The envelope is the worst of all weather
        # years for each calendar day, so it is a worst case, not a single year. 29 February is
        # dropped: only leap weather years have it, which made the envelope dip every fourth year.
        if gas_records:
            gas_df = pd.concat(gas_records.values(), ignore_index=True)
            gas_df.to_csv(os.path.join(out_dir, "gas_daily_by_weather_year.csv"), index=False,
                          float_format='%.2f')
            gd_dates = pd.to_datetime(gas_df['date'])
            gas_df['month'], gas_df['day'] = gd_dates.dt.month, gd_dates.dt.day
            gas_df = gas_df[~((gas_df['month'] == 2) & (gas_df['day'] == 29))]
            env = gas_df.groupby(['year', 'month', 'day'], as_index=False).agg(
                total_gwh=('total_gwh', 'max'), power_gwh=('power_gwh', 'max'),
                supply_gwh=('supply_gwh', 'first'))
            env['date'] = pd.to_datetime(dict(year=env['year'], month=env['month'], day=env['day']))
            env = env.sort_values('date')
            env['shortfall_gwh'] = (env['total_gwh'] - env['supply_gwh']).clip(lower=0)
            env.to_csv(os.path.join(out_dir, "gas_daily_demand_envelope.csv"), index=False,
                       float_format='%.2f')
            # 2026 check against the observed full-system day (8 January 2025 weather, 2026 system).
            vy, vm, vd = GAS_VALIDATION_DAY
            v = gas_df[(gas_df['year'] == start_year) & (gas_df['weather_year'] == vy)
                       & (gas_df['month'] == vm) & (gas_df['day'] == vd)]
            if len(v):
                v = v.iloc[0]
                say(f">> Gas check, {start_year} system on {vd:02d}/{vm:02d}/{vy} weather: total "
                    f"{v['total_gwh']:.1f} GWh/d (observed {GAS_VALIDATION_TOTAL_GWH:.1f}), power "
                    f"{v['power_gwh']:.1f} GWh/d (observed {GAS_VALIDATION_POWER_GWH:.1f}), "
                    f"supply {v['supply_gwh']:.1f} GWh/d")
                pd.DataFrame([{'scenario_year': start_year, 'weather_day': f"{vy}-{vm:02d}-{vd:02d}",
                               'model_total_gwh': round(v['total_gwh'], 1),
                               'observed_total_gwh': GAS_VALIDATION_TOTAL_GWH,
                               'model_power_gwh': round(v['power_gwh'], 1),
                               'observed_power_gwh': GAS_VALIDATION_POWER_GWH,
                               'model_nonpower_gwh': round(v['nonpower_gwh'], 1),
                               'supply_gwh': round(v['supply_gwh'], 1)}]).to_csv(
                    os.path.join(out_dir, "gas_validation_2026.csv"), index=False)
            if make_charts:
                fig, axes = plt.subplots(1, 2, figsize=(16, 5.5), gridspec_kw={'width_ratios': [1, 2]})
                ann = sim_df[['Year', 'Gas_Worst_Day_GWh', 'Gas_Worst_Day_Power_GWh',
                              'Gas_Supply_GWh_per_Day']]
                ax = axes[0]
                ax.plot(ann['Year'], ann['Gas_Worst_Day_GWh'], color='steelblue', label='Worst day, total')
                ax.plot(ann['Year'], ann['Gas_Worst_Day_Power_GWh'], color='steelblue', ls=':',
                        label='Worst day, power only')
                ax.plot(ann['Year'], ann['Gas_Supply_GWh_per_Day'], color='firebrick', ls='--',
                        label='Moffat + Corrib')
                ax.set_ylabel('Gas (GWh/d, GCV)')
                ax.set_title('Worst gas day of all weather years')
                ax.set_ylim(bottom=0)
                ax.grid(alpha=0.3)
                ax.legend(fontsize=8)
                ax = axes[1]
                ax.plot(env['date'], env['total_gwh'], color='steelblue', lw=0.5,
                        label='Daily gas demand (worst weather year per day)')
                ax.plot(env['date'], env['supply_gwh'], color='firebrick', ls='--',
                        label='Moffat + Corrib daily capacity')
                ax.set_title('Daily gas demand envelope')
                ax.set_ylim(bottom=0)
                ax.grid(alpha=0.3)
                ax.legend(fontsize=8)
                fig.tight_layout()
                fig.savefig(os.path.join(out_dir, 'gas_daily_demand.png'), dpi=200)
                plt.close(fig)
            say(f">> Gas: worst day {sim_df['Gas_Worst_Day_GWh'].iloc[0]:.0f} GWh/d in {start_year}, "
                f"{sim_df['Gas_Worst_Day_GWh'].iloc[-1]:.0f} GWh/d in {sim_df['Year'].iloc[-1]}; "
                f"first year with a day short: "
                f"{next((int(y) for y, n in zip(sim_df['Year'], sim_df['Gas_Days_Short_per_Year']) if n > 0), 'none')}")

        # Overall Transition Progress (issue #7): EU RED gross final energy consumption basis.
        # Electricity is counted as consumed (TWh_e), heat and transport fuels as final fuel, and
        # heat-pump ambient heat as renewable (RED Annex VII). The headline split is of energy
        # consumed in Ireland, so the three shares sum to 100%:
        #   fossil    = remaining heat fuel + remaining transport fuel + firm electricity consumed
        #   renewable = ambient heat + domestic wind/solar consumed + BESS discharge
        #   imported  = the electricity imported in the dispatch: zero in the main runs, which
        #               have no interconnector flows, and the dispatched imports with
        #               INTERCONNECTOR_DISPATCH on. FIXED_IMPORT_SHARE_PCT (default 0 from
        #               12 Nov 2026; 4 before) is an optional fixed allowance for runs without
        #               interconnector dispatch: fossil and renewables are scaled to
        #               100% - that share.
        # Avoided transport fuel is not energy and is not counted (fixed earlier under #7).
        # Firm generation is treated as fossil; bioenergy, hydro, waste and biofuels are not in
        # scope, so the renewable share is a lower bound against SEAI's published RES.
        # RES_Overall_RED_% and RES_E_RED_% follow RED Article 7: all domestic renewable
        # generation, including exported output, over gross final consumption.
        sim_df['Remaining_Heat_Fossil_TWh'] = sim_df['Remaining_Heat_Energy_TWh']
        sim_df['Remaining_Transport_Fossil_TWh'] = sim_df['Remaining_Transport_Energy_TWh']
        sim_df['Fossil_Electricity_Consumed_TWh'] = (
            sim_df['Fossil_Firm_Generation_TWh'] - sim_df['Export_Synchronous_TWh']).clip(lower=0.0)
        sim_df['Renewable_Electricity_Consumed_TWh'] = (
            sim_df['Wind_Gen_TWh'] + sim_df['Solar_Gen_TWh'] - sim_df['Export_Wind_Solar_TWh']
            + sim_df['Storage_Discharge_TWh']).clip(lower=0.0)
        sim_df['Total_Fossil_Energy_TWh'] = (
            sim_df['Remaining_Heat_Fossil_TWh']
            + sim_df['Remaining_Transport_Fossil_TWh']
            + sim_df['Fossil_Electricity_Consumed_TWh']
        )
        # Heat: a heat pump delivers COP x its electricity. The electricity part is already in
        # electricity demand, so only the ambient heat, (COP - 1) x electricity, is added.
        sim_df['Heat_Ambient_Renewable_TWh'] = (
            sim_df['Heat_Energy_Electrified_TWh'] - sim_df['Heat_Electricity_Demand_TWh']
        ).clip(lower=0.0)
        sim_df['Total_Renewable_Energy_TWh'] = (
            sim_df['Heat_Ambient_Renewable_TWh']
            + sim_df['Renewable_Electricity_Consumed_TWh']
        )
        sim_df['Gross_Final_Energy_TWh'] = (
            sim_df['Total_Fossil_Energy_TWh']
            + sim_df['Total_Renewable_Energy_TWh']
            + sim_df['Import_TWh']
        )
        gfec = sim_df['Gross_Final_Energy_TWh']

        # Electricity as a percentage of total final energy
        sim_df['Electricity_Share_Final_Energy_Pct'] = (
            100 * sim_df['Dem_TWh'] / sim_df['Gross_Final_Energy_TWh']
        )

        # Save annual comparison
        sim_df[[
            'Year',
            'Dem_TWh',
            'Gross_Final_Energy_TWh',
            'Electricity_Share_Final_Energy_Pct'
        ]].round(2).to_csv(
            os.path.join(out_dir, 'electricity_share_final_energy.csv'),
            index=False
        )

        say("Electricity share of final energy saved to CSV")


        share = lambda num: np.where(gfec > 0.0, 100.0 * num / gfec, 0.0)
        domestic = sim_df['Total_Fossil_Energy_TWh'] + sim_df['Total_Renewable_Energy_TWh']
        if INTERCONNECTOR_DISPATCH:
            domestic_pct = 100.0
            dispatched_import_twh = sim_df['Import_TWh']
        else:
            domestic_pct = 100.0 - FIXED_IMPORT_SHARE_PCT
            dispatched_import_twh = 0.0
        final_total = domestic + dispatched_import_twh
        # Final energy (RED gross final consumption) shares, kept for comparison with SEAI's RES.
        sim_df['Final_Fossil_Fuel_Pct'] = np.where(
            final_total > 0.0, domestic_pct * sim_df['Total_Fossil_Energy_TWh'] / final_total, 0.0)
        sim_df['Final_Renewables_Pct'] = np.where(
            final_total > 0.0, domestic_pct * sim_df['Total_Renewable_Energy_TWh'] / final_total, 0.0)
        # Headline shares (red box): primary energy. Firm electricity counts as the gas burnt to
        # make it, at that year's fleet efficiency; imported electricity counts at the electricity
        # delivered (fixed share in the main runs, dispatched imports with INTERCONNECTOR_DISPATCH).
        firm_eff = sim_df['Firm_Fleet_Efficiency_%'] / 100.0
        sim_df['Firm_Gas_Burnt_TWh'] = sim_df['Fossil_Electricity_Consumed_TWh'] / firm_eff
        sim_df['Primary_Fossil_TWh'] = (sim_df['Remaining_Heat_Fossil_TWh']
                                        + sim_df['Remaining_Transport_Fossil_TWh']
                                        + sim_df['Firm_Gas_Burnt_TWh'])
        sim_df['Primary_Renewable_TWh'] = sim_df['Total_Renewable_Energy_TWh']
        primary_domestic = (sim_df['Primary_Fossil_TWh'] + sim_df['Primary_Renewable_TWh']
                            + dispatched_import_twh)
        sim_df['Overall_Fossil_Fuel_Pct'] = np.where(
            primary_domestic > 0.0, domestic_pct * sim_df['Primary_Fossil_TWh'] / primary_domestic, 0.0)
        sim_df['Overall_Renewables_Pct'] = np.where(
            primary_domestic > 0.0, domestic_pct * sim_df['Primary_Renewable_TWh'] / primary_domestic, 0.0)
        # Electricity-equivalent basis (12 Nov 2026), against the primary energy fallacy. Fuel for
        # heat and transport not yet electrified counts as the electricity that would replace it
        # (heat / HEAT_COP, transport / TRANSPORT_DISPLACEMENT_FACTOR); firm and imported
        # electricity count as electricity delivered; ambient heat is not counted, because the
        # heat pump's electricity is already in wind, solar or firm output. The result is the
        # fossil share of the electricity a fully electrified system would need.
        sim_df['Elec_Equiv_Fossil_TWh'] = (
            sim_df['Remaining_Heat_Fossil_TWh'] / HEAT_COP
            + sim_df['Remaining_Transport_Fossil_TWh'] / TRANSPORT_DISPLACEMENT_FACTOR
            + sim_df['Fossil_Electricity_Consumed_TWh'])
        elec_equiv_total = (sim_df['Elec_Equiv_Fossil_TWh'] + sim_df['Renewable_Electricity_Consumed_TWh']
                            + dispatched_import_twh)
        sim_df['Elec_Equiv_Fossil_Share_Pct'] = np.where(
            elec_equiv_total > 0.0, 100.0 * sim_df['Elec_Equiv_Fossil_TWh'] / elec_equiv_total, 0.0)
        # Useful energy basis (20 Nov 2026; paper Section 4.6 and Table 4). A simple proxy for the
        # energy services delivered: heat counts as heat delivered (remaining fossil heat fuel at
        # its energy content, heat-pump heat at HEAT_COP x its electricity), remaining transport
        # fuel counts at 1 / TRANSPORT_DISPLACEMENT_FACTOR (the work an electric vehicle would do
        # with it), and all other electricity counts as delivered. Fossil useful energy is the
        # remaining fossil heat, the remaining transport fuel / factor and the firm electricity
        # consumed.
        sim_df['Useful_Energy_TWh'] = (
            (sim_df['Dem_TWh'] - sim_df['Heat_Electricity_Demand_TWh']
             - sim_df['Transport_Electricity_Demand_TWh']).clip(lower=0.0)
            + sim_df['Heat_Energy_Electrified_TWh']
            + sim_df['Remaining_Heat_Fossil_TWh']
            + sim_df['Transport_Electricity_Demand_TWh']
            + sim_df['Remaining_Transport_Fossil_TWh'] / TRANSPORT_DISPLACEMENT_FACTOR)
        sim_df['Useful_Fossil_TWh'] = (
            sim_df['Remaining_Heat_Fossil_TWh']
            + sim_df['Remaining_Transport_Fossil_TWh'] / TRANSPORT_DISPLACEMENT_FACTOR
            + sim_df['Fossil_Electricity_Consumed_TWh'])
        sim_df['Useful_Fossil_Share_Pct'] = np.where(
            sim_df['Useful_Energy_TWh'] > 0.0,
            100.0 * sim_df['Useful_Fossil_TWh'] / sim_df['Useful_Energy_TWh'], 0.0)

        # =====================================================================
        # DYNAMIC ENERGY ACCOUNTING CHART (REPORTING ONLY)
        # All series use each year's simulated energy mix. This does NOT change
        # the scenario demand trajectory, wind/solar dispatch or other results.
        # Generated here, inside run_scenario(), for every completed scenario.
        # =====================================================================
        energy_benchmark = pd.DataFrame({
            'Year': sim_df['Year'].to_numpy(),
            'Primary_Energy_Modelled_TWh': primary_domestic.to_numpy(),
            'Final_Energy_Modelled_TWh': sim_df['Gross_Final_Energy_TWh'].to_numpy(),
            # Useful energy: the proxy defined above (Useful_Energy_TWh).
            'Useful_Service_Energy_Modelled_TWh': sim_df['Useful_Energy_TWh'].to_numpy(),
            'Electricity_Equivalent_Modelled_TWh': elec_equiv_total.to_numpy(),
            # Wind and solar consumed on the island, including what reaches demand through
            # batteries. Batteries charge only from output that would otherwise be curtailed, and
            # that charging is not in Wind_Gen_TWh or Solar_Gen_TWh, so adding the discharge does
            # not count any energy twice (20 Nov 2026; before, discharge was left out).
            'Delivered_Wind_Solar_TWh': (
                sim_df['Wind_Gen_TWh'] + sim_df['Solar_Gen_TWh']
                - sim_df['Export_Wind_Solar_TWh'] + sim_df['Storage_Discharge_TWh']
            ).clip(lower=0.0).to_numpy(),
        }).sort_values('Year')

        energy_benchmark.to_csv(
            os.path.join(out_dir, 'energy_benchmarks_vs_renewables.csv'),
            index=False, float_format='%.4f'
        )

        if SCENARIO_CHARTS and make_charts:
            fig, ax = plt.subplots(figsize=(13.5, 7))
            energy_lines = [
                ('Primary_Energy_Modelled_TWh', 'Modelled primary energy', '#08306b'),
                ('Final_Energy_Modelled_TWh', 'Modelled final energy', '#2171b5'),
                ('Electricity_Equivalent_Modelled_TWh', 'Modelled electricity equivalent', '#9ecae1'),
                ('Delivered_Wind_Solar_TWh', 'Delivered wind + solar', '#008B45'),
            ]
            years = energy_benchmark['Year'].to_numpy()
            for column, label, color in energy_lines:
                renewable = column == 'Delivered_Wind_Solar_TWh'
                vals = energy_benchmark[column].to_numpy()
                ax.plot(
                    years, vals, label=label, color=color,
                    linewidth=3.0 if renewable else 2.2,
                    linestyle='--' if renewable else '-',
                )
                ax.annotate(
                    f'{label}  {vals[-1]:.0f}',
                    xy=(years[-1], vals[-1]), xytext=(8, 0),
                    textcoords='offset points', fontsize=9,
                    color=color, va='center',
                )
            ax.set_xlim(int(years.min()), int(years.max()) + 16)
            ax.set_ylim(bottom=0)
            ax.set_xlabel('Year')
            ax.set_ylabel('Energy (TWh/year)')
            ax.set_title(
                'Dynamic energy accounting measures vs delivered renewables\n'
                f'{scenario_name.replace("_", " ")}'
            )
            ax.grid(alpha=0.2)
            ax.legend(loc='upper left')
            fig.text(
                0.5, 0.015,
                'Energy measures calculated annually from each scenario. '
                'Electricity equivalent assumes full electrification of '
                'remaining fossil heat and land transport.',
                ha='center', fontsize=8, color='#555555'
            )
            fig.tight_layout(rect=[0, 0.04, 1, 1])
            fig.savefig(
                os.path.join(out_dir, 'energy_benchmarks_vs_renewables.png'),
                dpi=200, bbox_inches='tight'
            )
            plt.close(fig)
            say(f'      energy_benchmarks_vs_renewables.png saved: {out_dir}')
        sim_df['Overall_Imported_Electricity_Pct'] = (
            100.0 - sim_df['Overall_Fossil_Fuel_Pct'] - sim_df['Overall_Renewables_Pct'])
        # What replacing gas in firm plant with green hydrogen would take (physical, no costs).
        sim_df['Firm_On_H2_Hydrogen_TWh'] = sim_df['Firm_Generation_TWh'] / firm_eff
        sim_df['Firm_On_H2_Electrolysis_TWh'] = (sim_df['Firm_On_H2_Hydrogen_TWh']
                                                 / ELECTROLYSER_EFFICIENCY)
        red_res_twh = (sim_df['Heat_Ambient_Renewable_TWh'] + sim_df['Wind_Gen_TWh']
                       + sim_df['Solar_Gen_TWh'] + sim_df['Storage_Discharge_TWh'])
        sim_df['RES_Overall_RED_%'] = share(red_res_twh)
        sim_df['RES_E_RED_%'] = np.where(
            sim_df['Dem_TWh'] > 0.0,
            100.0 * (sim_df['Wind_Gen_TWh'] + sim_df['Solar_Gen_TWh'] + sim_df['Storage_Discharge_TWh'])
            / sim_df['Dem_TWh'], 0.0)
        share_check = (
            sim_df['Overall_Fossil_Fuel_Pct']
            + sim_df['Overall_Renewables_Pct']
            + sim_df['Overall_Imported_Electricity_Pct']
        )
        if not np.allclose(share_check, 100.0, rtol=0.0, atol=1e-8):
            raise RuntimeError('Primary energy shares do not reconcile to 100%.')
        for old, new in SHARE_COLUMN_NAMES.items():
            sim_df[new] = sim_df[old]
        # Electricity supplied = consumed renewable + firm + imports must match demand.
        elec_gap = (sim_df['Renewable_Electricity_Consumed_TWh'] + sim_df['Fossil_Electricity_Consumed_TWh']
                    + sim_df['Import_TWh'] - sim_df['Dem_TWh']).abs() / sim_df['Dem_TWh']
        record_check('results', scenario_name, 'electricity supply matches demand',
                     'PASS' if elec_gap.max() <= 0.01 else 'WARN',
                     f"largest gap {100 * elec_gap.max():.2f}% of demand")
        for c in [
            'Remaining_Heat_Fossil_TWh', 'Remaining_Transport_Fossil_TWh',
            'Fossil_Electricity_Consumed_TWh', 'Renewable_Electricity_Consumed_TWh',
            'Heat_Ambient_Renewable_TWh', 'Gross_Final_Energy_TWh',
            'Total_Fossil_Energy_TWh', 'Total_Renewable_Energy_TWh',
            'Overall_Fossil_Fuel_Pct', 'Overall_Renewables_Pct',
            'Overall_Imported_Electricity_Pct', 'RES_Overall_RED_%', 'RES_E_RED_%',
            'Final_Fossil_Fuel_Pct', 'Final_Renewables_Pct', 'Primary_Fossil_TWh',
            'Primary_Renewable_TWh', 'Firm_Gas_Burnt_TWh', 'Firm_On_H2_Hydrogen_TWh',
            'Firm_On_H2_Electrolysis_TWh', 'Elec_Equiv_Fossil_TWh', 'Elec_Equiv_Fossil_Share_Pct',
            'Useful_Energy_TWh', 'Useful_Fossil_TWh', 'Useful_Fossil_Share_Pct'
        ] + list(SHARE_COLUMN_NAMES.values()):
            sim_df[c] = sim_df[c].round(3 if c.endswith('_TWh') else 2)
        anchor = sim_df.loc[sim_df['Year'] == TRANSITION_BASE_YEAR]
        if not anchor.empty:
            a = anchor.iloc[0]
            print(f">> 2026 shares of primary energy (excl. aviation and marine): fossil "
                  f"{a['Overall_Fossil_Fuel_Pct']:.1f}%, renewables {a['Overall_Renewables_Pct']:.1f}%, "
                  f"imported electricity {a['Overall_Imported_Electricity_Pct']:.1f}% "
                  f"({'from the dispatch' if INTERCONNECTOR_DISPATCH or FIXED_IMPORT_SHARE_PCT == 0 else 'fixed'}). Domestic final-energy "
                  f"accounting: fossil {a['Final_Fossil_Fuel_Pct']:.1f}%. Modelled RES Overall (share of gross final "
                  f"energy) {a['RES_Overall_RED_%']:.1f}% (SEAI published 17.1% for IE in 2025, incl. bioenergy and "
                  f"biofuels not modelled here)")
        # Full decarbonisation year: first year the primary fossil share is at or below the threshold.
        def first_year_at_or_below(limit):
            hit = sim_df.loc[sim_df['Overall_Fossil_Fuel_Pct'] <= limit, 'Year']
            return int(hit.min()) if not hit.empty else None
        decarb_year = first_year_at_or_below(DECARBONISED_FOSSIL_PCT)
        decarb_year_strict = first_year_at_or_below(DECARBONISED_FOSSIL_PCT_STRICT)
        sc['Full_Decarbonisation_Year'] = decarb_year if decarb_year else f'not by {final_year}'
        sc['Full_Decarbonisation_Year_5pct'] = decarb_year_strict if decarb_year_strict else f'not by {final_year}'
        hit = sim_df.loc[sim_df['Elec_Equiv_Fossil_Share_Pct'] <= DECARBONISED_FOSSIL_PCT, 'Year']
        sc['Full_Decarbonisation_Year_Elec_Equiv'] = int(hit.min()) if not hit.empty else f'not by {final_year}'
        def transition_box(year):
            """Text of the red box: primary energy shares and what firm plant would need."""
            r = sim_df.loc[sim_df['Year'] == year].iloc[0]
            return (f"Primary energy {year} (excl. aviation, marine)\n"
                    f"Fossil: {r['Overall_Fossil_Fuel_Pct']:.0f}% | Renewable: {r['Overall_Renewables_Pct']:.0f}%"
                    f" | Imports: {r['Overall_Imported_Electricity_Pct']:.0f}%\n"
                    f"Firm capacity needed: {r['Firm_Capacity_Required_GW']:.1f} GW\n"
                    f"Firm generation: {r['Firm_Generation_TWh']:.0f} TWh (gas today)\n"
                    f"Same firm output from green H2: +{r['Firm_On_H2_Electrolysis_TWh']:.0f} TWh electricity")

        print(f">> Full decarbonisation (fossil <= {DECARBONISED_FOSSIL_PCT:g}% of primary energy): "
              f"{sc['Full_Decarbonisation_Year']}; at <= {DECARBONISED_FOSSIL_PCT_STRICT:g}%: "
              f"{sc['Full_Decarbonisation_Year_5pct']}")
        capacity_df = pd.DataFrame(capacity_rows).round(1)
        capacity_df = capacity_df[(capacity_df['Zone'] != 'UNZONED') | (capacity_df['Battery_MW'].abs() > 0)]
        validate_results(scenario_name, sim_df, capacity_df, balance_err_by_year)

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
        # Regional bands (issue #3): IE and NI each use their own hindcast error; the all-island
        # band adds the two regional bands (GridCon_IE_pts + GridCon_NI_pts = GridCon_%).
        b_ie, b_ni = hindcast_band_by_region['IE'], hindcast_band_by_region['NI']
        for reg, b in (('IE', b_ie), ('NI', b_ni)):
            sim_df[f'Con_{reg}_Low_%'] = (sim_df[f'Con_{reg}_%'] * (1 - b)).clip(lower=0).round(2)
            sim_df[f'Con_{reg}_High_%'] = (sim_df[f'Con_{reg}_%'] * (1 + b)).round(2)
        band_low = sim_df['GridCon_IE_pts'] * b_ie + sim_df['GridCon_NI_pts'] * b_ni
        sim_df['GridCon_Low_%'] = (sim_df['GridCon_%'] - band_low).clip(lower=0).round(2)
        sim_df['GridCon_High_%'] = (sim_df['GridCon_%'] + band_low).round(2)
        band_factor_by_year = dict(zip(sim_df['Year'], np.where(sim_df['GridCon_%'] > 0,
                                                                band_low / sim_df['GridCon_%'], 0.0)))
        sim_df.insert(0, 'Scenario', sc['scenario'])
        sim_df = pd.concat([actual_df, sim_df], ignore_index=True, sort=False).sort_values('Year').reset_index(drop=True)

        # Backcast: V9 uses fixed 2026 headroom / fitted L for history (no scenario reinforcement %).
        bc_df, bc_errors = baseline_backcast, baseline_errors
        backcast_store[sc['scenario']] = (bc_df, bc_errors)

        key_years = [2026, 2027, 2028, 2030, 2033, 2036, 2039, 2042, 2045, 2048, 2049, 2050]
        key_df = sim_df[(sim_df['Data_Type'] == 'Forecast') & sim_df['Year'].isin(key_years)]
        main_cols = ['Year', 'Wind_Cap_GW', 'Wind_Offshore_GW', 'Dem_TWh', 'RawCurt_%', 'GridCon_%',
                     'GridCon_Low_%', 'GridCon_High_%', 'TotLoss_%', 'Wind_Fleet_CF_%_SEM', 'Wind_%_SEM']
        region_cols = ['Year', 'IE_Share_%', 'Headroom_SE_MW', 'Headroom_NI_MW', 'Con_IE_%', 'Con_NI_%',
                       'GridCon_IE_pts', 'GridCon_NI_pts', 'GridCon_%']
        zone_cols = ['Year'] + [f'Con_{z}_%' for z in HEADROOM_ZONES] + ['Con_OFFSHORE_%']
        print("\n====================================================================")
        print(f" SCENARIO '{scenario_name}': FORECAST RESULTS TABLES")
        print("====================================================================")
        print("All-island results (GridCon_% = zonal constraint as a share of all-island available wind):")
        print(key_df[main_cols].to_string(index=False))
        print("\nConstraint rollup IE/NI (Con_IE_% includes offshore wind):")
        print(key_df[region_cols].to_string(index=False))
        print("\nConstraint by zone (% of that zone's available onshore wind; OFFSHORE = all offshore wind, "
              "sharing SE headroom with rates or its own area's zone with the pipeline):")
        print(key_df[zone_cols].to_string(index=False))
        solar_cols = ['Year', 'Solar_Cap_GW', 'Solar_Avail_TWh', 'Solar_Gen_TWh', 'Solar_GridCon_%',
                      'Solar_Con_IE_%', 'Solar_Con_NI_%', 'Solar_RawCurt_%', 'Solar_TotLoss_%', 'Solar_CF_%',
                      'Solar_%', 'Wind+Solar_%']
        print("\nSolar (shares each zone's headroom with wind; SNSP counts wind + solar together):")
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

        print(f"\nInstalled capacity by zone, MW ({'ECP-GSS-1 pipeline' if use_pipeline else 'GW/yr rates'}; "
              f"batteries by zone are for reporting, dispatch is all-island):")
        show_years = [2026, 2030, 2040, 2050]
        if use_pipeline and complete_year <= final_year:
            show_years.append(int(np.ceil(complete_year)))
        cap_view = capacity_df[capacity_df['Year'].isin(sorted(set(show_years)))]
        cap_view = cap_view.assign(Wind_MW=cap_view['Wind_Onshore_MW'] + cap_view['Wind_Offshore_MW'])
        print(cap_view.pivot_table(index='Zone', columns='Year', values=['Wind_MW', 'Solar_MW', 'Battery_MW'],
                                   aggfunc='sum', sort=False).round(0).to_string())
        capacity_store[scenario_name] = capacity_df

        # Readable summaries: wind, solar, wind + solar by zone, and system dispatch-down by reason
        summaries = {k: pd.DataFrame(v) for k, v in summary_rows_by_kind.items()}
        transition_cols = [
            'Year', 'Background_Demand_Growth_TWh_per_Year',
            'Heat_Demand_Growth_TWh_per_Year', 'Transport_Demand_Growth_TWh_per_Year',
            'Total_Demand_Growth_TWh_per_Year', 'Heat_Electricity_Demand_TWh',
            'Transport_Electricity_Demand_TWh', 'Heat_Energy_Electrified_TWh',
            'Transport_Energy_Electrified_TWh', 'Remaining_Heat_Energy_TWh',
            'Remaining_Transport_Energy_TWh', 'Heat_Ambient_Renewable_TWh', 'Firm_Generation_TWh',
            'Fossil_Firm_Generation_TWh', 'Remaining_Heat_Fossil_TWh',
            'Remaining_Transport_Fossil_TWh', 'Total_Fossil_Energy_TWh',
            'Fossil_Electricity_Consumed_TWh', 'Renewable_Electricity_Consumed_TWh',
            'Total_Renewable_Energy_TWh', 'Gross_Final_Energy_TWh', 'Import_TWh', 'Export_TWh',
            'Export_Wind_Solar_TWh', 'Export_Synchronous_TWh', 'Net_Import_TWh',
            'Interconnector_Capacity_GW', 'Firm_Capacity_Required_GW',
            'Firm_Capacity_Peak_Residual_GW', f'Firm_Residual_P{FIRM_RESIDUAL_PERCENTILE:g}_GW',
            'Firm_Reserve_GW', 'Interconnector_Capacity_Credit_GW',
            'Firm_Capacity_Net_of_IC_Credit_GW',
            'Firm_Capacity_Legacy_Formula_GW',
            'Overall_Fossil_Fuel_Pct', 'Overall_Renewables_Pct',
            'Overall_Imported_Electricity_Pct', 'RES_Overall_RED_%', 'RES_E_RED_%'
        ] + list(SHARE_COLUMN_NAMES.values())
        transition_by_year = sim_df.loc[sim_df['Data_Type'] == 'Forecast', transition_cols].copy()
        for k in ('total', 'system'):
            drop_existing = [c for c in transition_cols if c != 'Year' and c in summaries[k].columns]
            if drop_existing:
                summaries[k] = summaries[k].drop(columns=drop_existing)
            summaries[k] = summaries[k].merge(transition_by_year, on='Year', how='left')
        for k in ('wind', 'system'):          # regional hindcast bands on all-island constraint (issue #3)
            c = summaries[k]['Constraint_%']
            fac = summaries[k]['Year'].map(band_factor_by_year).fillna(hindcast_band)
            summaries[k].insert(summaries[k].columns.get_loc('Constraint_%') + 1, 'Constraint_Low_%', (c * (1 - fac)).clip(lower=0).round(2))
            summaries[k].insert(summaries[k].columns.get_loc('Constraint_Low_%') + 1, 'Constraint_High_%', (c * (1 + fac)).round(2))
        record_check('results', scenario_name, 'zone summaries add up to the all-island figures',
                     'PASS' if summary_gap <= 0.01 else 'WARN', f"largest gap {summary_gap:.4f} pts of available energy")
        summary_store[scenario_name] = summaries
        evaluation_df = pd.concat([historical_evaluation.assign(Scenario=scenario_name), pd.DataFrame(evaluation_rows)],
                                  ignore_index=True, sort=False)
        evaluation_store[scenario_name] = evaluation_df
        try:
            evaluation_df.to_csv(os.path.join(out_dir, EVALUATION_CSV), index=False)
        except OSError as e:
            print(f">> Could not save {EVALUATION_CSV}: {e}")
        for k, df_k in summaries.items():
            try:
                df_k.to_csv(os.path.join(out_dir, f"summary_{k}.csv"), index=False)
            except OSError as e:
                print(f">> Could not save summary_{k}.csv: {e}")
        print(f"\nConstraint and curtailment by zone, wind + solar (% of each zone's available output; "
              f"full tables in summary_wind / summary_solar / summary_total / summary_system.csv):")
        tz = summaries['total'].set_index('Year').loc[[y for y in (2026, 2030, 2040, final_year) if y in simulation_years]]
        print(tz[[f'{z}_constraint_%' for z in summary_zones] + [f'{z}_curtailment_%' for z in summary_zones]]
              .rename(columns=lambda c: c.replace('_constraint_%', ' con').replace('_curtailment_%', ' curt')).to_string())
        print("\nSystem dispatch-down by reason (% of available wind + solar; physical and reporting reclassification):")
        print(summaries['system'].set_index('Year').loc[tz.index][['Constraint_%', 'SNSP_Curtailment_%', 'MinGen_Curtailment_%',
                                                                  'Total_Dispatch_Down_%']].to_string())
        try:
            capacity_df.to_csv(os.path.join(out_dir, CAPACITY_BY_ZONE_CSV), index=False, float_format='%.1f')
            print(f">> Capacity by zone and year saved to '{os.path.join(out_dir, CAPACITY_BY_ZONE_CSV)}'")
        except OSError as e:
            print(f">> Could not save '{CAPACITY_BY_ZONE_CSV}': {e}")

        print("\n====================================================================")
        print(f" SCENARIO '{scenario_name}': {final_year} MODEL OUTCOME SUMMARY")
        print("====================================================================")
        row_final = sim_df[sim_df['Year'] == final_year].iloc[0]
        actual_cap_gw = row_final['Wind_Cap_GW']
        actual_dem_twh = row_final['Dem_TWh']
        actual_wind_pct = row_final['Wind_%_SEM']
        actual_gen_twh = max(0.0, actual_dem_twh * (actual_wind_pct / 100.0))
    
        firm_thermal_required_gw = float(row_final['Firm_Capacity_Required_GW'])
        fossil_pct_final = float(row_final['Overall_Fossil_Fuel_Pct'])
        overall_renewables_pct_final = float(row_final['Overall_Renewables_Pct'])
        imported_pct_final = float(row_final['Overall_Imported_Electricity_Pct'])

        # Long-term chart databox metrics. Total dispatch-down uses the final
        # year's mutually exclusive reporting categories: recoverable grid
        # constraint plus Operational Curtailment / Oversupply.
        row_2035_matches = sim_df[sim_df['Year'] == min(2035, final_year)]
        row_2035 = row_2035_matches.iloc[0]
        wind_pct_2035 = float(row_2035['Wind_%_SEM'])
        wind_pct_final = float(row_final['Wind_%_SEM'])
        wind_cf_final = float(row_final['Wind_Fleet_CF_%_SEM'])
        solar_cf_final = float(row_final['Solar_CF_%'])
        total_dispatch_down_final_twh = float(
            row_final['Recoverable_Grid_Constraint_TWh']
            + row_final['Operational_Curtailment_Oversupply_TWh']
        )
    
        print(f">> Total Projected Demand ({final_year})      : {actual_dem_twh:.2f} TWh")
        print(f">> Usable Wind Generation ({final_year})      : {actual_gen_twh:.2f} TWh ({actual_wind_pct:.2f}% of demand)")
        print(f">> Installed Wind Capacity ({final_year})     : {actual_cap_gw:.2f} GW")
        print(f">> Usable Solar Generation ({final_year})     : {row_final['Solar_Gen_TWh']:.2f} TWh ({row_final['Solar_%']:.2f}% of demand)")
        print(f">> Installed Solar Capacity ({final_year})    : {row_final['Solar_Cap_GW']:.2f} GW")
        print(f">> Wind + Solar Share of Demand ({final_year}): {row_final['Wind+Solar_%']:.2f}%")
        print(f">> Required Firm Capacity ({final_year}) : {firm_thermal_required_gw:.2f} GW "
              f"(peak residual {row_final['Firm_Capacity_Peak_Residual_GW']:.2f} + reserve (largest infeed + operating) "
              f"{row_final['Firm_Reserve_GW']:.2f} GW; net of interconnector credit "
              f"{row_final['Firm_Capacity_Net_of_IC_Credit_GW']:.2f} GW; legacy formula "
              f"{row_final['Firm_Capacity_Legacy_Formula_GW']:.2f} GW)")
        print(f">> Firm residual P{FIRM_RESIDUAL_PERCENTILE:g} ({final_year})      : "
              f"{row_final[f'Firm_Residual_P{FIRM_RESIDUAL_PERCENTILE:g}_GW']:.2f} GW")
        print(f">> Interconnector flows ({final_year})        : imports {row_final['Import_TWh']:.2f} TWh, exports "
              f"{row_final['Export_TWh']:.2f} TWh ({row_final['Export_Wind_Solar_TWh']:.2f} wind/solar)")
        print(f">> Actual Firm Generation ({final_year})      : {row_final['Firm_Generation_TWh']:.2f} TWh/year")
        print(f">> Applied Build-Out Rate             : {annual_build_rate_gw*1000:.2f} MW/year ({annual_build_rate_gw:.3f} GW/year)")
        print(f">> Applied Forecast SNSP / MUON      : {snsp_limit_pct:.1f}% SNSP; IE {muon_units_ie} + NI {muon_units_ni} = {total_muon_units} units x {MUON_MIN_GEN_PER_UNIT_MW:.0f} MW = {muon_floor_mw:.0f} MW minimum generation")

        latest_results[scenario_name] = sim_df
        if not make_charts:
            return sim_df
        scenario_stage[scenario_name] = 'charts'
        say("  charts", end='')

        hist_weather_map = {2026: 2026}
        future_loop_years = complete_weather_years
        hist_weather_map.update({fy: future_loop_years[(fy - 2027) % len(future_loop_years)]
                                 for fy in range(2027, final_year + 1)})

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
                                        'storage_discharge_gwh': 0.0,
                                        'potential_curtailment_gwh': 0.0,
                                        'interconnector_import_gwh': 0.0,
                                        'renewable_export_gwh': 0.0})
                    continue
                row = sim_df[sim_df['Year'] == y].iloc[0]
                dem_y = float(row['Dem_TWh'])
                solar_y, s_share_y = solar_setup(row)
                snsp_y = snsp_fraction_for_year(y)
                df_wy = merged[merged['year'] == hist_weather_map[y]]
                hist_avg = df_wy['sem_demand'].mean()
                scale = (dem_y * 1e6 / 8760.0) / hist_avg if hist_avg > 0 else 1.0
                # Dispatch the complete weather year in one chronological pass. This preserves
                # state of charge between months and prevents a fresh initial SOC being created
                # twelve times in a year solely for plotting.
                wind_on_y, wind_off_y, _, _, _ = wind_avail_for_year(df_wy['spec_avail_mw_per_gw'].values, y)
                avail_year = wind_on_y + wind_off_y
                solar_year = df_wy['solar_avail_mw_per_gw'].values * solar_y
                demand_year = scenario_demand_mw(df_wy, dem_y, y)
                sp_y, se_y = storage_for_year(y)
                d_year = dispatch_year(df_wy['spec_avail_mw_per_gw'].values, solar_year, demand_year, y,
                                       snsp_y, sp_y, se_y)
                usable_w_year = d_year['usable_w']
                usable_s_year = d_year['usable_s']
                months_year = df_wy['month'].to_numpy()
                for m in sorted(df_wy['month'].dropna().unique()):
                    mask = months_year == m
                    hours = pd.Period(f"{y}-{int(m):02d}").days_in_month * 24.0
                    records.append({'year': y, 'month': int(m),
                                    'demand_gwh': demand_year[mask].mean() * hours / 1000.0,
                                    'usable_wind_gwh': usable_w_year[mask].mean() * hours / 1000.0,
                                    'usable_solar_gwh': usable_s_year[mask].mean() * hours / 1000.0,
                                    'storage_charge_gwh': d_year['charge_mw'][mask].mean() * hours / 1000.0,
                                    'storage_discharge_gwh': d_year['discharge_mw'][mask].mean() * hours / 1000.0,
                                    'potential_curtailment_gwh': d_year['potential_curt_mw'][mask].mean() * hours / 1000.0,
                                    'interconnector_import_gwh': 0.0,
                                    'renewable_export_gwh': 0.0})
            return records

        records_19_30 = monthly_series(hist_chart_years, historical=True) + monthly_series(range(2026, 2031))
        df_g1 = pd.DataFrame(records_19_30)
        df_g1['date'] = pd.to_datetime(df_g1[['year', 'month']].assign(day=1))
        df_g1 = df_g1.sort_values('date').drop_duplicates(subset=['date'], keep='first')

        fig1, ax1 = plt.subplots(figsize=(13.3, 6.5), dpi=100)
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
        ax1.fill_between(df_g1['date'], storage_top1, np.maximum(storage_top1, df_g1['demand_gwh']),
                         color='#D3D3D3', linewidth=0, alpha=0.8, zorder=0,
                         label='Firm (dispatchable: gas today)')
        ax1.axhline(0, color='#666666', linewidth=0.8)
        ax1.plot(df_g1['date'], df_g1['demand_gwh'], color='black', linewidth=2.2, label='Demand (GWh)')

        x_nums1 = mdates.date2num(df_g1['date'])
        z_d1 = np.polyfit(x_nums1, df_g1['demand_gwh'], 1)
        p_d1 = np.poly1d(z_d1)
        ax1.plot(df_g1['date'], p_d1(x_nums1), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        row_2030 = sim_df[sim_df['Year'] == 2030].iloc[0]
        wind_pct_2030 = float(row_2030['Wind_%_SEM'])
        wind_cf_2030 = float(row_2030['Wind_Fleet_CF_%_SEM'])
        solar_cf_2030 = float(row_2030['Solar_CF_%'])
        firm_capacity_2030_gw = float(row_2030['Firm_Capacity_Required_GW'])
        fossil_pct_2030 = float(row_2030['Overall_Fossil_Fuel_Pct'])
        overall_renewables_pct_2030 = float(row_2030['Overall_Renewables_Pct'])
        imported_pct_2030 = float(row_2030['Overall_Imported_Electricity_Pct'])

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
            f"2030 Wind Capacity Factor: {wind_cf_2030:.1f}%\n"
            f"2030 Solar Capacity Factor: {solar_cf_2030:.1f}%\n"
            f"{capacity_box_line(2030)}\n"
            f"Wind Build Rate: {annual_build_rate_gw*1000:.1f} MW/yr\n"
            f"Solar Build Rate: {solar_build_rate_gw*1000:.1f} MW/yr\n"
            f"{snsp_muon_label(2030)}"
        )
        ax1.text(1.015, 0.03, stats_text1, transform=ax1.transAxes, va='bottom', fontsize=9.5, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))
        transition_text1 = transition_box(2030)
        ax1.text(1.015, 0.50, transition_text1, transform=ax1.transAxes, va='bottom', fontsize=9.0,
                 fontweight='bold', color='#8B0000', bbox=dict(boxstyle='round,pad=0.6',
                 facecolor='#FFF2F2', edgecolor='#8B0000', alpha=0.95))

        plt.tight_layout()
        g1_png = scenario_plot_filename("Historical_2019_2030_Overview.png")
        plt.savefig(os.path.join(out_dir, g1_png), dpi=CHART_DPI, bbox_inches='tight', pad_inches=0.08)
        print(f">> Graph 1 saved as '{g1_png}'!")

        # -------------------------------------------------------------------------
        # GRAPH 2: LONG-TERM FORECAST STACKED OVERVIEW (JAN 2045 - DEC 2050)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(f" 6. GENERATING GRAPH 2: LONG-TERM FORECAST ({max(start_year, final_year - 5)} - {final_year})")
        print("====================================================================")
    
        df_monthly2 = pd.DataFrame(monthly_series(range(max(start_year, final_year - 5), final_year + 1)))
        df_monthly2['date'] = pd.to_datetime(df_monthly2[['year', 'month']].assign(day=1))
        df_monthly2 = df_monthly2.sort_values('date')

        fig2, ax2 = plt.subplots(figsize=(13.3, 6.5), dpi=100)
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
        ax2.fill_between(df_monthly2['date'], storage_top2, np.maximum(storage_top2, df_monthly2['demand_gwh']),
                         color='#D3D3D3', linewidth=0, alpha=0.8, zorder=0,
                         label='Firm (dispatchable: gas today)')
        ax2.axhline(0, color='#666666', linewidth=0.8)
        ax2.plot(df_monthly2['date'], df_monthly2['demand_gwh'], color='black', linewidth=2.2, label='Demand (GWh)')

        x_nums2 = mdates.date2num(df_monthly2['date'])
        z_d2 = np.polyfit(x_nums2, df_monthly2['demand_gwh'], 1)
        p_d2 = np.poly1d(z_d2)
        ax2.plot(df_monthly2['date'], p_d2(x_nums2), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        ax2.plot([], [], ' ', label=f'{final_year} Wind % of Demand: {actual_wind_pct:.1f}%')

        ax2.set_title(scenario_plot_title(f'Ireland (All-Island) Energy Transition Forecast (Jan {max(start_year, final_year - 5)} to Dec {final_year})'), fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax2.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax2.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax2.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax2.xaxis.set_major_locator(mdates.YearLocator(1))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax2.set_xlim(df_monthly2['date'].iloc[0], df_monthly2['date'].iloc[-1])

        ax2.legend(loc='upper left', bbox_to_anchor=(1.015, 1.00), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=8.5)

        renewables_final_pct = renewables_including_storage_pct(final_year)
        stats_text2 = (
            f"{final_year} Demand: {actual_dem_twh:.2f} TWh\n"
            f"{final_year} Renewables (incl. Storage): {renewables_final_pct:.1f}%\n"
            f"Total Dispatch Down ({final_year}): {total_dispatch_down_final_twh:.2f} TWh/yr\n"
            f"Wind as % of Demand (2035): {wind_pct_2035:.1f}%\n"
            f"Wind as % of Demand ({final_year}): {wind_pct_final:.1f}%\n"
            f"{final_year} Wind Capacity Factor: {wind_cf_final:.1f}%\n"
            f"{final_year} Solar Capacity Factor: {solar_cf_final:.1f}%\n"
            f"{capacity_box_line(final_year)}\n"
            f"Wind Build Rate: {annual_build_rate_gw*1000:.1f} MW/yr\n"
            f"Solar Build Rate: {solar_build_rate_gw*1000:.1f} MW/yr\n"
            f"{snsp_muon_label(final_year)}"
        )
        ax2.text(1.015, 0.03, stats_text2, transform=ax2.transAxes, va='bottom', fontsize=8.7, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))
        transition_text2 = transition_box(final_year)
        ax2.text(1.015, 0.49, transition_text2, transform=ax2.transAxes, va='bottom', fontsize=9.0,
                 fontweight='bold', color='#8B0000', bbox=dict(boxstyle='round,pad=0.6',
                 facecolor='#FFF2F2', edgecolor='#8B0000', alpha=0.95))

        plt.tight_layout()
        g2_png = scenario_plot_filename(f"Forecast_{max(start_year, final_year - 5)}_{final_year}_Overview.png")
        plt.savefig(os.path.join(out_dir, g2_png), dpi=CHART_DPI, bbox_inches='tight', pad_inches=0.08)
        print(f">> Graph 2 saved as '{g2_png}'!")

        # -------------------------------------------------------------------------
        # HELPER FUNCTION FOR DAILY DISPATCH PROFILE CHARTS (GRAPHS 3, 4, 5, 6)
        # -------------------------------------------------------------------------
        def generate_daily_chart(target_year, month_num, day_num, output_filename, chart_title_suffix):
            row_yr = sim_df[sim_df['Year'] == target_year].iloc[0]
            demand_twh = float(row_yr['Dem_TWh'])
            required_firm_thermal_gw = float(row_yr['Firm_Capacity_Required_GW'])
            solar_gw_yr, solar_share_yr = solar_setup(row_yr)
            cap_gw = float(row_yr['Wind_Cap_GW'])      # installed wind (onshore + offshore) that year

            wy = hist_weather_map.get(target_year, complete_weather_years[target_year % len(complete_weather_years)])
            df_wy = merged[merged['year'] == wy].copy().sort_values('parsed_date').reset_index(drop=True)

            wind_on_yr, wind_off_yr, _, _, _ = wind_avail_for_year(df_wy['spec_avail_mw_per_gw'].to_numpy(), target_year)
            df_wy['scaled_avail_mw'] = wind_on_yr + wind_off_yr
            expected_avg_mw = (demand_twh * 1000000.0) / 8760.0
            actual_hist_avg_mw = df_wy['sem_demand'].mean()
            mw_scale = expected_avg_mw / actual_hist_avg_mw if actual_hist_avg_mw > 0 else 1.0
            df_wy['scaled_demand_mw'] = scenario_demand_mw(df_wy, demand_twh, target_year)

            # Dispatch the complete chronological weather year first, then extract the
            # requested day. This gives the chart the true SOC carried in from the
            # preceding day instead of resetting the battery at midnight.
            avail_w_year = df_wy['scaled_avail_mw'].to_numpy()
            avail_s_year = df_wy['solar_avail_mw_per_gw'].to_numpy() * solar_gw_yr
            demand_year = df_wy['scaled_demand_mw'].to_numpy()
            storage_power_day, storage_energy_day = storage_for_year(target_year)
            dd_year = dispatch_year(df_wy['spec_avail_mw_per_gw'].to_numpy(), avail_s_year, demand_year,
                                    target_year, snsp_fraction_for_year(target_year),
                                    storage_power_day, storage_energy_day)

            day_mask = ((df_wy['month'].to_numpy() == month_num) &
                        (df_wy['day'].to_numpy() == day_num))
            if not np.any(day_mask):
                print(f"Warning: Day {day_num} Month {month_num} not present in dataset!")
                return
            df_day = df_wy.loc[day_mask].copy()
            month_name = pd.to_datetime(f"2022-{month_num:02d}-{day_num:02d}").strftime('%B')

            time_hours = np.arange(day_mask.sum()) * INTERVAL_HOURS
            native_demand_mw = demand_year[day_mask]
            avail_w_mw = avail_w_year[day_mask]
            avail_s_mw = avail_s_year[day_mask]
            snsp_limit_mw = dd_year['operational_limit_mw'][day_mask]

            dd_day = {
                key: (value[day_mask] if isinstance(value, np.ndarray) else value)
                for key, value in dd_year.items() if key != 'reg'
            }
            dd_day['reg'] = {
                r: {tech: values[day_mask] for tech, values in dd_year['reg'][r].items()}
                for r in REGIONS
            }
            reg_cons_mw = {r: dd_day['reg'][r]['wind'] + dd_day['reg'][r]['solar'] for r in REGIONS}
            # Physical fitted constraint is retained in dd_day['con_w'] + dd_day['con_s'].
            # The chart uses the reporting-only split so coincident constrained
            # oversupply is shown as Operational Curtailment / Oversupply.
            original_grid_constraint_mw = dd_day['original_grid_constraint_mw']
            grid_constrained_oversupply_mw = dd_day['grid_constrained_oversupply_mw']
            grid_constraint_mw = dd_day['recoverable_grid_constraint_mw']
            operational_curtailment_oversupply_mw = dd_day['operational_curtailment_oversupply_mw']
            snsp_curtailed_mw = operational_curtailment_oversupply_mw
            storage_charge_mw = dd_day['charge_mw']
            d_mw = native_demand_mw + storage_charge_mw
            storage_discharge_mw = dd_day['discharge_mw']
            usable_w_mw, usable_s_mw = dd_day['usable_w'], dd_day['usable_s']
            total_avail_mw = avail_w_mw + avail_s_mw
            usable_tot_mw = usable_w_mw + usable_s_mw
            total_dispatch_down_mw = grid_constraint_mw + snsp_curtailed_mw

            fig, ax = plt.subplots(figsize=(13.3, 6.5), dpi=100)
            fig.subplots_adjust(right=0.73)

            ax.plot(time_hours, total_avail_mw, color='#2CA02C', linewidth=2.0, linestyle='--', label='Available Wind + Solar (MW)')
            ax.plot(time_hours, d_mw, color='black', linewidth=2.5, label='System Demand (MW)')
            ax.plot(time_hours, snsp_limit_mw, color='#D62728', linewidth=2.0, linestyle='-', label=f'Operational Limit (SNSP {100 * snsp_fraction_for_year(target_year):.0f}% / MUON floor)')
            # Firm requirement is the gap between renewable availability and the
            # shared operational limit, plus the gap from that limit to demand.
            ax.fill_between(time_hours, total_avail_mw, snsp_limit_mw,
                            where=(snsp_limit_mw > total_avail_mw), color='#BDBDBD', alpha=0.65,
                            label='Firm (dispatchable: gas today)', zorder=0)
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
                            facecolor='none', edgecolor='#D62728', hatch='///', linewidth=0.8, label='Operational Curtailment / Oversupply (MW)')
            ax.fill_between(time_hours, usable_tot_mw + snsp_curtailed_mw, total_avail_mw, where=(grid_constraint_mw > 0),
                            facecolor='none', edgecolor='#FF8C00', hatch='...', linewidth=0.8, label='Grid Constraints Loss (MW)')

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
            daily_original_cons_gwh = (original_grid_constraint_mw.sum() * INTERVAL_HOURS) / 1000.0
            daily_constrained_oversupply_gwh = (grid_constrained_oversupply_mw.sum() * INTERVAL_HOURS) / 1000.0
            if not np.isclose(
                daily_original_cons_gwh,
                daily_cons_gwh + daily_constrained_oversupply_gwh,
                rtol=1e-9,
                atol=1e-6,
            ):
                raise RuntimeError("Daily constraint reclassification failed its GWh check.")
            daily_cons_ie_gwh = (reg_cons_mw['IE'].sum() * 0.25) / 1000.0
            daily_cons_ni_gwh = (reg_cons_mw['NI'].sum() * 0.25) / 1000.0
            daily_tot_dd_gwh = (total_dispatch_down_mw.sum() * 0.25) / 1000.0
            daily_dd_pct = (daily_tot_dd_gwh / daily_avail_gwh) * 100.0 if daily_avail_gwh > 0 else 0.0

            firm_thermal_line = (
                f"Required Firm Capacity ({target_year}): {required_firm_thermal_gw:.2f} GW\n"
                if 'dunkelflaute' in chart_title_suffix.lower() else ''
            )
            stats_text = (
                f"Simulated: {day_num} {month_name} {target_year} | Weather {wy}\n"
                f"Installed: Wind {cap_gw:.2f} GW | Solar {solar_gw_yr:.2f} GW\n"
                f"Battery: {storage_power_day:.0f} MW / {storage_energy_day/1000.0:.2f} GWh\n"
                f"Daily Demand: {daily_dem_gwh:.1f} GWh\n"
                f"{firm_thermal_line}"
                f"Available Wind + Solar: {daily_avail_gwh:.1f} GWh\n"
                f"Grid Constraint Loss: {daily_cons_gwh:.1f} GWh\n"
                f"Operational Curtailment / Oversupply: {daily_curt_gwh:.1f} GWh\n"
                f"  incl. constrained oversupply: {daily_constrained_oversupply_gwh:.1f} GWh\n"
                f"Battery Charge / Discharge: {daily_charge_gwh:.1f} / {daily_discharge_gwh:.1f} GWh\n"
                f"{snsp_muon_label(target_year)}"
            )
            ax.text(1.015, 0.03, stats_text, transform=ax.transAxes, va='bottom', fontsize=9.5, fontweight='bold', color='#000080',
                     bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))

            # Data behind the chart, for paper figures (analysis/figure10_showcase.py)
            pd.DataFrame({
                'time_h': time_hours, 'demand_incl_charging_mw': d_mw, 'demand_mw': native_demand_mw,
                'available_wind_solar_mw': total_avail_mw, 'operational_limit_mw': snsp_limit_mw,
                'usable_wind_mw': usable_w_mw, 'usable_solar_mw': usable_s_mw,
                'battery_discharge_mw': storage_discharge_mw, 'battery_charge_mw': storage_charge_mw,
                'curtailment_oversupply_mw': snsp_curtailed_mw, 'grid_constraint_mw': grid_constraint_mw,
                'year': target_year, 'month': month_num, 'day': day_num, 'weather_year': wy,
                'wind_gw': cap_gw, 'solar_gw': solar_gw_yr, 'battery_mw': storage_power_day,
                'battery_mwh': storage_energy_day,
            }).to_csv(os.path.join(out_dir, 'chart_' + os.path.splitext(output_filename)[0] + '.csv'), index=False)
            plt.tight_layout()
            output_filename = scenario_plot_filename(output_filename)
            plt.savefig(os.path.join(out_dir, output_filename), dpi=CHART_DPI, bbox_inches='tight', pad_inches=0.08)
            plt.close(fig)
            print(f">> Chart saved as '{output_filename}' for {day_num} {month_name} {target_year}!")

        # -------------------------------------------------------------------------
        # GENERATE DAILY DISPATCH PROFILES (GRAPHS 3, 4, 5, 6)
        # -------------------------------------------------------------------------
        late_showcase_year = max(start_year, final_year - 2)
        mid_showcase_year = min(2033, final_year)   # average-day chart; 2033 unless the run ends sooner
        print("\n====================================================================")
        print(f" 7. GENERATING DAILY SHOWCASE PROFILES ({mid_showcase_year} & {late_showcase_year})")
        print("====================================================================")
        
        # Late-horizon showcase calculations. Use two years before the selected
        # final year, preserving the old 2048 behaviour when target_year is 2050.
        # Choosing this from sim_df guarantees that chart lookups remain in range.
        if late_showcase_year not in set(sim_df['Year'].astype(int)):
            available_years = sim_df['Year'].astype(int)
            late_showcase_year = int(available_years.iloc[(available_years - late_showcase_year).abs().argmin()])
        wy_2048 = hist_weather_map.get(
            late_showcase_year,
            complete_weather_years[late_showcase_year % len(complete_weather_years)]
        )
        df_wy_2048 = merged[merged['year'] == wy_2048].copy()
        row_2048 = sim_df[sim_df['Year'] == late_showcase_year].iloc[0]
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
            raise ValueError(f"No November-January days are available for the {late_showcase_year} weather reference year.")
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
        wy_2033 = hist_weather_map.get(mid_showcase_year, complete_weather_years[mid_showcase_year % len(complete_weather_years)])
        df_wy_2033 = merged[merged['year'] == wy_2033].copy()
        df_wy_2033['scaled_avail_mw'] = df_wy_2033['spec_avail_mw_per_gw'] * float(sim_df[sim_df['Year'] == mid_showcase_year]['Wind_Cap_GW'].values[0])
        daily_sums_2033 = df_wy_2033.groupby(['month', 'day'])['scaled_avail_mw'].sum().reset_index()
        daily_sums_2033 = daily_sums_2033.sort_values('scaled_avail_mw', ascending=True).reset_index(drop=True)
        
        avg_day_2033 = daily_sums_2033.iloc[int(len(daily_sums_2033) * 0.50)] # 50th percentile (Median average)
        
        # Generate Graph 3 (Storm {late_showcase_year})
        generate_daily_chart(late_showcase_year, int(storm_day['month']), int(storm_day['day']), f"Daily_Absolute_Storm_{late_showcase_year}.png", "Absolute Peak Wind Storm Event")
        
        # Generate Graph 4 (Typical Low {late_showcase_year})
        generate_daily_chart(late_showcase_year, int(low_avg_day['month']), int(low_avg_day['day']), f"Daily_Typical_Low_Average_{late_showcase_year}.png", "Typical Low-Average Wind Day")
        
        # Generate Graph 5 (Winter Dunkelflaute {late_showcase_year}: jointly low wind and solar)
        generate_daily_chart(late_showcase_year, int(dunkel_day['month']), int(dunkel_day['day']),
                             f"Daily_Dunkelflaute_{late_showcase_year}.png",
                             "Winter Dunkelflaute: Joint Low Wind and Solar Event")
        
        # Generate Graph 6 (Average 2033)
        generate_daily_chart(mid_showcase_year, int(avg_day_2033['month']), int(avg_day_2033['day']), f"Daily_Average_Wind_{mid_showcase_year}.png", "Average Wind Day")

        # Generate an additional 2040 daily chart selected from May-August. The chosen
        # day must contain both battery charging and discharging. Among qualifying
        # days, selection rewards both high renewable availability and high battery
        # throughput, so the result illustrates a genuine same-day storage cycle.
        target_cycle_year = min(2040, final_year)   # 2040 unless the run ends sooner
        row_cycle = sim_df[sim_df['Year'] == target_cycle_year].iloc[0]
        demand_cycle_twh = float(row_cycle['Dem_TWh'])
        solar_cycle_gw, solar_share_cycle = solar_setup(row_cycle)
        wy_cycle = hist_weather_map.get(target_cycle_year,
                                        complete_weather_years[target_cycle_year % len(complete_weather_years)])
        df_cycle = merged[merged['year'] == wy_cycle].copy().sort_values('parsed_date').reset_index(drop=True)
        wind_on_c, wind_off_c, _, _, _ = wind_avail_for_year(df_cycle['spec_avail_mw_per_gw'].to_numpy(),
                                                             target_cycle_year)
        wind_cycle = wind_on_c + wind_off_c
        solar_cycle = df_cycle['solar_avail_mw_per_gw'].to_numpy() * solar_cycle_gw
        expected_cycle_mw = (demand_cycle_twh * 1000000.0) / 8760.0
        hist_cycle_mw = df_cycle['sem_demand'].mean()
        demand_cycle = scenario_demand_mw(df_cycle, demand_cycle_twh, target_cycle_year)
        storage_power_cycle, storage_energy_cycle = storage_for_year(target_cycle_year)
        dd_cycle = dispatch_year(df_cycle['spec_avail_mw_per_gw'].to_numpy(), solar_cycle, demand_cycle,
                                 target_cycle_year, snsp_fraction_for_year(target_cycle_year),
                                 storage_power_cycle, storage_energy_cycle)
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
                                 f"Daily_Storage_Charge_Discharge_{target_cycle_year}.png",
                                 "High-Renewables Same-Day Battery Charge and Discharge")

        # -------------------------------------------------------------------------
        # GRAPH 7: GRAND MASTER OVERVIEW (JAN 2019 - DEC 2050)
        # -------------------------------------------------------------------------
        print("\n====================================================================")
        print(f" 8. GENERATING GRAPH 7: GRAND MASTER OVERVIEW (2019 - {final_year})")
        print("====================================================================")
    
        # Extract Maximum Wind % Attained and the Year it occurred for the stats box
        max_wind_row = sim_df.loc[sim_df['Wind_%_SEM'].idxmax()]
        max_wind_pct_val = max_wind_row['Wind_%_SEM']
        max_wind_year = int(max_wind_row['Year'])

        df_grand = pd.DataFrame(monthly_series(hist_chart_years, historical=True)
                                + monthly_series(range(start_year, final_year + 1)))

        df_grand['date'] = pd.to_datetime(df_grand[['year', 'month']].assign(day=1))
        df_grand = df_grand.sort_values('date').drop_duplicates(subset=['date'], keep='first')
        # Data behind the overview chart, for paper figures (analysis/figure10_showcase.py)
        df_grand.to_csv(os.path.join(out_dir, 'chart_monthly_overview.csv'), index=False)

        fig6, ax6 = plt.subplots(figsize=(14.5, 7), dpi=100)
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
        ax6.fill_between(df_grand['date'], storage_top6, np.maximum(storage_top6, df_grand['demand_gwh']),
                         color='#D3D3D3', linewidth=0, alpha=0.8, zorder=0,
                         label='Firm (dispatchable: gas today)')
        ax6.axhline(0, color='#666666', linewidth=0.8)
        ax6.plot(df_grand['date'], df_grand['demand_gwh'], color='black', linewidth=2.0, label='System Demand (GWh)')

        x_nums6 = mdates.date2num(df_grand['date'])
        z_d6 = np.polyfit(x_nums6, df_grand['demand_gwh'], 1)
        p_d6 = np.poly1d(z_d6)
        ax6.plot(df_grand['date'], p_d6(x_nums6), color='#555555', linestyle='--', linewidth=1.2, label='Demand Trend')

        ax6.set_title(scenario_plot_title(f'Ireland (All-Island) Grand Energy Transition Timeline & Wind Penetration (Jan 2019 to Dec {final_year})'), fontsize=14, fontweight='bold', color='#000080', pad=15)
        ax6.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
        ax6.set_xlabel('Year', fontsize=11, fontweight='bold')
        ax6.grid(True, linestyle=':', alpha=0.6, color='#CCCCCC')

        ax6.xaxis.set_major_locator(mdates.YearLocator(max(2, int(np.ceil((final_year - 2019) / 16.0)))))
        ax6.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax6.set_xlim(df_grand['date'].iloc[0], df_grand['date'].iloc[-1])

        ax6.legend(loc='upper left', bbox_to_anchor=(1.015, 1.00), frameon=True, facecolor='white', edgecolor='#D3D3D3', fontsize=8.2, ncol=1)

        # Added Max Wind % Attained (and the year) to the stats box
        renewables_final_pct = renewables_including_storage_pct(final_year)
        stats_text6 = (
            f"{final_year} Demand: {actual_dem_twh:.1f} TWh\n"
            f"{final_year} Renewables (incl. Storage): {renewables_final_pct:.1f}%\n"
            f"Total Dispatch Down ({final_year}): {total_dispatch_down_final_twh:.2f} TWh/yr\n"
            f"Wind as % of Demand (2035): {wind_pct_2035:.1f}%\n"
            f"Wind as % of Demand ({final_year}): {wind_pct_final:.1f}%\n"
            f"{final_year} Wind Capacity Factor: {wind_cf_final:.1f}%\n"
            f"{final_year} Solar Capacity Factor: {solar_cf_final:.1f}%\n"
            f"{capacity_box_line(final_year)}\n"
            f"Wind Build Rate: {annual_build_rate_gw*1000:.0f} MW/yr\n"
            f"Solar Build Rate: {solar_build_rate_gw*1000:.0f} MW/yr\n"
            f"{snsp_muon_label(final_year)}"
        )
        ax6.text(1.015, 0.03, stats_text6, transform=ax6.transAxes, va='bottom', fontsize=8.7, fontweight='bold', color='#000080',
                 bbox=dict(boxstyle='round,pad=0.6', facecolor='#F0F4FF', edgecolor='#B0C4DE', alpha=0.9))
        transition_text6 = transition_box(final_year)
        ax6.text(1.015, 0.49, transition_text6, transform=ax6.transAxes, va='bottom', fontsize=9.0,
                 fontweight='bold', color='#8B0000', bbox=dict(boxstyle='round,pad=0.6',
                 facecolor='#FFF2F2', edgecolor='#8B0000', alpha=0.95))

        plt.tight_layout()
        g6_png = scenario_plot_filename(f"Grand_Overview_2019_{final_year}.png")
        plt.savefig(os.path.join(out_dir, g6_png), dpi=CHART_DPI, bbox_inches='tight', pad_inches=0.08)
        print(f">> Grand Overview chart saved as '{g6_png}'!")

        # -------------------------------------------------------------------------
        # CHART-ONLY INTERCONNECTOR EXTREME SENSITIVITIES
        # -------------------------------------------------------------------------
        # Deliberately isolated from dispatch, CSV outputs, scenario summaries and
        # daily plots. The normal Gamma model remains interconnector-neutral.
        if interconnector_chart_sensitivities:
            celtic_year = int(round(float(sc.get('celtic_energised_year', DEFAULT_CELTIC_ENERGISED_YEAR))))
            mares_year = int(round(float(sc.get('mares_energised_year', DEFAULT_MARES_ENERGISED_YEAR))))

            def commissioned_ic_mw(year):
                cap = EXISTING_INTERCONNECTOR_CAPACITY_MW
                if int(year) >= celtic_year:
                    cap += CELTIC_INTERCONNECTOR_CAPACITY_MW
                if int(year) >= mares_year:
                    cap += MARES_INTERCONNECTOR_CAPACITY_MW
                return cap

            def build_ic_variant(base_df, mode):
                x = base_df.copy()
                for col in ('interconnector_import_gwh', 'renewable_export_gwh',
                            'potential_curtailment_gwh'):
                    if col not in x:
                        x[col] = 0.0
                forecast = x['year'] >= 2026
                hours = x.apply(lambda q: pd.Period(f"{int(q['year'])}-{int(q['month']):02d}").days_in_month * 24.0, axis=1)
                cap_gwh = np.array([commissioned_ic_mw(y) for y in x['year']], dtype=float) * hours.to_numpy() / 1000.0
                if mode == '50pct_Import':
                    # Fifty per cent of commissioned capacity imports, capped by native monthly demand.
                    # For this chart-only energy balance, imports displace the domestic
                    # stack proportionally; they never charge storage.
                    import_cap_gwh = 0.50 * cap_gwh
                    imp = np.where(forecast, np.minimum(import_cap_gwh, x['demand_gwh'].to_numpy()), 0.0)
                    domestic = (x['usable_wind_gwh'].fillna(0.0) + x['usable_solar_gwh'].fillna(0.0)
                                + x['storage_discharge_gwh'].fillna(0.0)).to_numpy()
                    allowed = np.maximum(0.0, x['demand_gwh'].to_numpy() - imp)
                    factor = np.divide(np.minimum(domestic, allowed), domestic,
                                       out=np.ones_like(domestic), where=domestic > 0.0)
                    x['usable_wind_gwh'] *= factor
                    x['usable_solar_gwh'] *= factor
                    x['storage_discharge_gwh'] *= factor
                    x['interconnector_import_gwh'] = imp
                elif mode == 'Max_Export':
                    # Export receives first call on the original post-zonal operational
                    # surplus. Export therefore displaces plotted BESS charging first.
                    exportable = x['potential_curtailment_gwh'].fillna(0.0).to_numpy()
                    exp = np.where(forecast, np.minimum(cap_gwh, exportable), 0.0)
                    x['renewable_export_gwh'] = exp
                    x['storage_charge_gwh'] = np.maximum(
                        0.0, x['storage_charge_gwh'].fillna(0.0).to_numpy() - exp)
                return x

            def plot_ic_overview(base_df, year_end, mode, stem):
                x = build_ic_variant(base_df, mode)
                x = x[x['year'] <= year_end].copy()
                fig, ax = plt.subplots(figsize=(14.5 if year_end > 2030 else 13.3, 7), dpi=100)
                fig.subplots_adjust(right=0.75)
                wind_top = x['usable_wind_gwh'].fillna(0.0)
                solar_top = wind_top + x['usable_solar_gwh'].fillna(0.0)
                storage_top = solar_top + x['storage_discharge_gwh'].fillna(0.0)
                ax.fill_between(x['date'], 0, wind_top, color='#90EE90', edgecolor='#2CA02C',
                                linewidth=0.8, label='Usable Wind Gen (GWh)', alpha=0.9)
                ax.fill_between(x['date'], wind_top, solar_top, color='#FFD54F', edgecolor='#E0A800',
                                linewidth=0.6, label='Solar Gen (GWh)', alpha=0.9)
                ax.fill_between(x['date'], solar_top, storage_top, color='#9467BD', edgecolor='#6F42A5',
                                linewidth=0.7, label='Storage Discharge (GWh)', alpha=0.9)
                if mode == '50pct_Import':
                    import_top = storage_top + x['interconnector_import_gwh'].fillna(0.0)
                    ax.fill_between(x['date'], storage_top, import_top, color='#4C78A8', edgecolor='#1F4E79',
                                    linewidth=0.7, label='Extreme 50% IC Imports (GWh)', alpha=0.88)
                    sensitivity_title = '(With Imports)'
                else:
                    ax.fill_between(x['date'], 0, -x['renewable_export_gwh'].fillna(0.0),
                                    color='#17A2B8', edgecolor='#0B6978', linewidth=0.7,
                                    label='Including Full Surplus Renewable Exports (GWh)', alpha=0.85)
                    sensitivity_title = '(FullExports)'
                ax.fill_between(x['date'], 0, -x['storage_charge_gwh'].fillna(0.0),
                                color='#FF8C00', edgecolor='#B05A00', linewidth=0.6,
                                label='Storage Charging (GWh)', alpha=0.78)
                ax.plot(x['date'], x['demand_gwh'], color='black', linewidth=2.0, label='Native Demand (GWh)')
                ax.axhline(0, color='#555555', linewidth=0.7)
                ax.set_title(scenario_plot_title(
                    f"{sensitivity_title} | 2019-{year_end}\nWith Interconnector +-Flow"),
                    fontsize=13, fontweight='bold', color='#000080', pad=13)
                ax.set_ylabel('Monthly Electricity GWh', fontsize=11, fontweight='bold')
                ax.set_xlabel('Year', fontsize=11, fontweight='bold')
                ax.grid(True, linestyle=':', alpha=0.55, color='#CCCCCC')
                ax.xaxis.set_major_locator(mdates.YearLocator(1 if year_end <= 2030 else 2))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
                ax.set_xlim(x['date'].iloc[0], x['date'].iloc[-1])
                ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1.0), fontsize=8.3,
                          frameon=True, facecolor='white', edgecolor='#D3D3D3')
                note = (f"Existing IC: {EXISTING_INTERCONNECTOR_CAPACITY_MW/1000:.2f} GW\n"
                        f"Celtic +{CELTIC_INTERCONNECTOR_CAPACITY_MW/1000:.2f} GW from {celtic_year}\n"
                        f"Mares +{MARES_INTERCONNECTOR_CAPACITY_MW/1000:.2f} GW from {mares_year}\n"
                        "Import case uses 50% of commissioned capacity\n"
                        "Chart-only sensitivity; not a market-flow forecast")
                ax.text(1.01, 0.03, note, transform=ax.transAxes, va='bottom', fontsize=8.8,
                        color='#000080', bbox=dict(boxstyle='round,pad=0.5', facecolor='#F0F4FF',
                                                   edgecolor='#B0C4DE', alpha=0.92))

                # Transition box for the sensitivity chart. Imported Electricity is shown
                # only for the explicit 50% import case, using that case's actual annual
                # import energy. It is deliberately omitted from all other red boxes.
                end = x[x['year'] == year_end]
                base_transition = sim_df.loc[sim_df['Year'] == year_end].iloc[0]
                sensitivity_import_twh = end['interconnector_import_gwh'].sum() / 1000.0
                sensitivity_renewable_electricity_twh = (
                    end['usable_wind_gwh'].sum() + end['usable_solar_gwh'].sum()
                    + end['storage_discharge_gwh'].sum()) / 1000.0
                sensitivity_demand_twh = end['demand_gwh'].sum() / 1000.0
                sensitivity_fossil_electricity_twh = max(
                    0.0, sensitivity_demand_twh - sensitivity_renewable_electricity_twh
                    - sensitivity_import_twh)
                sensitivity_fossil_twh = (
                    float(base_transition['Remaining_Heat_Fossil_TWh'])
                    + float(base_transition['Remaining_Transport_Fossil_TWh'])
                    + sensitivity_fossil_electricity_twh)
                sensitivity_renewable_twh = (
                    float(base_transition['Heat_Ambient_Renewable_TWh'])
                    + sensitivity_renewable_electricity_twh)
                sensitivity_gfec_twh = (sensitivity_fossil_twh + sensitivity_renewable_twh
                                        + sensitivity_import_twh)
                if sensitivity_gfec_twh > 0.0:
                    sensitivity_fossil_pct = 100.0 * sensitivity_fossil_twh / sensitivity_gfec_twh
                    sensitivity_renewable_pct = 100.0 * sensitivity_renewable_twh / sensitivity_gfec_twh
                    sensitivity_import_pct = 100.0 * sensitivity_import_twh / sensitivity_gfec_twh
                else:
                    sensitivity_fossil_pct = sensitivity_renewable_pct = sensitivity_import_pct = 0.0

                transition_lines = [
                    f"Overall Transition Progress {year_end}",
                    f"Required Firm Capacity: {float(base_transition['Firm_Capacity_Required_GW']):.2f} GW",
                    f"Fossil-Fuel: {sensitivity_fossil_pct:.1f}%",
                    f"Renewables: {sensitivity_renewable_pct:.1f}%",
                ]
                if mode == '50pct_Import':
                    transition_lines.append(f"Imported Electricity: {sensitivity_import_pct:.1f}%")
                transition_text = "\n".join(transition_lines)
                ax.text(1.01, 0.49, transition_text, transform=ax.transAxes, va='bottom', fontsize=9.0,
                        fontweight='bold', color='#8B0000', bbox=dict(boxstyle='round,pad=0.6',
                        facecolor='#FFF2F2', edgecolor='#8B0000', alpha=0.95))
                plt.tight_layout()
                filename = scenario_plot_filename(f"{stem}_interconnector_{mode}.png")
                plt.savefig(os.path.join(out_dir, filename), dpi=CHART_DPI, bbox_inches='tight', pad_inches=0.08)
                plt.close(fig)
                print(f">> Interconnector sensitivity chart saved as '{filename}'!")

            print(">> Generating chart-only interconnector extreme sensitivities for this scenario.")
            plot_ic_overview(df_grand, 2030, '50pct_Import', 'Historical_2019_2030_Overview')
            plot_ic_overview(df_grand, final_year, '50pct_Import', f'Grand_Overview_2019_{final_year}')
            plot_ic_overview(df_grand, 2030, 'Max_Export', 'Historical_2019_2030_Overview')
            plot_ic_overview(df_grand, final_year, 'Max_Export', f'Grand_Overview_2019_{final_year}')

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
        plt.savefig(os.path.join(out_dir, g8_png), dpi=CHART_DPI)
        print(f">> Backcast chart saved as '{g8_png}'!")

        plt.close('all')
        return sim_df

    merged_input = merged.copy()   # untouched 15-minute data; each scenario starts from a copy
    scenario_file = next((input_path(f) for f in SCENARIO_FILE_CANDIDATES if os.path.exists(input_path(f))),
                         input_path(SCENARIO_FILE))
    summary_path = os.path.join(SCENARIO_OUTPUT_DIR, SCENARIO_SUMMARY_CSV)
    if os.path.exists(scenario_file):
        scenarios = load_scenarios(scenario_file)
        if len(sys.argv) > 1:
            name = sys.argv[1].lower()
            scenarios = [s for s in scenarios if s['scenario'].lower() == name]
            if not scenarios:
                raise ValueError(f"Scenario not found: {sys.argv[1]}")
        elif SCENARIOS_SWITCHED_OFF:
            skipped = [s['scenario'] for s in scenarios if s['scenario'].lower() in SCENARIOS_SWITCHED_OFF]
            scenarios = [s for s in scenarios if s['scenario'].lower() not in SCENARIOS_SWITCHED_OFF]
            print(f">> Switched off in the workbook (run = no), not run: {', '.join(skipped)}")

        stop_on_failures('scenarios', SCENARIO_OUTPUT_DIR)
        print(f"\n>> Running {len(scenarios)} scenarios from '{scenario_file}' "
              f"(charts {'on' if SCENARIO_CHARTS else 'off'})")
        say(f"[5/5] Scenarios: {len(scenarios)} from {os.path.basename(scenario_file)} "
            f"(charts {'on' if SCENARIO_CHARTS else 'off'})")
        say_checks('scenarios')
        summary_rows, all_results, failed = [], [], []
        for i_sc, sc in enumerate(scenarios, start=1):
            out_dir = os.path.join(SCENARIO_OUTPUT_DIR, sc['scenario'])
            t_sc = time.time()
            say(f"   ({i_sc}/{len(scenarios)}) {sc['scenario']}  ", end='')
            scenario_stage[sc['scenario']] = 'model'
            try:
                res = run_scenario(
                    # Charts run to each scenario's target_year, including the 2030 and 2035 runs.
                    sc, out_dir, make_charts=SCENARIO_CHARTS,
                    interconnector_chart_sensitivities=False,   # chart-only IC cases dropped for simplicity
                )
            except Exception as e:
                _to_log(traceback.format_exc())
                where = traceback.extract_tb(e.__traceback__)[-1]
                stage = scenario_stage.get(sc['scenario'], 'model')
                say(f"\n      FAILED during {stage}: {type(e).__name__}: {e} "
                    f"(line {where.lineno}; traceback in {RUN_LOG})")
                if stage == 'charts' and sc['scenario'] in latest_results:
                    say("      results were saved before the charts failed; continuing")
                    res = latest_results[sc['scenario']]
                else:
                    failed.append(sc['scenario'])
                    continue
            sy = summary_store[sc['scenario']]['system'].set_index('Year')
            tw = summary_store[sc['scenario']]['total'].set_index('Year')
            say(f" done ({fmt_secs(time.time() - t_sc)})")
            sc_final_year = int(sc.get('target_year', 2050))
            say(f"      {sc_final_year}: constraint {sy.loc[sc_final_year, 'Constraint_%']:.1f}% "
                f"[{sy.loc[sc_final_year, 'Constraint_Low_%']:.1f}-{sy.loc[sc_final_year, 'Constraint_High_%']:.1f}], "
                f"curtailment {sy.loc[sc_final_year, 'SNSP_Curtailment_%'] + sy.loc[sc_final_year, 'MinGen_Curtailment_%']:.1f}%, "
                f"wind+solar {tw.loc[sc_final_year, 'Share_of_Demand_%']:.0f}% of demand")
            say_checks('results', sc['scenario'])
            all_results.append(res)
            sc_years = [y for y in (2030, 2035, 2040, 2050, 2075, 2100) if y <= sc_final_year]
            for yr in sorted(set(sc_years + [sc_final_year])):
                r = res[res['Year'] == yr]
                if r.empty:
                    continue
                r = r.iloc[0]
                summary_rows.append({
                    'Scenario': sc['scenario'], 'Description': sc['description'], 'Year': yr,
                    'Full_Decarbonisation_Year': sc.get('Full_Decarbonisation_Year', ''),
                    'Full_Decarbonisation_Year_5pct': sc.get('Full_Decarbonisation_Year_5pct', ''),
                    'Scenario_Path': sc.get('scenario_path', ''), 'Weather_Years': sc.get('weather_years', '') or 'all',
                    'Headroom_Pipeline_Cover_%': sc.get('headroom_pipeline_cover_pct', 0.0),
                    'Build_Wind_IE_GW_yr': round(sc['build_rate_wind_ie'], 3),
                    'Build_Wind_NI_GW_yr': round(sc['build_rate_wind_ni'], 3),
                    'Build_Solar_IE_GW_yr': round(sc['build_rate_solar_ie'], 3),
                    'Build_Solar_NI_GW_yr': round(sc['build_rate_solar_ni'], 3),
                    'SNSP_%': r.get('SNSP_Limit_%', sc['snsp_limit_pct']),
                    'MUON_Floor_MW': r.get('MUON_Floor_MW', np.nan),
                    'Storage_Power_Build_MW_yr': sc['storage_power_build_rate_mw'],
                    'Storage_Energy_Build_MWh_yr': sc['storage_energy_build_rate_mwh'],
                    'Storage_Power_2026_MW': sc['storage_power_2026_mw'],
                    'Storage_Energy_2026_MWh': sc['storage_energy_2026_mwh'],
                    'Headroom_Curve': sc.get('headroom_curve', DEFAULT_HEADROOM_CURVE),
                    'Headroom_Scale': sc.get('headroom_scale', DEFAULT_HEADROOM_SCALE),
                    'IE_Reinf_%_yr': sc['ie_reinforcement_pct'] if (is_reinforcement_curve(sc.get('headroom_curve', '')) or is_hybrid_tid_2035_curve(sc.get('headroom_curve', ''))) else '',
                    'NI_Reinf_%_yr': sc['ni_reinforcement_pct'] if (is_reinforcement_curve(sc.get('headroom_curve', '')) or is_hybrid_tid_2035_curve(sc.get('headroom_curve', ''))) else '',
                    'Build_Wind_Offshore_GW_yr': round(sc.get('build_rate_wind_offshore', 0.0), 3),
                    'Capacity_Source': sc.get('capacity_source', DEFAULT_CAPACITY_SOURCE),
                    'Pipeline_Target_Year': sc['pipeline_target_year'] if sc.get('capacity_source') == 'pipeline' else '',
                    'Pipeline_Build_Pct': sc['pipeline_build_pct'] if sc.get('capacity_source') == 'pipeline' else '',
                    'Pipeline_Complete_Year': (round(pipeline_complete_year(sc['pipeline_target_year'], sc['pipeline_build_pct']), 1)
                                               if sc.get('capacity_source') == 'pipeline' else ''),
                    'Headroom_Note': sc.get('headroom_note', ''),
                    'Offshore_Connection': sc.get('offshore_connection', DEFAULT_OFFSHORE_CONNECTION),
                    'Background_Demand_Growth_TWh_yr': sc['background_demand_growth_twh_per_year'],
                    'Heat_Demand_Growth_TWh_yr': sc['heat_demand_growth_twh_per_year'],
                    'Transport_Demand_Growth_TWh_yr': sc['transport_demand_growth_twh_per_year'],
                    'Inputs_Defaulted': ' '.join(k for k in sc.get('defaulted', []) if k != 'description'),
                    'Wind_Cap_GW': r['Wind_Cap_GW'], 'Wind_Offshore_GW': r['Wind_Offshore_GW'],
                    'Storage_Power_MW': r['Storage_Power_MW'], 'Storage_Energy_MWh': r['Storage_Energy_MWh'],
                    'Dem_TWh': r['Dem_TWh'],
                    'Firm_Capacity_Required_GW': r['Firm_Capacity_Required_GW'],
                    'Firm_Capacity_Peak_Residual_GW': r['Firm_Capacity_Peak_Residual_GW'],
                    'Firm_Capacity_Legacy_Formula_GW': r['Firm_Capacity_Legacy_Formula_GW'],
                    'Firm_Capacity_Net_of_IC_Credit_GW': r['Firm_Capacity_Net_of_IC_Credit_GW'],
                    'Interconnector_Capacity_GW': r['Interconnector_Capacity_GW'],
                    'Import_TWh': r['Import_TWh'], 'Export_TWh': r['Export_TWh'],
                    'Export_Wind_Solar_TWh': r['Export_Wind_Solar_TWh'],
                    'Firm_Generation_TWh': r['Firm_Generation_TWh'],
                    'Firm_Peaking_Share_%': r['Firm_Peaking_Share_%'],
                    'Firm_Fleet_Efficiency_%': r['Firm_Fleet_Efficiency_%'],
                    'Firm_Gas_Burnt_TWh': r['Firm_Gas_Burnt_TWh'],
                    'Total_Fossil_Energy_TWh': r['Total_Fossil_Energy_TWh'],
                    'Total_Renewable_Energy_TWh': r['Total_Renewable_Energy_TWh'],
                    'Overall_Fossil_Fuel_Pct': r['Overall_Fossil_Fuel_Pct'],
                    'Overall_Renewables_Pct': r['Overall_Renewables_Pct'],
                    'Overall_Imported_Electricity_Pct': r['Overall_Imported_Electricity_Pct'],
                    'Final_Fossil_Fuel_Pct': r['Final_Fossil_Fuel_Pct'],
                    'Primary_Fossil_TWh': r['Primary_Fossil_TWh'],
                    'Firm_On_H2_Hydrogen_TWh': r['Firm_On_H2_Hydrogen_TWh'],
                    'Firm_On_H2_Electrolysis_TWh': r['Firm_On_H2_Electrolysis_TWh'],
                    'Con_WS_IE_%': r['Con_WS_IE_%'], 'Con_WS_NI_%': r['Con_WS_NI_%'],
                    'RES_Overall_RED_%': r['RES_Overall_RED_%'], 'RES_E_RED_%': r['RES_E_RED_%'],
                    **{new: r[new] for new in SHARE_COLUMN_NAMES.values()},
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
        pd.concat(capacity_store.values(), ignore_index=True).to_csv(
            os.path.join(SCENARIO_OUTPUT_DIR, "all_scenarios_" + CAPACITY_BY_ZONE_CSV), index=False, float_format='%.1f')
        for k in ('wind', 'solar', 'total', 'system'):
            pd.concat([v[k].assign(Scenario=s) for s, v in summary_store.items()], ignore_index=True) \
                .pipe(lambda df: df[['Scenario'] + [c for c in df.columns if c != 'Scenario']]) \
                .to_csv(os.path.join(SCENARIO_OUTPUT_DIR, f"all_scenarios_summary_{k}.csv"), index=False)
        if evaluation_store:
            write_evaluation_outputs(evaluation_store, historical_evaluation)
        if BACKCAST_SCENARIO_TREND and backcast_store:
            pd.concat([v[0].assign(Scenario=k) for k, v in backcast_store.items()], ignore_index=True).round(3).to_csv(
                os.path.join(SCENARIO_OUTPUT_DIR, "all_scenarios_backcast.csv"), index=False)
        print("\n====================================================================")
        print(" SCENARIO SUMMARY")
        print("====================================================================")
        print(summary[summary['Year'] == summary['Year'].max()][['Scenario', 'Headroom_Curve', 'GridCon_%', 'GridCon_Low_%',
                                                'GridCon_High_%', 'Con_IE_%', 'Con_NI_%', 'RawCurt_%',
                                                'Wind_%_SEM', 'Solar_Cap_GW', 'Solar_GridCon_%',
                                                'Solar_RawCurt_%', 'Solar_%', 'Wind+Solar_%']].to_string(index=False))
        print(">> Backcast (same for every scenario): forecast starting limits run back over history; "
              f"see section 2 and '{os.path.join(SCENARIO_OUTPUT_DIR, 'backcast_results.csv')}'.")
        print(f"\n>> Summary (2030/2040/2050) saved to '{summary_path}'; every year of every "
              f"scenario saved to '{os.path.join(SCENARIO_OUTPUT_DIR, 'all_scenarios_by_year.csv')}'")
        print("\n====================================================================")
        print(" VALIDATION")
        print("====================================================================")
        report = pd.DataFrame(VALIDATION)
        print(report.groupby(['Stage', 'Status']).size().unstack(fill_value=0).to_string())
        issues = report[report['Status'] != 'PASS']
        if len(issues):
            print(issues[['Stage', 'Scenario', 'Check', 'Status', 'Detail']].to_string(index=False))
        print(f">> Validation report saved to '{write_validation_report(SCENARIO_OUTPUT_DIR)}'")
        def report_years(name):
            end = int(next(s['target_year'] for s in scenarios if s['scenario'] == name))
            return sorted({y for y in (2030, 2035, 2050, 2075) if y <= end} | {end})

        say("")
        say("RESULTS  (wind + solar dispatch-down, % of available)")
        say(f"   {'scenario':<26} {'year':>4}  {'constraint':>17}  {'SNSP':>5}  {'min gen':>7}  {'total':>6}  {'RES share':>9}")
        for name, v in summary_store.items():
            sy, tw = v['system'].set_index('Year'), v['total'].set_index('Year')
            for y in report_years(name):
                band = f"{sy.loc[y, 'Constraint_%']:.1f} [{sy.loc[y, 'Constraint_Low_%']:.1f}-{sy.loc[y, 'Constraint_High_%']:.1f}]"
                say(f"   {name if y == report_years(name)[0] else '':<26} {y:>4}  {band:>17}  {sy.loc[y, 'SNSP_Curtailment_%']:>5.1f}  "
                    f"{sy.loc[y, 'MinGen_Curtailment_%']:>7.1f}  "
                    f"{sy.loc[y, 'Total_Dispatch_Down_%']:>6.1f}  {tw.loc[y, 'Share_of_Demand_%']:>8.0f}%")
        if evaluation_store:
            say("")
            say("CAPACITY FACTORS AND CURTAILMENT  (delivered CF = after all dispatch-down; curtailment excludes grid constraint)")
            say(f"   {'scenario':<26} {'year':>4}  {'wind CF avail/deliv':>19}  {'solar CF avail/deliv':>20}  "
                f"{'wind curt':>9}  {'solar curt':>10}")
            for name, ev_df in evaluation_store.items():
                e = ev_df[ev_df['Data_Type'] == 'Forecast'].set_index('Year')
                for y in report_years(name):
                    say(f"   {name if y == report_years(name)[0] else '':<26} {y:>4}  "
                        f"{e.loc[y, 'Wind_Available_CF_%']:>9.1f} / {e.loc[y, 'Wind_Delivered_CF_%']:>5.1f}%  "
                        f"{e.loc[y, 'Solar_Available_CF_%']:>10.1f} / {e.loc[y, 'Solar_Delivered_CF_%']:>5.1f}%  "
                        f"{e.loc[y, 'Wind_Curtailment_%']:>8.1f}%  {e.loc[y, 'Solar_Curtailment_%']:>9.1f}%")
            act = historical_evaluation[historical_evaluation['Data_Type'] == 'Actual']
            if len(act):
                a = act.sort_values('Year').iloc[-1]
                say(f"   {'actual (all-island)':<26} {int(a['Year']):>4}  "
                    f"{a.get('Wind_Available_CF_%', np.nan):>9.1f} / {a.get('Wind_Delivered_CF_%', np.nan):>5.1f}%  "
                    f"{a.get('Solar_Available_CF_%', np.nan):>10.1f} / {a.get('Solar_Delivered_CF_%', np.nan):>5.1f}%  "
                    f"{a.get('Wind_Curtailment_%', np.nan):>8.1f}%  "
                    f"{a.get('Solar_Curtailment_%', np.nan):>9.1f}%")
            say(f"   Full tables: {os.path.join(SCENARIO_OUTPUT_DIR, 'all_scenarios_' + EVALUATION_CSV)}; "
                f"chart: {os.path.join(SCENARIO_OUTPUT_DIR, EVALUATION_CHART)}")
        if failed:
            say(f"\n   FAILED scenarios (no results): {', '.join(failed)}  - see {RUN_LOG}")
        counts = pd.DataFrame(VALIDATION)['Status'].value_counts()
        say(f"\nChecks: {counts.get('PASS', 0)} passed, {counts.get('WARN', 0)} warnings, {counts.get('FAIL', 0)} failed "
            f"-> {os.path.join(SCENARIO_OUTPUT_DIR, VALIDATION_REPORT_CSV)}")
        say(f"Outputs: {SCENARIO_OUTPUT_DIR}/<scenario>/summary_wind | summary_solar | summary_total | summary_system.csv, "
            f"plus all_scenarios_summary_*.csv")
    else:
        run_scenario(interactive_scenario(), os.path.join(SCENARIO_OUTPUT_DIR, "interactive"), make_charts=True)

def run_demonstrator():
    """Run every scenario. The console gets a short readout; every detailed table goes to
    SCENARIO_OUTPUT_DIR/RUN_LOG. An error stops the run with a one-line reason; the full
    traceback is in the log."""
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    os.makedirs(SCENARIO_OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(SCENARIO_OUTPUT_DIR, RUN_LOG)
    _LOG['file'] = open(log_path, 'w', encoding='utf-8')
    previous_showwarning = warnings.showwarning
    warnings.showwarning = _warning_to_log            # library warnings go to the log, not the console
    t0 = time.time()
    try:
        _run_demonstrator()
        say(f"\nDone in {fmt_secs(time.time() - t0)}. Full detail of this run: {log_path}")
    except Exception as e:
        _to_log(traceback.format_exc())
        where = traceback.extract_tb(e.__traceback__)[-1]
        say(f"\nSTOPPED: {type(e).__name__}: {e}")
        say(f"   at {os.path.basename(where.filename)} line {where.lineno}; full traceback in {log_path}")
        raise SystemExit(1)
    finally:
        warnings.showwarning = previous_showwarning
        _LOG['file'].close()
        _LOG['file'] = None


if __name__ == "__main__":
    run_demonstrator()