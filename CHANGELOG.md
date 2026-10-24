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

## Gamma V13 issue fixes: 24 October 2026

Changes to `Gamma.py` and `Data_inputs/scenariosXLSX.xlsx` for the open GitHub issues. Decisions on approach were agreed by Niall on 24 October; values marked PLACEHOLDER still need group agreement.

### Scenario inputs
- **Demand split.** Every scenario now has its own background / heat / transport growth (TWh/yr). Background 0.8 in all (Demand Calculator, IE background increase). Heat 0.15 and transport 0.25 in A, C, E, F, G. B 0.84 heat and 1.06 transport: full electrification of 70.6 TWh heat (COP 3.5) and 76 TWh transport (factor 3) over 24 years. D (No Transition) 0 and 0. The calculated `total_demand_growth_twh_per_year` column is now recognised and no longer warned about.
- **New columns:** `offshore_connection`, `ic_export_availability`, `ic_import_availability`, `ic_capacity_credit`, `celtic_energised_year`, `mares_energised_year`, `ie_reinforcement_mw_per_year`, `ni_reinforcement_mw_per_year`, `reinforcement_steps`. The Field Guide describes every column, including the storage rows that were blank.
- New check warns when a scenario adds battery MW with (almost) no MWh. E, F and G add 625.8 MW/yr after the pipeline completes with 0 MWh/yr; this was not changed and needs a decision.

### #1 Offshore wind connection
- Offshore wind has its own connection by default (`offshore_connection = own`): headroom equal to installed offshore capacity, no use of onshore zonal headroom. Its output still counts in SNSP and min-gen curtailment. `shared` restores the earlier treatment as a sensitivity. With `own`, OFFSHORE appears as its own zone in the summary files.

### #2 Reinforcement as a build path
- New `headroom_curve = reinforcement_mw`: 2026 headroom plus a fixed MW each year (`ie_/ni_reinforcement_mw_per_year`; IE split over zones by 2026 headroom).
- New `reinforcement_steps` column for named one-off steps on any built-in curve, e.g. `NI:2032:950` for the North–South interconnector (300 to 1,250 MW, October 2031, SEAI NEP26). No scenario uses either yet.

### #3 Regional uncertainty bands
- IE and NI each get a band from their own rolling hindcast error (IE ±11.2%, NI ±29.7%). The all-island band adds the regional bands applied to each region's constraint. New columns `Con_IE_Low/High_%`, `Con_NI_Low/High_%`.
- Investigation of the NI step change: NI available wind energy and the 99th-percentile hourly availability (a fleet-size proxy) rose only about 4% from 2022 to 2025, while NI constraint went from 5.8% (2022) to 14.1% (2023, from July) and 26.4% (2024). The change is not explained by new connections. Outage or transfer-limit data from SONI is needed to confirm the cause.

### #5, #8, #9 Interconnectors, firm capacity and imports
- Interconnectors to GB/France now enter the 15-minute dispatch. Capacity: existing 1,450 MW, Celtic 700 MW from April 2028, MaresConnect 750 MW from January 2031 (SEAI NEP26), credited for the fraction of the year in service.
- Exports absorb surplus wind/solar after battery charging, up to capacity x `ic_export_availability`. Exports enter the SNSP denominator and the min-gen ceiling, so the extra wind/solar dispatched is L(D+C+E) − L(D+C). When SNSP binds, (1 − SNSP) of the export flow is synchronous generation; it is reported (`Export_Synchronous_TWh`) and counted as firm generation.
- Imports cover the residual after wind, solar and batteries, before firm plant, up to capacity x `ic_import_availability` and within SNSP/min-gen headroom (HVDC imports are non-synchronous).
- Firm capacity required = peak 15-minute firm residual (before imports) + largest single infeed (500 MW, or 700/750 MW once Celtic/Mares are in service) − `ic_capacity_credit` x interconnector capacity. The old 0.9 x average demand / 0.68 is kept as `Firm_Capacity_Legacy_Formula_GW`; the 99.9th percentile residual is reported beside the maximum.
- Daily Dunkelflaute chart uses the new firm capacity figure.
- Interconnectors run from 2026, including the 2026 calibration run. Exports now absorb some curtailment the model previously attributed to SNSP, so the fixed 'other' curtailment residual rises from 3.4% to 4.6%.
- PLACEHOLDERS: export availability 0.5, import availability 0.7, capacity credit 0.5. As a check, the model gives 6.8 TWh of all-island imports in 2026; CSO reports IE net imports of 6.1 TWh in 2025 (17% of supply). Not a like-for-like comparison (IE only, net).

