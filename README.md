# WEST_GAMMA

Gamma is an open 15-minute dispatch model of the all-island (Ireland and Northern Ireland) electricity system. It separates network constraint from system-wide curtailment and projects how much of the planned wind and solar output can be used, what firm capacity and energy remain, and what electrification does to peak-day gas demand. It is the model behind the WEST Phase 1 paper, "Real-World Constraints on Ireland's Energy Transition: Electrification, Curtailment and Grid Limitations".

The code is joint work by the WEST group (Niall Burke, Cian Murtagh, Mark Kelly, Marcel Sarnecki and Laurentiu Dimache). Project aims, decisions and the location of the master copies of the paper are in `CONTEXT.md`; writing rules in `STYLE.md`; how changes are made in `WORKFLOW.md`; every change to results, with old and new values, in `CHANGELOG.md`.

## What the model does

In each 15-minute interval Gamma computes, in order: available wind and solar output in seven onshore zones and an offshore zone; network constraint in each zone (a lognormal effective limit calibrated on the TSOs' records); battery charging from output that would otherwise be curtailed; curtailment at the SNSP and minimum-units ceilings; battery discharge into the remaining headroom. Firm plant meets the rest of demand. Each simulated year is run on thirteen weather years (2014 to 2026). There is no unit commitment, market clearing or cost. The equations are in `docs/model_equations.md`.

## Running it

1. Python 3.10 or later: `pip install -r requirements.txt`.
2. Scenarios are rows of `Data_inputs/scenariosXLSX.xlsx` (sheet `Scenarios`; the `Field Guide` sheet explains every column). The paper uses two: `EirGrid_Extended` (EE) and `Historical_Trend` (HT). Rows with `run = yes` are run by `python Gamma.py`; any row can be run by name with `python Gamma.py <scenario>`.
3. `python Gamma.py` writes `scenario_outputs/`: one folder per scenario (`forecast_results.csv`, `summary_*.csv`, gas files, charts) and all-scenario tables. `GAMMA_CHARTS=0` gives a faster CSV-only run.
4. Switches (environment variables): `GAMMA_IC_DISPATCH=1` puts interconnector flows in the dispatch; `GAMMA_FLAT_GROWTH=0` scales underlying demand growth on the recorded shape instead of as flat load; `GAMMA_OFFSHORE_CF` sets the offshore capacity factor in weather year 2020 (default 0.40); `GAMMA_SIGMA_IE` and `GAMMA_SIGMA_NI` fix the constraint spread.

A full run of both scenarios to 2100 takes about 8 minutes with charts off and 25 minutes with charts on.

## Reproducing the paper

| Paper item | Command | Output |
|---|---|---|
| Tables 4 and S15, Figures 8, 9 and 10 | `python Gamma.py` (charts on for Figure 10) | `scenario_outputs/` |
| Figures 1, 2 and 6 | not drawn by a script in this repository | |
| Figure 3 | `python analysis/figure3_wind_history.py` | `analysis/output/paper/Figure_3.*` |
| Figure 4 | `python analysis/figure4_model_flow.py` | `analysis/output/paper/Figure_4.*` |
| Figure 5 | EE run to 2050 with charts on, then `python analysis/figure5_dunkelflaute.py <outputs>` | `Figure_5.*` |
| Table 2, Figure 7 | `python Gamma.py EirGrid_Validation_2030_Initial`, `python Gamma.py EirGrid_Validation_2030_2035`, then `python analysis/eirgrid_validation.py` | `analysis/output/eirgrid_validation.csv`, `Figure_7.*` |
| Figure 8 | main run and a run with the published network path kept after 2035, then `python analysis/figure8_projections.py <outputs> <published-path outputs>` | `Figure_8.*` |
| Figure 9 | `python analysis/figure9_energy_bases.py <outputs>` | `Figure_9.*` |
| Figure 10 | EE run with charts on and `target_year` 2052 for the 2050 days, then `python analysis/figure10_showcase.py <outputs>` | `Figure_10.*` |
| Table 5, Figure 11 | `python analysis/interconnector_sensitivity.py`, then `python analysis/figure11_gas.py analysis/ic_run/scenario_outputs` | `analysis/output/interconnector_sensitivity.*`, `Figure_11.*` |
| Section 7.3, Table S8 | `python analysis/grid_reinforcement_study.py` | `analysis/output/grid_reinforcement/` |
| Section 7.2, Tables S9 to S12 | `python analysis/sensitivity_study.py` | `analysis/output/sensitivity/` |
| Table 6 and Supplement S5, S9 tests | see `CHANGELOG.md`, 20 November 2026 | `analysis/output/sensitivity_tests.csv` |

Figure 1 is drawn from the TSOs' annual reports for 2011 to 2020 and the half-hourly records for 2021 to 2026; its script is not yet in the repository. Every figure script writes a vector PDF for submission and a 600 dpi PNG.

## Data

All inputs are public and listed in Supplementary Table S1: the TSOs' quarter-hourly system data and half-hourly dispatch-down records, monthly zonal dispatch down, EirGrid's ECP-GSS-1 generation lists and constraint results, the All-Island Resource Adequacy Assessment 2026 to 2035, Met Éireann hourly temperature at Dublin Airport, Gas Networks Ireland's Network Development Plan 2025 and SEAI's National Energy Projections 2026. They are in `Data_inputs/`.

## Licence

The code is released under the MIT licence; see `LICENSE`. Input data in `Data_inputs/` come from the public sources listed in Supplementary Table S1 and remain under their providers' terms.
