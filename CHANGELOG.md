# Changelog: SEM Wind Capacity & Loss Modelling Demonstrator

Handover record of changes to `DemonstratorV2.py` and its data builder `build_all_island_dd.py`.
The full methodology is in `Technical_Briefing_README.docx`.

## How to run

1. Put the EirGrid/SONI `DD-HH-<year>.xlsx` workbooks in `Demo\Raw Data` (2021–2026 so far; 2026 covers January to August).
2. Run `python build_all_island_dd.py`. It writes `system_dd_hourly_ie.csv`, `system_dd_hourly_ni.csv` and `system_dd_hourly_all_island.csv` into `Demo`.
3. Keep `Input - capacity, constraints, curtailment.xlsx` and `sem_demand_wind_from_2019.csv` in the same folder as `DemonstratorV2.py`.
4. Run `python DemonstratorV2.py`.
   - With `scenarios.csv` present, every scenario runs without prompts and results go to `scenario_outputs/` and `scenario_summary.csv`.
   - Without it, the script prompts for one scenario and writes `forecast_results.csv` and the charts to the script folder.

## V2: 10 October 2026

### Added
- **Fitted network-limit constraint model.** Constraint in each 15-minute interval is the expected available wind above an effective limit L that varies from hour to hour (lognormal spread σ). L and σ are fitted to hourly dispatch-down records (briefing Section 5B).
- **Separate models for Ireland (IE) and Northern Ireland (NI).** Each region has its own L and σ, and the results are reported per region and added for all-island. NI has been three to five times as constrained as IE since 2024 (26.4% against 5.1% in 2024).
- **`build_all_island_dd.py`.** Builds the hourly IE, NI and all-island files from the DD-HH workbooks, handling clock changes and part-years. Its IE output reproduces the earlier `system_dd_hourly.csv` exactly.
- **Inputs.** Separate IE and NI reinforcement rates (negative values allowed) and the share of new build located in IE. One-off limit steps per region via `REINFORCEMENT_STEPS_MW`.
- **Scenario batch mode.** `scenarios.csv` drives any number of runs. Outputs per scenario (CSV and charts), `all_scenarios_by_year.csv` and `scenario_summary.csv` (2030/2040/2050). `SCENARIO_CHARTS = False` gives CSV-only runs.
- **Rolling one-year-ahead hindcast.** Each year is predicted from a fit on the previous year. The typical all-island error is applied as a ± band (`GridCon_Low_%`, `GridCon_High_%`).
- **Regional results columns:** `IE_Share_%`, `Limit_IE_MW`, `Limit_NI_MW`, `Con_IE_%`, `Con_NI_%`, `GridCon_IE_pts`, `GridCon_NI_pts`.
- **`forecast_results.csv`,** with every forecast year.
- **Part-year support.** A year counts for fitting once it has 60 days of data (`MIN_HOURS_FOR_FIT`), and part-years are labelled "(n mo)".
- **Availability check** between the IE + NI hourly data and the 15-minute file, with a warning if they differ by more than 10%.

### Changed
- **Constraint now comes from the weather loop**, replacing `10% × (capacity ratio)^0.75`.
- **The fit matches recorded constraint energy exactly.** σ is chosen for the best hourly fit, and the separate calibration factor k has been removed.
- **Default fit years are 2024–2026 for both regions**, so the forecast starts from today's networks.
- **Usable generation is summed directly from the 15-minute dispatch** (from REV2), replacing the efficiency-factor formula. Capacity factor is reported from the result rather than assumed.
- **The monthly charts (Graphs 1, 2 and 6) are summed from the same interval dispatch** (from REV2), and all charts share one weather-year assignment.
- **Constraint is applied before SNSP** in the annual loop, matching the daily charts.
- **Curtailment is split** into an SNSP part, recalculated each year at the scenario's limit, and an "other causes" part held at its 2026 level. Curtailment can now fall as well as rise.
- **The daily charts** show the IE and NI limits and the constraint split between them.

### Fixed
- **Capacity timeline:** 2027 and 2028 had the same capacity, so 2050 was one build increment short. Each year from 2027 now adds one full increment.
- **Curtailment floor:** `max(0, …)` held curtailment at 4.9% or above, and the 2026 baseline was hard-coded at 75% SNSP.
- **Double-counted losses:** the capacity factor decline `ratio^-0.12` counted losses already captured by constraint and curtailment.
- **IE-only constraint data:** the hourly file was IE-only while the 15-minute data was all-island, so NI was implicitly given IE's constraint rate. Fixed by the regional split.
- **Graph 4** searched for its showcase day in one weather year and plotted a different one.
- **Build script:** a missing workbook produced a year of zero rows. The hourly grid now only covers days in the source.

### Removed
- The 0.75 power-law constraint scaling and its hindcast table.
- The "peak wind % so far" ratchet: Wind_% is now reported as calculated, so it can fall. REV2 keeps the ratchet on purpose (its NOTE 1). Agree one convention before publishing results.

## REV2: 10 October 2026, 11:30 (parallel version, not V2)

- Interval-summed dispatch for generation and the monthly charts. Both were carried into V2.
- "Advanced mode" toggles to switch off grid constraints or SNSP curtailment. Not carried into V2.
- Keeps the 0.75 power law, the wind % ratchet and the 2027 = 2028 capacity issue.

## V1: original `Demonstrator.py`

- Constraint `= base × (capacity ratio)^0.75`. SNSP curtailment by a delta from a 75% baseline. Generation from an efficiency factor. Hindcast table comparing against the spreadsheet without an error measure.

## Open issues and decisions for the next owner

- **Reinforcement assumptions drive the results.** On test data, 2050 all-island constraint ranged from about 16% (+3%/yr) to about 57% (−3%/yr). Present results as a range of scenarios.
- **Network trend.** IE's effective limit has fallen about 19% since 2023, and NI's fell sharply in 2023–2024 before partly recovering. Find out what drove these changes (outages, works, where new capacity connected) before choosing scenario values.
- **Uncertainty.** The effective limit moves about 10–20% from year to year (rolling hindcast, IE about ±15%). The band reflects this, but it is symmetric and simple.
- **Location of new build.** The share of new build in NI has a large effect, because NI is far more constrained. Base the default on connection data if available.
- **Same profile in both regions.** IE and NI use the same per-GW availability profile, and offshore wind is not modelled separately.
- **Curtailment.** Only SNSP curtailment is simulated. RoCoF, minimum generation and high-frequency curtailment are held at their 2026 share. Raising the SNSP limit has no effect unless the network is reinforced.
- **Sample console output** in the briefing predates V2 and needs refreshing from a full run.
- **Wind % ratchet:** V2 and REV2 handle this differently (see Removed).