### #7 Energy accounting (point 3)
- Transition shares follow the EU RED gross final consumption basis: electricity counted as consumed, heat and transport fuel as final fuel, heat-pump ambient heat as renewable. The fixed 4% import share is gone; imports come from the dispatch. The three shares (fossil, renewable, imported) sum to 100% of energy consumed in Ireland.
- `RES_Overall_RED_%` and `RES_E_RED_%` follow RED Article 7 (domestic renewable generation including exports, over gross final consumption) for comparison with SEAI.
- Scope limits: firm generation is treated as fossil; bioenergy, hydro, waste and biofuels are not modelled, so the renewable share is a lower bound against SEAI's published 17.1% RES (2025, IE only).
- New check: renewable + firm + imports must equal electricity demand each year.

### #10 Input data
- Rows with the same project name in different ECP batches (Ballyroe Solar 120 MW in ECP-2.2 and 7 MW in ECP-GSS1) are kept as separate increments and no longer warned about. Only rows repeating name, technology and batch are flagged.
- Battery MWh: the published list masks project MWh; EirGrid's sheet total (15,217.75 MWh for 5,632 MW, 2.70 h) is used. Dispatch uses the fleet total, so the per-project split only affects zonal reporting. The check is now a PASS with this note.

### Decisions of 24 October 2026 (Niall)
- Interconnector export availability 0.5, import availability 0.7 and capacity credit 0.5 agreed (no longer placeholders). Reserve = largest single infeed + 0.5 GW operating reserve (`OPERATING_RESERVE_MW`); column renamed `Firm_Reserve_GW`.
- E, F, G: battery energy added after the pipeline = power x 2.70 h (EirGrid ECP pipeline average), was 0 MWh.
- Heat and transport totals in the code aligned with the Demand Calculator: 70.6 and 76 TWh (were 62 and 75.5). COP stays 3.5; background growth stays 0.8 TWh/yr.
- Headroom growth stays compound %/yr. North–South interconnector added to A, C, D, E, F, G as `reinforcement_steps = NI:2032:950` (300 → 1,250 MW, October 2031, SEAI NEP26).
- NI calibration stays on 2025.
- Weather years extended to 2014–2026: installed wind 2014–2018 added from the EirGrid/SONI 2025 report Table 1. Year-end capacity is used to normalise availability, so CF is biased low in fast-growth years (2016–2018).
- NI must-run units 3 → 2 in all scenarios: SONI made this standing policy in April 2026 (*Northern Ireland Dispatch Down Action Plan*, August 2026, p. 13: minimum conventional generation 389 → 323 MW).
- Dispatch fix: wind/solar serving native demand is capped at that demand (charging was counted as demand in the SNSP/MUON ceiling, which let direct supply exceed demand; C's supply check showed a 1.04% gap).
- Added heat-pump demand can follow hourly temperature: `TEMPERATURE_FILE` (Met Éireann hourly, Dublin Airport 532). Weight = heating degree hours (base 15.5 °C) / COP(T), COP falling 2.5% per K below its heating-weighted mean. Without the file, or for weather years it doesn't cover, the demand shape is used.

### NI constraint drivers: Moyle imports and transmission outages (`analysis/ni_constraint_drivers.py`)
- Data added in `Data_inputs/ni_drivers/`: NESO historic demand data 2024 (`MOYLE_FLOW`), SONI system data quarter-hourly 2026 (Moyle, North–South flow, NI demand), SONI transmission outage plans 2024–2026, SONI System and Renewable Data Summary Report, and the 2026 committed generator outage programme.
- **Moyle.** In 2024 Moyle imported into NI in 87% of hours (mean 284 MW). Within the same NI wind band, constraint is far higher when NI imports: in the windiest quarter of hours, 17.7% when exporting against about 49–50% when importing over 200 MW. A regression of hourly constrained MW on NI wind availability, NI demand, Moyle import and month gives 0.33 MW more constraint per MW imported in 2024 and 0.26 in January–July 2026 (day-clustered standard errors about 0.02). With imports set to zero, the fitted model's constraint falls by about 46% (2024) and 36% (2026). This is an association: flows follow GB and SEM prices, and must-run decisions and outages are not in the data, so it is an upper-end indication, not a causal estimate.
- **Planned 275 kV circuit outages.** Days with a planned 275 kV circuit outage show no higher NI constraint than other days in the same wind band (2024: 25.5% vs 27.1%; 2025: 17.8% vs 19.5%; 2026: 20.0% vs 19.5%). Individual north-west corridor outages coincide with spikes (Coolkeeragh–Magherafelt A, July 2024, 46% constraint; Magherafelt–Tamnamore B, August 2024, 46%), about 10–25 GWh each. The plans are planned dates, not as-run.
- **Reading together with the EirGrid/SONI reports:** planned network outages explain little of the annual change; the import pattern and the conventional units' running (must-run CCGT in 2024, unplanned outage in 2025) fit the data better. Generator running data (as-run unit commitment) would be needed to separate imports from must-run.
- NI installed wind before 2024 is an estimate: SONI notes that most NI DSO connection dates before 2024 are not available (Wind Installed Capacities table).

### Temperature-shaped heat-pump demand (24 October 2026)
- Met Éireann hourly data for Dublin Airport (station 532), 2014–2025, added as `Data_inputs/met_eireann_hly532_dublin_airport.csv`. Added heat-pump demand now follows heating degree hours (base 15.5 °C) divided by a temperature-dependent COP, instead of today's demand shape. Weather year 2026 is not covered and keeps the demand shape.
- Peak firm residual in 2050: A 12.26 → 13.01 GW, B 18.05 → 22.38 GW, C 11.98 → 12.63 GW; D unchanged (no added heat demand). Firm generation rises by 0.2–2.0 TWh.
- Firm capacity required in 2050 (peak residual + largest infeed + 0.5 GW operating reserve): A 14.3, B 23.6, C 13.9, D 11.8, E 14.2, F 14.1, G 14.3 GW.
- The operating-reserve commit missed the PR #11 merge and is included here.

### Firm capacity follow-up (Cian's review)
- The 2026 firm requirement was too low (6.44 GW). The 2026 row used 2026 weather only, so it missed the 8–9 January 2025 cold, calm peak (7.49 GW demand with 0.2–0.8 GW of wind). Firm peaks are now taken over every weather year for every year, including 2026.
- The interconnector credit no longer reduces the headline figure. `Firm_Capacity_Required_GW` = peak residual + largest single infeed. The figure net of the de-rated credit is `Firm_Capacity_Net_of_IC_Credit_GW`.
- 2026 is now 8.02 GW (7.52 peak residual + 0.50 reserve), matching Cian's estimate of about 8 GW. 2050: A 12.97, B 18.74, C 12.69 GW.
- No load factor enters the new figure; the 0.68 load factor is only in the legacy comparison column.
- Not yet fixed: added heat-pump and EV demand is spread in proportion to the historical demand shape, so its cold-weather peak is understated. This matters most for B. A temperature-driven profile is needed.

### NI constraint: sources and calibration (issue #3)
- Official NI wind figures (EirGrid/SONI Annual Renewable Constraint and Curtailment Report 2025, Table 3): constraint 5.8% (2022), 14.1% (2023), 26.4% (2024), 18.6% (2025); curtailment 3.6, 4.5, 3.2, 3.3%. The model's NI dispatch-down input reproduces these constraint figures to 0.1 point.
- Stated causes: 2024 report (p. 14): summer transmission outages, a large CCGT made must-run in a high-wind region after coal closure and delayed replacement units, higher GB imports even at high island wind, and constraints during testing of two new OCGTs. 2025 report (pp. 4, 15): the fall was primarily driven by a long unplanned outage of a large conventional generator; NI transmission outages in 2025 were normal.
- NI installed wind in `Input - capacity, constraints, curtailment.xlsx` corrected to the report's Table 1 (2019 1,276.3; 2020 1,276.3; 2021 1,350.6; 2022 1,350.6; 2023 1,364.3; 2024 1,387.0; 2025 1,392.5 MW). It previously showed 1,392.5 MW from 2020. Effect on results is under 0.2 points.
- New setting `NI_CALIBRATION_YEARS` (default `[2025]`). Pooling 2024 and 2025 raises modelled NI constraint from 21.7% to 25.5% in 2026 and from 27.0% to 31.0% in 2050 (A); all-island constraint rises by 0.5–0.9 points. The 2026 data so far (19.7% for January to September) sit closer to the 2025 calibration, so the default is unchanged. Revisit if the conventional unit returns to service.

### Weather years and dunkelflaute (`analysis/weather_dunkelflaute.py`)
- The model's weather years are 2019–2025 plus 2026 (January–September actual, October–December filled from the 2025 shape). 2014–2018 demand and wind are in the input file but unused, because installed capacity is only given from 2019.
- Against DNV's Ireland wind index (annual mean wind speed, % of the 1996-to-prior-year average): 2021 93.6, 2022 97.9, 2023 99.2, 2024 99.1, 2025 97.2. DNV gives no Irish figure for 2019 or 2020 (UK: 98.4 and 106.1). The set is slightly less windy than the long-term average, with 2021 among the three calmest years since 1996. This is about 26–29 years of reference, not a 30-year normal.
- Outputs in `analysis/output/`: wind CF by year, dunkelflaute events (2+ days with daily mean wind CF below 10%) with the storage each would need, and storage for an all-renewable islanded system.

### Effect on 2050 results (run of 24 October 2026)
| Scenario | Constraint % (before → after) | Total dispatch-down % | Imports TWh | Firm capacity GW (legacy) | Renewables % (RED, consumed) |
|---|---|---|---|---|---|
| A.CurrentTrajectory | 32.8 → 16.1 | 36.3 → 21.9 | 10.3 | 11.5 (10.8) | 28.5 |
| B.AcceleratedNOCONSTRAINT | 0.0 → 0.0 | 48.8 → 40.2 | 3.4 | 17.3 (16.2) | 83.4 |
| C.EirgridAIRAA | 56.0 → 30.6 | 60.8 → 48.1 | 3.5 | 11.2 (10.8) | 35.8 |
| D.ActualBuild_NoTransition | 32.8 → 16.1 | 36.5 → 26.4 | 7.1 | 9.8 (9.3) | 20.2 |
| E.ECP_Normal | 38.6 → 25.4 | 42.6 → 32.4 | 9.2 | 11.5 (10.8) | 28.0 |
| F.ECP_Fast | 42.6 → 30.3 | 47.5 → 38.5 | 8.0 | 11.4 (10.8) | 29.1 |
| G.ECP_Slow | 34.0 → 23.5 | 37.7 → 29.0 | 10.9 | 11.6 (10.8) | 26.2 |

Most of the constraint fall is offshore leaving SE headroom (#1). In B, exports cut min-gen curtailment from 45.3% to 35.6% in 2050 (#5). Demand inputs also changed (background 0.5 → 0.8 TWh/yr; B, D re-split), so the columns are not a pure method comparison.

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
