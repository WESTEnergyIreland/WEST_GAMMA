# Changelog: SEM Wind Capacity & Loss Modelling Demonstrator

Handover record of changes to `DemonstratorV2.py` and its data builder `build_all_island_dd.py`.
The full methodology is in `Technical_Briefing_README.docx`.

## Offshore wind yield set to EirGrid's study profile: 11 November 2026

Correction to the model. Offshore availability used the onshore per-GW shape unscaled, so offshore wind ran at the onshore capacity factor (28% over the thirteen weather years). It now uses the same weather multiplied by a factor k and capped at installed capacity in each interval (the approach of the regulators' SEM PLEXOS model), with k = 1.242 solved so that offshore availability averages 40% in weather year 2020, the year of EirGrid's ECP constraint studies. EirGrid's vendor offshore profile implies about 40% that year (GSS-1 workbook, project extract of 25 October). Over all thirteen weather years offshore averages 35.1% against 28.3% onshore. `GAMMA_OFFSHORE_CF` sets the 2020 target (e.g. 0.45, the GCS planning value). The scaled shape keeps offshore fully correlated with onshore, which overstates coincident surplus.

All results rerun: main pathways (charts on), EirGrid validation and GSS-2 prediction (with sigma interval ends), published network path after 2035, interconnector sensitivity, grid reinforcement study (interconnectors off only; the 50%/70% interconnector variant is no longer in the paper), sensitivity study, a 45% offshore case, and a 2050 run for Figure 4 and S2. Not rerun: Section 6.3 60% cover and EirGrid-order constraint (Table S6), the 35% efficiency and COP 3.9 sentence in 7.2, Supplementary S5 to S8, Figure 5. GSS-2 prediction rows dated 11 November added to `analysis/gss2_prediction_2035.csv`; earlier rows kept.

| Result | Before | Now |
|---|---|---|
| GSS-1 validation, Gamma minus EirGrid total, 2030 Initial / 2030 + 2.6 GW offshore / 2035 (points) | -4.5 / -4.7 / -2.3 | -4.5 / -3.1 / -0.2 |
| Same at sigma interval ends, offshore cases | -4.1 to -5.1 / -1.3 to -3.2 | -2.6 to -3.5 / +0.8 to -0.9 |
| Gamma constraint / curtailment, offshore cases (%) | 11.8, 14.3 / 10.3, 11.8 | 11.2, 13.5 / 12.4, 14.8 |
| GSS-1 2035 with 40% cover, Gamma minus EirGrid (points) | -5.6 | -2.9 |
| GSS-2 prediction, published path, 100% ECP + 4.7 GW offshore (%) | 33.1 (32.0-34.5) | 34.9 (33.9-36.1) |
| Same, cover 40% (%) | 28.6 | 30.8 |
| GSS-2 100% ECP without offshore | 29.9 / 19.9 | unchanged |
| EirGrid_Extended dispatch down 2030 / 2035 / 2050 / 2100 (%) | 20.8 / 23.0 / 28.2 / 43.8 | 22.0 / 24.7 / 32.1 / 48.0 |
| Historical_Trend dispatch down 2035 / 2050 / 2100 (%) | 17.2 / 17.9 / 23.8 | 18.6 / 20.0 / 24.8 |
| Wind and solar share of demand, EirGrid_Extended 2030 / 2050 / 2100 (%) | 52.7 / 73.3 / 79.8 | 54.2 / 75.1 / 81.5 |
| Fossil share of primary energy, EirGrid_Extended 2035 / 2050 / 2100 (%) | 74.8 / 59.9 / 28.5 | 74.0 / 59.2 / 27.2 |
| Same, Historical_Trend 2050 / 2075 (%) | 70.3 / 60.4 | 69.8 / 59.9 |
| Firm capacity 2050 / 2100, EirGrid_Extended (GW) | 14.4 / 25.0 | 14.4 / 24.9 |
| Firm fleet efficiency / peaking share 2050 (%) | 48.1 / 32 | 46.5 / 41 |
| Worst gas day 2050, EirGrid_Extended / Historical_Trend (GWh/d) | 680 / 593 | 692 / 588 |
| First gas shortfall, no flows / 70% / 100%, EirGrid_Extended | 2031 / 2042 / 2046 | unchanged |
| Same, Historical_Trend | 2036 / 2050 / 2055 | 2037 / 2050 / 2056 |
| Electrolysis for firm plant on hydrogen vs all dispatched down, 2050 (TWh) | 42.3 vs 24.0 | 40.1 vs 29.4 |
| Published path after 2035, 2050: constraint / curtailment / total / fossil (%) | 19.6 / 14.9 / 34.5 / 62.8 | 18.2 / 18.9 / 37.1 / 61.6 |
| Fossil 2050 at IE headroom growth 0 / 1 / 2 / 4 / 7.3 %/yr, limits kept (%) | 63.1 / 62.5 / 62.1 / 61.3 / 60.6 | 61.9 / 61.4 / 61.0 / 60.4 / 59.8 |
| Marginal yield of next 10.5 GW / 10.5 GW after, 0%/yr (TWh/GW; fleet average) | 0.35 / 0.25 (1.14) | 0.33 / 0.23 (1.18) |
| Electrification +150% / build +150%, fossil 2050 (%) | 44.7 / 54.6 | 43.4 / 54.2 |
| Offshore 45% in 2020 instead of 40%: EirGrid_Extended 2050 dispatch down / fossil (%) | | 34.5 / 58.9 |

## Interconnector sensitivity to 2075; Figure 8 redrawn from it: 11 November 2026

No model change. `analysis/interconnector_sensitivity.py` now runs to 2075 and reports annual gas use and gas for power on the worst day. The 2035 and 2050 rows are unchanged from the entry below (checked: no difference in any column). `analysis/figure8_gas.py` now draws paper Figure 8 from these runs: solid line interconnectors at 70% of capacity, shading from no flows (dashed) to 100% (dotted). Its usage is now `python analysis/figure8_gas.py analysis/ic_run/scenario_outputs <out.png> [end year]`.

Historical_Trend at 100% first exceeds supply in 2055 (the run to 2050 reported "none by 2050").

| All-island, 0% / 70% / 100% of interconnector capacity | 2026 | 2035 | 2050 | 2075 |
|---|---|---|---|---|
| EirGrid_Extended, worst gas day (GWh/d) | 394 / 345 / 324 | 531 / 432 / 390 | 680 / 582 / 538 | 979 / 837 / 776 |
| Historical_Trend, worst gas day (GWh/d) | 394 / 345 / 324 | 489 / 391 / 349 | 593 / 494 / 452 | 771 / 672 / 630 |
| EirGrid_Extended, annual gas use (TWh GCV) | 70.2 / 56.8 / 52.1 | 61.9 / 42.9 / 37.1 | 47.8 / 39.3 / 36.1 | 42.9 / 36.1 / 33.4 |
| Historical_Trend, annual gas use (TWh GCV) | 70.2 / 56.8 / 52.1 | 63.0 / 41.4 / 35.3 | 57.5 / 42.0 / 36.7 | 58.3 / 45.2 / 40.3 |
| Gas supply (GWh/d) | 459 | 495 | 488 | 485 |

Check against Gas Networks Ireland's Network Development Plan 2025 (Best Estimate, Tables A2-2 and A2-8): annual demand 77.7 TWh in 2025/26 and 56.8 TWh in 2034/35, 1-in-50 peak day 469 GWh/d in 2034/35. For annual gas use the run with no flows is the nearer one (70.2 and 61.9 TWh); the 70% run is 27% below GNI in 2026. For the peak day in 2035 GNI lies between the no-flow and 70% runs. The 70% case is therefore used as the central case for the worst day only; annual gas use in the paper stays on the main runs. On Historical_Trend annual gas use stops falling in the late 2030s in every case.

## Interconnector sensitivity at 0%, 70% and 100%: 11 November 2026

No model change. New script `analysis/interconnector_sensitivity.py` runs EirGrid_Extended and Historical_Trend to 2050 with interconnector flows in the 15-minute dispatch (`GAMMA_IC_DISPATCH=1`) at 0%, 70% and 100% of interconnector capacity, the same share for imports and exports. It replaces the 50% export / 70% import pair quoted in paper Sections 7.3 and 7.5. Capacity is Gamma's: 1,450 MW existing, Celtic 700 MW from April 2028, MaresConnect 750 MW from 2031. Outputs in `analysis/output/interconnector_sensitivity.csv` and `.md`.

The 0% case has no flows and equals the main run (checked on EirGrid_Extended: no difference in any output column). 0% and 100% are bounds, not forecasts. Imported electricity is counted as non-fossil. Firm capacity is the same in every case (14.4 GW and 12.4 GW in 2050), because the main firm figure gives interconnectors no capacity credit.

| 2050, all-island | EirGrid_Extended 0% / 70% / 100% | Historical_Trend 0% / 70% / 100% |
|---|---|---|
| Fossil share of primary energy (%) | 59.9 / 59.4 / 59.1 | 70.3 / 68.9 / 68.3 |
| Dispatch down (% of available wind and solar) | 28.2 / 23.4 / 21.2 | 17.9 / 13.3 / 11.6 |
| Firm generation (TWh) | 14.2 / 11.3 / 10.0 | 19.3 / 12.3 / 9.7 |
| Imports / exports (TWh) | 0 / 0; 4.3 / 5.4; 5.8 / 7.5 | 0 / 0; 8.0 / 3.3; 10.7 / 4.4 |
| Worst gas day (GWh/d), supply 488 | 680 / 582 / 538 | 593 / 494 / 452 |
| First year the worst day exceeds supply | 2031 / 2042 / 2046 | 2036 / 2050 / none by 2050 |
| Days a year above supply | 7.6 / 1.5 / 0.7 | 2.5 / 0.1 / 0.0 |

Validation day (8 January 2025 weather, 2026 system; recorded 365.6 GWh/d): 393.9, 344.7 and 323.6 GWh/d at 0%, 70% and 100%.

## Constraint closed form corrected; model equations written out: 8 November 2026

Correction to the model. `expected_constraint_mw` (and equation 3 of the paper) did not compute the expectation it is defined as, E[max(0, x - H*eta)] with ln(eta) ~ N(0, sigma^2). It used x*Phi(a + sigma/2) - H*exp(sigma^2/2)*Phi(a - sigma/2), a = ln(x/H)/sigma, which is not the expectation of any lognormal and went negative for x below about 0.3-0.4 H (clipped to zero). The correct form is x*Phi(a) - H*exp(sigma^2/2)*Phi(a - sigma); its derivation is in `docs/model_equations.md`. `tests/test_constraint_closed_form.py` checks it against Monte Carlo. Every limit and spread is refitted; the estimator is unchanged (annual constrained energy matched exactly, sigma by least squares on hourly records).

- The corrected form fits the hourly records better: RMSE 140.7 against 147.4 MW (IE, 2024-2026) and 103.3 against 107.6 MW (NI).
- The records identify sigma only weakly: hourly RMSE changes by under 2% for IE sigma between 1.2 and 2.5 while the median limit goes from 8,300 to 50,000 MW. `analysis/sigma_identification.py` profiles the error and block-bootstraps calendar months (100 samples): 90% interval IE 0.95-1.38, NI 1.57-2.27 (`analysis/output/sigma_profile.csv`, `sigma_bootstrap.csv`). `GAMMA_SIGMA_IE` / `GAMMA_SIGMA_NI` fix sigma for a run; headrooms are then recalibrated.
- H is a median of a wider distribution, so the MW values are not comparable with earlier ones (IE zones sum 11,229 MW in 2026, was 5,121).
- Using expected rather than realised constraint understates dispatch down (Jensen; convex in constraint): about 1.5 points of available energy on the 2024-2025 records. In 2026 this is absorbed in the residual; documented, not modelled.
- `analysis/headroom_history.py` now holds sigma at the new fits (1.17 IE, 1.89 NI).
- GSS-2 prediction: rows dated 8 November added to `analysis/gss2_prediction_2035.csv`, with the sigma interval; the 7 November rows stay as registered.

| Result | Before | Now |
|---|---|---|
| Fitted sigma, 2024-2026, IE / NI | 0.88 / 1.13 | 1.17 / 1.89 |
| Jurisdiction limit L, 2024-2026, IE / NI (MW) | 4,456 / 506 | 7,982 / 1,115 |
| Rolling hindcast mean absolute error, IE / NI / all-island (%) | 11.2 / 29.7 / 10.9 | 11.8 / 33.0 / 10.3 |
| Fixed-limit backcast, IE 2021-2023, largest error (points) | 0.6 | 1.5 |
| 2026 modelled SNSP curtailment / residual kappa, wind (% of available; recorded SNSP 1.37) | 1.30 / 3.60 | 2.23 / 2.67 |
| GSS-1 validation, Gamma minus EirGrid total, 2030 Initial / 2030 + 2.6 GW offshore / 2035 (points) | -2.9 / -3.2 / +0.9 | -4.5 / -4.7 / -2.3 |
| Same at sigma 90% interval ends (low / high) | | -3.9 to -4.9 / -4.1 to -5.1 / -1.3 to -3.2 |
| Gamma constraint, same cases (%) | 10.5 / 15.0 / 19.0 | 9.4 / 11.8 / 14.3 |
| GSS-2 prediction, published path, 100% ECP (%) | 38.0 | 29.9 (sigma interval 27.5-33.1) |
| Same, 100% ECP + 4.7 GW offshore (%) | 36.9 | 33.1 (32.0-34.5) |
| GSS-2, cover 40%, 100% ECP / with offshore (%) | 19.5 / 29.1 | 19.9 / 28.6 |
| EirGrid_Extended dispatch down 2026 / 2030 / 2035 / 2050 / 2100 (%) | 15.7 / 22.4 / 25.2 / 28.8 / 44.2 | 15.2 / 20.8 / 23.0 / 28.2 / 43.8 |
| EirGrid_Extended constraint 2035 (%) | 17.2 | 14.2 |
| Wind and solar share of electricity demand 2030 / 2050 / 2100 (%) | 51.7 / 72.6 / 79.1 | 52.7 / 73.3 / 79.8 |
| Fossil share of primary energy, EirGrid_Extended 2035 / 2050 / 2100 (%) | 75.4 / 60.2 / 29.4 | 74.8 / 59.9 / 28.5 |
| Same, Historical_Trend 2050 / 2075 / 2100 (%) | 70.5 / 60.7 / 52.4 | 70.3 / 60.4 / 52.0 |
| Electricity for firm plant on hydrogen vs dispatched down, 2050 (TWh) | 43.7 vs 24.5 | 42.3 vs 24.0 |
| Firm capacity 2035 / 2050 / 2100 (GW) | 11.2 / 14.4 / 25.0 | unchanged |
| Worst gas day 2050 (GWh/d); first year above supply | 680; 2031 | 681; 2031 |
| Published network path after 2035, EirGrid_Extended 2050: constraint / curtailment / total dispatch down / fossil share (%) | 25.0 / 12.2 / 37.2 / 64.2 | 19.6 / 14.9 / 34.5 / 62.8 |
| Same, delivered solar / wind 2050 (TWh), against no limits | 9.8 / 40.3 against 14.4 / 39.3 | 11.5 / 40.3 against 14.5 / 39.8 |
| Interconnector flows: validation day / worst-day rise 2026-2050, EirGrid_Extended / Historical_Trend / first year short | 344.1 GWh; 69% / 44%; 2042 / 2050 | 344.7 GWh; 69% / 43%; 2042 / 2050 |
| Cover share that reproduces EirGrid's constraint (Gamma order) | 40% | 60% (RMS 0.42 points) |
| Cover 40%: Ireland constraint / total, 2030 and 2035 (%) | 6.3 / 19.2 and 6.0 / 23.5 | 7.4 / 20.0 and 7.5 / 22.9 |
| Grid study, fossil share 2050 at 0 / 1 / 2 / 4 / 7.3% a year headroom growth (%) | 64.6 / 63.8 / 63.1 / 62.0 / 60.9 | 63.1 / 62.5 / 62.1 / 61.3 / 60.6 |
| Grid study, constraint / curtailment 2050 at 0% and 7.3% (%) | 27.1 / 11.0 and 5.9 / 24.6 | 21.2 / 13.9 and 6.0 / 23.9 |
| Sensitivity study, fossil share 2050, electrification +50 / +100 / +150% | 55.6 / 50.5 / 45.1 | 55.2 / 50.1 / 44.7 |
| Same, build +50 / +100 / +150% | 58.2 / 56.2 / 55.0 | 57.8 / 55.8 / 54.6 |
| Same, 2100: electrification / build +150% | 18.7 / 21.5 | 17.7 / 20.5 |
| Firm plant all at 35% efficiency; heat-pump COP 3.9: change in fossil share 2050 and 2100 (points) | +1.5 to +4.0; -0.8 to -2.2 | +1.4 to +4.0; -0.8 to -2.3 |
| Historical_Trend on the slow operating rules: largest change in dispatch down / fossil share (points) | 1.4 / 0.3 | 1.2 (2035) / 0.2 |

Figures 5, 6 and 8 and the two sensitivity charts are redrawn from these outputs.

## EirGrid paths use AIRAA's median demand: 7 November 2026

Correction to inputs. The EirGrid paths (`eirgrid_gss1_path`, `eirgrid_gss1_initial_2030`, `eirgrid_gss2_fg_100ecp*`) took Ireland's demand as 40.0 TWh in 2030 and 44.3 TWh in 2035 with Northern Ireland held at 7.1 TWh. 40.0 TWh is AIRAA 2026–2035's Low case for 2030; the median is 44.6 TWh (2030) and 49.2 TWh (2035) TER for Ireland and 9.2 and 10.7 TWh for Northern Ireland (`Data_inputs/AIRAA-2026-2035_DataWorkbook.xlsx`, now in the repository). TER is converted to Gamma's recorded-demand basis by the 2024 ratio of recorded demand to TER (Ireland 33.72/35.20, Northern Ireland 7.22/8.16), giving 50.8 TWh all-island in 2030 and 56.6 TWh in 2035 (was 47.1 and 51.4). Post-2035 growth on the EirGrid rows is now the 2030–2035 change divided by five, 1.16 TWh a year (background 0.71, heat 0.15, transport 0.30; was 0.86). Historical_Trend is unchanged.

Also: `analysis/cover_recalibration.py` sets `run = yes` on its rows (it ran no scenarios after PR #40). The GSS-2 prediction gains rows dated 7 November 2026; earlier rows are kept.

| Result | Before | Now |
|---|---|---|
| Validation, Gamma minus EirGrid total (points): 2030 Initial / 2030 + 2.6 GW offshore / 2035 | −2.6 / −0.8 / +4.1 | −2.9 / −3.2 / +0.9 |
| Surplus in EirGrid's order, before the network (%) | 2.3 / 14.6 / 23.2 | 1.5 / 11.6 / 18.9 |
| Constraint in EirGrid's order, published path, 2030 / 2035 (%) | 5.0 / 5.6 | 6.4 / 6.7 |
| GSS-2 prediction, published path / cover 40%, 100% ECP (%) | 38.4 / 22.6 | 38.0 / 19.5 |
| Same, 100% ECP + 4.7 GW offshore (%) | 40.0 / 33.0 | 36.9 / 29.1 |
| EirGrid_Extended demand 2035 / 2050 / 2100 (TWh) | 51.4 / 64.3 / 104.1 | 56.6 / 74.0 / 128.8 |
| Dispatch down 2030 / 2035 / 2050 / 2100 (% of available) | 24.5 / 27.7 / 35.2 / 53.9 | 22.4 / 25.2 / 28.8 / 44.2 |
| Fossil share of primary energy 2035 / 2050 / 2100 (%) | 75.0 / 60.9 / 27.4 | 75.3 / 60.2 / 29.4 |
| Firm capacity 2035 / 2050 / 2100 (GW) | 10.2 / 12.7 / 20.7 | 11.2 / 14.4 / 25.0 |
| Electricity for firm plant on hydrogen vs dispatched down, 2050 (TWh) | 35.4 vs 29.9 | 43.7 vs 24.5 |
| Worst gas day 2050 (GWh/d); first year above supply, worst / second-worst / median weather year | 648; 2036 / 2036 / 2040 | 680; 2031 / 2032 / 2035 |
| Same with interconnector flows: first year above supply | 2047 | 2042 |
| Fossil share 2050 with the published network path after 2035 (%) | 63.5 | 64.2 |

The sensitivity study (Supplementary S7) was rerun on this model; the 16.5 GW step in 2100 firm capacity with build +150% noted in the entry below no longer appears (23.8 GW, against 24.3 GW at +100%).

## Sensitivity study rerun on current main: 7 November 2026

No model change. `python analysis/sensitivity_study.py` rerun on `main` (bdac59b), so the base case now matches EirGrid_Extended in the paper (PRs #25, #30 and #37 included). Outputs in `analysis/output/sensitivity/`. Supplementary Section S7, Tables S9 to S12.

| EirGrid_Extended, fossil share of primary energy (%) | Before (30 Oct) | Now |
|---|---|---|
| Base, 2050 / 2100 | 66.3 / 34.4 | 60.9 / 27.4 |
| Heat and transport electrification +50 / +100 / +150%, 2050 | 62.3 / 57.9 / 53.3 | 55.5 / 49.8 / 43.6 |
| Same, 2100 | 25.1 / 21.4 / 20.8 | 18.5 / 14.6 / 14.2 |
| Wind, solar and battery build +50 / +100 / +150%, 2050 | 64.2 / 62.6 / 61.5 | 58.8 / 57.4 / 56.7 |
| Same, 2100 | 29.0 / 26.4 / 25.2 | 24.5 / 23.2 / 22.6 |

Constraint is now zero in 2050 and 2100 (no zonal limits from 2036), so the extra build shows up as curtailment: 35.2% of available output in the base case and 57.6% with build +150% in 2050. Firm capacity in 2100 with build +150% is 16.5 GW, against 20.0 GW at +100% and 20.7 GW in the base case; the cause of that step has not been checked.

## Gas: annual use against the worst day, and an interconnector sensitivity: 7 November 2026

No change to the main runs. New script `analysis/figure8_gas.py` draws paper Figure 8 (annual gas use; worst gas day against supply) from the main outputs and from a run with `GAMMA_IC_DISPATCH=1`. Paper Section 7.5.

| | EirGrid_Extended | Historical_Trend |
|---|---|---|
| Annual gas use, TWh GCV, 2026 / 2050, main runs | 70.0 / 41.3 | 70.0 / 57.5 |
| Worst gas day, GWh/d, 2026 / 2050, main runs | 393 / 648 | 393 / 593 |
| First year the worst day exceeds supply: worst / second-worst / median weather year | 2036 / 2036 / 2040 | 2036 / 2037 / 2042 |
| Same, with 25 / 50 GWh/d of extra entry capacity (worst weather year) | 2039 / 2042 | 2040 / 2043 |
| With interconnector flows (imports 70% of capacity): worst day 2026 / 2050, GWh/d | 344 / 511 | 344 / 494 |
| With interconnector flows: first year short, days short a year in 2050 | 2047, 0.3 | 2050, 0.1 |

Validation day (8 January 2025 weather, 2026 system; recorded 365.6 GWh/d): 393.4 GWh/d without interconnector flows, 344.1 with them.

## Grid reinforcement study rerun on current main: 6 November 2026

`analysis/output/grid_reinforcement/grid_reinforcement_results.csv` rerun after PRs #33 to #42 (zonal limits kept after 2035; see PR #42). Paper Section 7.3.

| EirGrid_Extended 2050 | Before (1 Nov) | Now |
|---|---|---|
| Fossil share of primary energy, IE headroom 0 / 1 / 2 / 4 / 7.3% a year | 66.6 / 66.0 / 65.6 / 64.8 / 64.2 | 63.9 / 63.3 / 62.7 / 61.9 / 61.2 |
| Same with interconnector flows in the dispatch | 65.1 to 63.6 | 62.3 to 60.6 |
| No zonal limits from 2036 | 63.8 | 60.9 |
| Published path after 2035 | 66.3 | 63.5 |
| Firm generation, TWh, 0% / 7.3% / no limits | 16.5 / 12.3 / 11.6 | 15.8 / 11.3 / 10.4 |
| Marginal yield of the next 10.5 GW and the 10.5 GW after, TWh/GW, 0% (7.3%) | 0.27, 0.20 (0.22, 0.16) | 0.35, 0.24 (0.28, 0.16) |
| Average yield of the 2050 fleet, TWh/GW, 0% | 1.01 | 1.09 |

Sensitivities (fossil share of primary energy, change from the central run, 2050 and 2100): all firm plant at 35% efficiency +1.0 to +4.0 points (was +1.6 to +3.7); heat-pump COP 3.9 -0.8 to -2.7 points (was -0.7 to -2.6).

## Evaluation chart joins the record; grid study updated for the no-limits pathways: 6 November 2026

No result changes.
- `evaluation_curtailment_cf.png` (Cian, 4 Nov): each forecast line now starts from the last full recorded year, so it joins the black line; the part-year record (2026, January to August) is shown as an open marker and not joined, because it is seasonally biased. The 2026 forecast point still differs from the record: it is one weather year on the assumed year-end fleet (6.6 GW wind), where the record is part-year on the connected fleet.
- `analysis/grid_reinforcement_study.py`: runs now keep the zonal limits after 2035 (`reinforcement_steps = NI:2032:950`), since EirGrid_Extended and Historical_Trend remove them from 2036 (PR #30) and the study tests headroom growth; reads `Primary_Fossil_Share_Pct` (renamed in PR #37); sets `run = yes` on its rows (PR #40).

## Gas supply from GNI's Network Development Plan 2025: 6 November 2026

From Mark's review of the gas check (4 November). Gas supply only; no other result changes.
- **Moffat:** 433.3 GWh/d (2025/26), 450 (2026/27), 475 from 2027/28 with the committed Scottish compressor upgrades (NDP 2025, Table A2-13). The EMD compressors at Beattock and Brighouse Bay are not committed and are left out.
- **Corrib:** NDP 2025 Table 7-1, 25.7 GWh/d (2025/26) to 9.8 (2034/35), then falling at the 2033/34 to 2034/35 rate. Replaces the 15.6%/yr placeholder.
- **Biomethane:** NDP 2025 Table 7-2, Low scenario, 0.1 to 3.6 TWh a year by 2034/35, injected evenly, then held.
- **Not included:** the State strategic gas emergency reserve (floating LNG, for supply disruption only), any shortage of supply from Great Britain, linepack, distillate at gas plant.
- A winter in calendar year Y uses gas year (Y-1)/Y.

| Result (GWh/d, GCV) | 4 Nov | 6 Nov |
|---|---|---|
| Supply 2026 / 2035 / 2050 | 457.8 / 438.8 / 433.8 | 459.3 / 494.7 / 487.9 |
| First year with a day above supply, both pathways | 2030 | 2036 |
| Days above supply per year, EirGrid_Extended 2035 / 2050 / 2100 | 1.4 / 8.9 / 9.9 | 0 / 5.4 / 8.2 |
| Same, Historical_Trend 2035 / 2050 / 2100 | 1.2 / 8.0 / 30.2 | 0 / 2.5 / 22.9 |
| Worst day / supply 2050, EirGrid_Extended and Historical_Trend | 1.49 and 1.37 | 1.33 and 1.21 |

Worst days are unchanged (393 in 2026; 648 and 593 in 2050). In 2035 the worst day is within 1% of supply on both pathways.

## How to run

1. Install Python 3.10 or later, then from the repository folder: `pip install -r requirements.txt`.
2. Inputs live in `Data_inputs/`. Edit scenarios in `Data_inputs/scenariosXLSX.xlsx` (sheet `Scenarios`) and save.
3. Run `python Gamma.py` (or `python Gamma.py <scenario>` for one). All scenarios run without prompts (about 25 minutes with charts; the runs to 2100 take longest). Outputs go to `scenario_outputs/`: one folder per scenario, `scenario_summary.csv`, `all_scenarios_evaluation_curtailment_cf.csv` (curtailment and capacity factors, with actuals), `evaluation_curtailment_cf.png`, `validation_report.csv` and `run_log.txt`. Set `SCENARIO_CHARTS = False` near the top of `Gamma.py` for a faster CSV-only run.
4. Validation against EirGrid: `python analysis/eirgrid_validation.py` (after step 3). Paper figures: `python analysis/figure6_projections.py <outputs, no limits> <outputs, published path> fig6.png [end year]` and `python analysis/figure7_showcase.py <outputs> fig7.png [end year] [day year]` (Figure 7 needs a run with charts on; a run to 2035 gives 2033 daily panels), `python analysis/figure8_gas.py <outputs> <outputs with GAMMA_IC_DISPATCH=1, or -> fig8.png [end year]`. Optional analyses: `python analysis/weather_dunkelflaute.py` and `python analysis/ni_constraint_drivers.py`. Outputs in `analysis/output/`.
5. To rebuild the hourly dispatch-down files from new EirGrid/SONI `DD-HH-<year>.xlsx` workbooks, use `build_all_island_dd.py` (not in this repository yet).

## Scenario on/off switch and clearer network field guide: 4 November 2026

From Cian's comment on the paper. No result changes.
- **`run` column** in `Data_inputs/scenariosXLSX.xlsx` (sheet `Scenarios`, last column). `no` leaves a scenario out of `python Gamma.py` but keeps it in the workbook; `python Gamma.py <scenario>` still runs it. Only EirGrid_Extended and Historical_Trend are set to `yes`. Run the validation scenarios by name before `analysis/eirgrid_validation.py`.
- **Field Guide** rows for `headroom_curve`, `headroom_scale`, `ie/ni_reinforcement_pct`, `reinforcement_steps` and `headroom_pipeline_cover_pct` now say what each does, when it is used and the value in each pathway, including the 2036 no-limits steps.

## Gas supply check against Moffat and Corrib: 4 November 2026

Reworks PR #38. New outputs only; no existing result changes. Gamma now tests daily gas demand against daily entry capacity for every scenario year and weather year.
- **Test.** Daily gas energy (GWh/d, gross calorific value) against Moffat (433.4 GWh/d) plus Corrib (24.4 GWh/d in 2026, falling 15.6% a year). PR #38 compared the 15-minute peak with Moffat's daily capacity divided by 24; Moffat's capacity is a daily figure and linepack is not modelled, so the daily test is the defensible one.
- **Power gas.** Firm output less 400 MW of hydro, biomass and waste, split at the 1,500-hour band into CCGT (55%) and peaking (38%) output, both LHV, converted to GCV at 0.90. Moneypoint on oil covers up to 855 MW of the peaking tranche to the end of 2029. PR #38 used a flat 50% on all firm output, LHV against a GCV capacity.
- **Non-power gas.** All-island, 37.6 + 6.51 x heating degree days (Dublin Airport daily mean, base 15.5 °C) GWh/d, fitted to IE non-power demand in Q1 2025 (CSO) and on 8 January 2025 (GNI) and scaled for NI distribution demand (GMO NI). It is scaled down in line with heat electrification, so heat is not counted twice. Isle of Man 5 GWh/d. Weather year 2026 has no temperature record and uses the 2014–2025 mean for each calendar day.
- **Check.** 2026 system on 8 January 2025 weather: 393.4 GWh/d modelled against 365.6 observed (+7.6%); power 233.5 against 205.3. Two reasons the model is high: interconnector imports are zero in the main runs, and Moneypoint ran on coal that day.
- **Fixes to PR #38.** Unused `check_gas_capacity()` and duplicate firm series removed; 2026 uses all weather years, as the firm capacity does; 29 February dropped from the envelope (it caused the dips every fourth year); console output through `say()`.
- **Outputs.** `Gas_*` columns in `forecast_results.csv`; `gas_daily_by_weather_year.csv`, `gas_daily_demand_envelope.csv`, `gas_validation_2026.csv` and `gas_daily_demand.png` in each scenario folder.
- **Moneypoint matters.** The worst day rises by about 60 GWh/d between 2029 and 2030 on both pathways because Moneypoint's oil duty ends; the first shortfall year moves with that date.
- Placeholders for group agreement: Corrib decline, non-gas firm MW, Moneypoint end date, Isle of Man. Open questions are in the WEST project note `claude/gas-supply-research-brief.md`.

| Result (all-island, GWh/d GCV) | PR #38 (peak GW basis) | New |
|---|---|---|
| Daily capacity 2026 / 2050 | 433.4 (18.06 GW) flat | 457.8 / 433.8 |
| EirGrid_Extended worst day 2026 / 2030 / 2035 / 2050 / 2100 | peak 20 / 21 / 23 / 28 / 45 GW | 393.4 / 460.9 / 491.1 / 648.1 / 960.1 |
| Historical_Trend worst day 2026 / 2030 / 2035 / 2050 / 2100 | not run | 393.4 / 466.7 / 488.7 / 592.7 / 948.8 |
| First year with a day above capacity, both pathways | 2026 | 2030 |
| Days above capacity per year, mean of 13 weather years, EirGrid_Extended 2035 / 2050 / 2100 | | 1.4 / 8.9 / 9.9 |
| Same, Historical_Trend 2035 / 2050 / 2100 | | 1.2 / 8.0 / 30.2 |

## Transport ceiling, battery duration, share names and Figure 7: 2 November 2026

Group decisions from the Phase 1 paper comments (Cian, Niall).
- **Transport ceiling.** `ALL_ISLAND_TRANSPORT_DEMAND_TWH` 76.0 → 62.2 TWh: land transport only, IE 46.5 TWh (SEAI, excluding aviation and navigation) plus NI 15.7 TWh (DESNZ road), as derived in the paper. The ceiling on transport electricity falls from 25.3 to 20.7 TWh. The remaining transport fuel also falls by 13.8 TWh in every year, so the fossil share of primary energy falls from 2026 on, in every scenario. Dispatch is unaffected until the ceiling binds (EirGrid_Extended from 2090; never on Historical_Trend).
- **Battery duration.** New scenario inputs `battery_hours_target` and `battery_hours_target_year` (blank = off). With them set, the MW build is unchanged and fleet MWh is raised so the average duration rises linearly from its 2026 value (1.6 h) to the target, then holds. EirGrid_Extended and Historical_Trend use 4 h by 2035. The EirGrid validation runs, the sensitivities and the GSS-2 prediction keep EirGrid's own storage and are unchanged.
- **Share names.** Every output now also carries `Primary_Fossil_Share_Pct`, `Primary_Renewables_Share_Pct`, `Primary_Imported_Electricity_Share_Pct` (shares of primary energy), `Modelled_RES_Overall_Gross_Final_Pct` (share of gross final energy, the SEAI RES Overall basis), `Modelled_RES_E_Pct` and `Domestic_Final_Energy_*_Pct`. The old names (`Overall_*`, `RES_Overall_RED_%`, `RES_E_RED_%`, `Final_*`) are kept as aliases with the same values.
- **Figure 7.** Gamma writes the data behind the daily and monthly overview charts (`chart_Daily_*.csv`, `chart_monthly_overview.csv`). `analysis/figure7_showcase.py` draws the 2 x 2 figure: dunkelflaute day and windiest day on EirGrid_Extended, and the monthly overview of both pathways, with one legend and no data boxes.

| Result (all-island) | Old | New |
|---|---|---|
| Fossil share of primary energy 2026, all scenarios (%) | 86.69 | 86.01 |
| Modelled RES Overall (gross final) 2026 (%) | 10.86 | 11.74 |
| EirGrid_Extended battery fleet 2035 / 2050 (GWh) | 13.3 / 31.0 | 21.4 / 47.5 |
| Historical_Trend battery fleet 2035 / 2050 (GWh) | 3.9 / 7.6 | 8.5 / 16.0 |
| EirGrid_Extended dispatch down 2030 / 2035 / 2050 / 2100 (% of available) | 24.76 / 28.67 / 36.79 / 53.31 | 24.52 / 27.73 / 35.18 / 53.90 |
| Historical_Trend dispatch down 2030 / 2035 / 2050 / 2100 (%) | 16.38 / 18.68 / 20.79 / 28.09 | 16.21 / 17.68 / 18.63 / 24.34 |
| EirGrid_Extended wind and solar share of demand 2035 / 2050 / 2100 (%) | 63.33 / 75.35 / 81.63 | 63.39 / 75.40 / 82.01 |
| EirGrid_Extended firm generation 2035 / 2050 / 2100 (TWh) | 17.85 / 11.56 / 11.03 | 17.48 / 10.44 / 9.25 |
| Historical_Trend firm generation 2035 / 2050 / 2100 (TWh) | 21.39 / 20.59 / 28.76 | 21.10 / 19.67 / 25.64 |
| EirGrid_Extended demand 2100 (TWh) | 107.30 | 104.08 |
| EirGrid_Extended firm capacity needed 2100 (GW) | 21.26 | 20.70 |
| EirGrid_Extended fossil share 2035 / 2050 / 2075 / 2100 (%) | 76.71 / 63.84 / 47.32 / 30.57 | 75.04 / 60.89 / 42.15 / 27.43 |
| Historical_Trend fossil share 2035 / 2050 / 2075 / 2100 (%) | 80.09 / 72.68 / 63.96 / 56.59 | 78.78 / 70.50 / 60.68 / 52.40 |
| EirGrid_Extended modelled RES Overall 2035 / 2050 / 2075 (%) | 21.86 / 36.06 / 55.30 | 23.88 / 39.74 / 60.84 |
| Validation runs and GSS-2 prediction: dispatch down, firm capacity | | unchanged |

Findings:
- Longer batteries cut dispatch down by about 1 point by 2035 on both pathways and by 2.2 to 3.8 points on Historical_Trend after 2050. Firm capacity needed is unchanged up to 2075: a 4 h fleet does not cover a multi-day still, cold spell.
- Most of the fall in the fossil share comes from the smaller transport fuel total, not from the batteries. It is an accounting correction (aviation and shipping were never meant to be in the base).
- EirGrid_Extended dispatch down in 2100 rises slightly because the transport ceiling now binds and demand is 3.2 TWh lower.
- No published Irish projection of fleet-average battery duration has been found. The 4 h target rests on EirGrid's long-duration storage consultation (at least 4 h) and should be stated as an assumption.

## Firm fleet efficiency from a baseload and peaking split: 1 November 2026

The fixed firm plant efficiency (`FIRM_FUEL_EFFICIENCY = 0.50`) is replaced by a fleet efficiency that depends on how the firm plant runs. Proposed by Niall; values are placeholders for group agreement.
- Each weather year's 15-minute firm output is split by a screening-curve rule. Output at MW levels reached for at least `FIRM_PEAKER_MAX_HOURS` (1,500 h) a year is the baseload tranche at `FIRM_CCGT_EFFICIENCY` (55%). Output above that level is the peaking tranche at `FIRM_PEAKER_EFFICIENCY` (38%). All lower heating value.
- Fleet efficiency is the energy-weighted result. It falls as firm output moves from baseload to peaking duty. Part-load and start-up losses inside each tranche are not modelled.
- Firm plant on green hydrogen uses the same fleet efficiency (`H2_POWER_EFFICIENCY` removed). Electrolysis stays at 70%.
- New outputs: `Firm_Peaking_Share_%`, `Firm_Fleet_Efficiency_%`, `Firm_Gas_Burnt_TWh`.
- Only primary energy shares and the hydrogen figures change. Dispatch, dispatch down, firm generation and firm capacity are unchanged.

| Result (all-island) | Old | New |
|---|---|---|
| Firm fleet efficiency 2026 (%) | 50.0 | 54.1 |
| EirGrid_Extended fleet efficiency 2035 / 2050 / 2100 (%) | 50.0 / 50.0 / 50.0 | 52.6 / 45.8 / 40.2 |
| EirGrid_Extended peaking share of firm output 2035 / 2050 / 2100 (%) | n/a | 10.0 / 44.9 / 82.0 |
| Historical_Trend fleet efficiency 2035 / 2050 / 2100 (%) | 50.0 / 50.0 / 50.0 | 53.2 / 52.4 / 51.4 |
| Fossil share of primary energy 2026 (%) | 86.86 | 86.69 |
| EirGrid_Extended fossil share 2035 / 2050 / 2100 (%) | 76.88 / 63.48 / 28.62 | 76.71 / 63.84 / 30.57 |
| Historical_Trend fossil share 2035 / 2050 / 2100 (%) | 80.29 / 72.89 / 56.85 | 80.09 / 72.68 / 56.59 |
| EirGrid_Extended electricity for green hydrogen firm plant 2050 / 2100 (TWh) | 33.03 / 31.51 | 36.05 / 39.19 |
| Historical_Trend electricity for green hydrogen firm plant 2050 / 2100 (TWh) | 58.83 / 82.16 | 56.13 / 79.92 |

Findings:
- In 2026 the model gives 54.1%, above the old 50%. This should be checked against SEAI's reported efficiency for gas-fired generation before the values are agreed. If the actual fleet figure is lower, `FIRM_CCGT_EFFICIENCY` is the parameter to lower.
- On EirGrid_Extended the peaking share passes 40% by 2050. Fleet efficiency falls to 45.8%, and the old fixed 50% understated fuel burn from then on.
- Historical_Trend keeps a large baseload tranche, so its efficiency stays above 51% and its fossil share falls slightly.
- The hydrogen requirement on EirGrid_Extended in 2100 rises by 24%, because firm plant in a high-renewable system mostly does peaking duty.
- The 35% sensitivity in the 1 November entry below was run with the old constant. To repeat it, lower both tranche efficiencies in a copy of `Gamma.py`.

## Zonal network limits removed from 2036 in the projections: 1 November 2026

Group decision (Cian, Niall): from 2036 EirGrid_Extended and Historical_Trend have no zonal network constraint. This is a bounding case that favours renewables, not a forecast: all available wind and solar reaches the all-island system, and dispatch down after 2035 is surplus and curtailment only. It replaces any calibrated post-2035 reinforcement rate (see the cover recalibration, PR #29).
- Implemented with `reinforcement_steps`: +1,000,000 MW in every zone (NW, W, MID, NE, SW, SE, NI) from 2036, after the North–South step. No code change. Offshore keeps its own connection.
- Results to 2035, the validation runs and the GSS-2 prediction are unchanged.

| Result (all-island) | Old | New |
|---|---|---|
| EirGrid_Extended fossil share of primary energy 2050 / 2100 (%) | 66.3 / 34.4 | 63.5 / 28.6 |
| Historical_Trend fossil share 2050 / 2100 (%) | 74.4 / 62.9 | 72.9 / 56.9 |
| EirGrid_Extended dispatch down 2050 / 2100 (% of available) | 42.5 / 56.8 | 36.8 / 53.3 |
| of which constraint 2050 / 2100 | 25.0 / 33.8 | 0.0 / 0.0 |
| of which curtailment (incl. surplus) 2050 / 2100 | 17.4 / 23.0 | 36.8 / 53.3 |
| Historical_Trend dispatch down 2050 / 2100 (%) | 26.3 / 39.9 | 20.8 / 28.1 |
| EirGrid_Extended wind and solar share of demand 2050 / 2100 (%) | 71.8 / 78.6 | 75.3 / 81.6 |
| Historical_Trend wind and solar share of demand 2050 / 2100 (%) | 61.0 / 59.7 | 64.5 / 67.5 |
| EirGrid_Extended firm generation 2050 / 2100 (TWh) | 15.9 / 17.6 | 11.6 / 11.0 |
| Historical_Trend firm generation 2050 / 2100 (TWh) | 23.3 / 40.0 | 20.6 / 28.8 |
| Firm capacity 2050 / 2100, both pathways (GW) | 12.7 / 21.3; 12.4 / 20.3 | unchanged |
| EirGrid_Extended delivered wind capacity factor 2050 / 2100 (%) | 17.1 / 13.5 | 16.5 / 12.5 |
| EirGrid_Extended electricity for green-hydrogen firm plant 2050, 35% round trip (TWh) | 45.4 | 33.0 |
| EirGrid_Extended wind and solar dispatched down 2050 (TWh) | 36.2 | 31.3 |

Findings:
- Unlimited network access from 2036 lowers the 2050 fossil share by 2.8 points (EirGrid_Extended) and 1.5 points (Historical_Trend). In 2050, 103.1 of 126.2 TWh of fossil primary energy is unelectrified heat and transport, the same in both runs.
- Firm capacity does not change: still, cold periods set it, not the network.
- The delivered wind capacity factor falls slightly because solar, previously the most constrained, now reaches the system and shares the curtailment. Delivered solar in 2050 rises from 9.3 to 12.9 TWh; wind falls from 36.9 to 35.6 TWh.
- Green hydrogen for firm plant in 2050 now needs 27.5 to 47.2 TWh of electricity (42% to 24.5% round trip) against 31.3 TWh dispatched down. The earlier statement that it needs more than all dispatched-down output holds only at the central and lower efficiencies.
- `Sensitivity_EirGrid_Reinforcement_*` (40% cover) are not changed in this PR and are now superseded for the paper.
- Sensitivities rerun on the new setting (fossil share of primary energy, 2050 / 2100): firm plant at 35% efficiency, EirGrid_Extended 65.1 / 32.0 and Historical_Trend 74.7 / 60.5 (1.6 to 3.7 points above the central runs); heat-pump COP 3.9, EirGrid_Extended 62.5 / 26.0 and Historical_Trend 72.2 / 55.2 (0.7 to 2.6 points below). Run by changing `FIRM_FUEL_EFFICIENCY` and `HEAT_COP` in a copy of `Gamma.py`.
- On EirGrid_Extended, all wind and solar dispatched down first exceeds the electricity needed to run the firm plant on green hydrogen (35% round trip) in 2051, when 12.9 GW of firm capacity is needed (2056 on the published path).
- Figure 6 of the paper: `analysis/figure6_projections.py`, output `analysis/output/paper/figure6_projections.png`.

## Headroom cover re-fitted against GSS-1: 31 October 2026 (analysis only, no result changes)

`analysis/cover_recalibration.py` re-runs EirGrid_Validation_2030_2035 at 0 to 80% `headroom_pipeline_cover_pct` on the current model and compares Ireland with GSS-1 (2030: 33% ECP + 2.6 GW offshore; 2035: 66% ECP + 4.7 GW offshore) on three bases. Results in `analysis/output/cover_recalibration/`.

| Ireland, % of available wind + solar | EirGrid 2030 / 2035 | Gamma 0% cover | Gamma 40% cover |
|---|---|---|---|
| Constraint, Gamma's order (network first) | 5.7 / 6.0 | 15.0 / 19.0 | 6.3 / 6.0 |
| Constraint, EirGrid's order (surplus first; approximate) | 5.7 / 6.0 | 5.0 / 5.6 | 0.2 / 0.7 |
| Total dispatch down | 26.8 / 28.5 | 26.0 / 32.6 | 22.4 / 27.5 |

| Basis | Best cover | RMS error, points |
|---|---|---|
| Constraint, Gamma's order | 40% | 0.42 |
| Constraint, EirGrid's order | 0% | 0.57 |
| Total dispatch down | 10% | 2.02 |

- 40% still reproduces EirGrid's constraint on the current model, but only when constraint is counted in Gamma's order.
- Counted in EirGrid's order, Gamma on the published TID path with no cover already matches EirGrid's constraint within 0.7 points. The 40% fit is therefore mostly an artefact of the order in which constraint and surplus are removed, not evidence of network growth beyond the TID path.
- The 28 October finding that EirGrid's forecasts imply Ireland's zonal network capacity rises to about 9.7 GW by 2035 is not supported. The published TID path (about 5.4 GW) is consistent with GSS-1.
- Total dispatch down does not fit well at any cover value: more cover lowers 2030 below EirGrid while 2035 stays above it.
- EirGrid-order constraint is approximate: Gamma total minus surplus before constraint minus operational curtailment, where operational curtailment is computed after the network. It goes slightly negative above 50% cover.
- For group decision: whether `Sensitivity_EirGrid_Reinforcement_*`, the GSS-2 Cover40 rows and any post-2035 reinforcement coefficient should rest on the 40% fit. The prediction rows in `analysis/gss2_prediction_2035.csv` are not changed.

## Surplus reported separately: 30 October 2026 (no change to totals)

EirGrid's ECP studies split dispatch down into surplus, curtailment and constraint. Gamma now reports surplus as well; constraint, curtailment and totals are unchanged (validation totals 15.0 / 26.0 / 32.6% IE, as before).
- Surplus: wind and solar left after native demand, battery charging and exports, which no operating limit could release. It is the part of curtailment that remains at SNSP 100% with no minimum units.
- `summary_system.csv`: new `Surplus_%`, `Operational_Curtailment_%` (curtailment minus surplus, including the residual) and `Surplus_Before_Constraint_%` (the same quantity on output before the network is applied, EirGrid's order; diagnostic only). `summary_total.csv`: new `Surplus_%`.
- `analysis/eirgrid_validation.py` adds the three-way split:

| Ireland, % of available | EirGrid surplus | Gamma surplus (after network) | Gamma surplus (before network) | EirGrid curtailment | Gamma curtailment excl. surplus | EirGrid constraint | Gamma constraint |
|---|---|---|---|---|---|---|---|
| 2030 Initial | 5.4 | 0.2 | 2.3 | 2.2 | 4.4 | 10.0 | 10.5 |
| 2030 33% ECP + 2.6 GW offshore | 18.7 | 4.6 | 14.6 | 2.4 | 6.4 | 5.7 | 15.0 |
| 2035 66% ECP + 4.7 GW offshore | 21.5 | 9.7 | 23.2 | 0.9 | 3.9 | 6.0 | 19.0 |

- Finding: measured in EirGrid's order, Gamma's surplus is close to EirGrid's in 2035 (23.2% against 21.5%) and 4 points below it in 2030. Most of the gap in the constraint split is the order in which the categories are removed.

## Grid reinforcement study: 30 October 2026 (analysis only, no result changes)

- `analysis/headroom_history.py`: effective headroom that reproduces each year's recorded constraint. IE 4,469 MW (2021) to 4,323 MW (2025), trend −0.4% a year. Zone values move by up to 20% a year either way and do not support a zonal growth rate.
- `analysis/grid_reinforcement_study.py`: EirGrid_Extended to 2050 at 0, 1, 2, 4 and 7.3% a year IE headroom growth, each with and without interconnector flows; wind, solar and battery build x1.5 and x2.0 at 0% and 7.3%; Historical_Trend at 0% and 0.5%. Results and tables in `analysis/output/grid_reinforcement/`.
- `Gamma.py`: `GAMMA_IC_DISPATCH=1` and `GAMMA_CHARTS=0` environment switches. Defaults unchanged.
- Findings: in 2050, 103.1 of 119.6 TWh of fossil energy is unelectrified heat and transport, the same in every run. Headroom growth from 0 to 7.3% a year moves the fossil share from 66.7% to 63.9%; with interconnector flows, 65.0% to 63.1%. The next 10.5 GW of wind and solar delivers 0.27 TWh/GW against a fleet average of 1.01 TWh/GW.
- For group decision: Historical_Trend uses 0.5% a year headroom growth; the recorded rate is about 0%. At 0% its 2050 fossil share is 74.8% (74.4% now).

## Residual curtailment on the delivered basis; sensitivity study: 30 October 2026

Group decision: the corrected residual curtailment is now the default (PRs #24 and #25 merged).
- Residual curtailment κ (the recorded high frequency and minimum generation curtailment the rules do not simulate) was a fixed share of available energy. That share grew without limit as capacity was added, so in faster-build runs adding wind and solar reduced delivered output. It is now the same 2026 energy, held in later years as a share of the energy the operating rules would otherwise deliver. 2026 results are identical. `GAMMA_RESIDUAL_BASIS=available` reproduces the old basis.
- Heat and transport demand now stops growing once those sectors are fully electrified (no effect on the paper's scenarios, which stay below the caps).
- New `analysis/sensitivity_study.py`: heat and transport electrification pace, and wind, solar and battery build rate, each +50%, +100% and +150% on EirGrid_Extended; tables and charts in `analysis/output/sensitivity/` (old basis in `sensitivity_available/`).
- Effect on the paper's results (old → new):

| Result | Old | New |
|---|---|---|
| EirGrid validation, Gamma total 2030 Initial / 2030 / 2035 (% IE) | 15.2 / 26.8 / 33.6 | 15.0 / 26.0 / 32.6 |
| Largest difference from EirGrid (points) | 5.1 | 4.1 |
| 40% reinforcement, 2035 total (% IE; EirGrid 28.5) | 28.3 | 27.5 |
| GSS-2 central prediction, 100% ECP / with offshore (% IE) | 23.4 / 34.2 | 22.6 / 33.0 |
| EirGrid_Extended fossil share 2050 / 2100 (%) | 67.3 / 38.9 | 66.3 / 34.4 |
| Historical_Trend fossil share 2050 / 2100 (%) | 74.6 / 63.8 | 74.4 / 62.9 |
| EirGrid_Extended dispatch down 2050 / 2100 (%) | 44.2 / 59.4 | 42.5 / 56.8 |
| Firm capacity 2050 / 2100 (GW) | 12.7 / 21.3 | unchanged |

- `analysis/gss2_prediction_2035.csv` keeps the 28 October prediction and adds the revised rows, both made before EirGrid publishes.

## ECP-GSS-2 prediction: 28 October 2026

- GSS-2 assumptions (Q4 2026) and generation list (data freeze 2 October 2026) added: `Data_inputs/ECP-GSS-2-IE-Generation-List.xlsx`. EirGrid publishes GSS-2 results on 15 December 2026; until then validation stays on GSS-1.
- Four prediction runs for the two GSS-2 Future Grid (2035) cases that the generation list fully specifies, `100% ECP` and `100% ECP + 4.7 GW offshore`, each on the published network path and with the 40% headroom cover: `GSS2_Prediction_2035_*`, paths `eirgrid_gss2_fg_100ecp*.csv`. GSS-2 rules: SNSP 100%, no minimum sets, 1 Dublin unit; 2022 weather.
- Results in `analysis/gss2_prediction_2035.csv`. Central prediction (cover 40%): Ireland total dispatch down 23.4% (100% ECP) and 34.2% (with offshore).
- New IE capacity is still split between zones by the GSS-1 list; GSS-2 zone shares are within 2 points of GSS-1 for wind and solar.

## Paper revision 9 changes: 28 October 2026

- `CHART_DPI = 600` near the top of `Gamma.py`; every saved chart uses it (was 130 to 300). Runs take about a minute longer.
- `storage_initial_soc_pct` removed from the scenario workbook and the Field Guide. It only affects the first day of each weather year; the code keeps 50% as a fixed default and no longer asks for it or flags it as missing.
- `Historical_Trend`: SNSP and minimum units now follow the TSO roadmap, the same values as the EirGrid runs (SNSP 95% in 2030, 100% from 2035; units IE 4 + NI 1 in 2030, IE 1 + NI 0 from 2035). Operating rules are policy, not a build trend. The old slower ramp is kept as `scenario_paths/historical_trend_slow_ops.csv`. Effect: dispatch down differs by at most 1.4 points (2035), fossil share by at most 0.3 points; 2050 fossil share 74.6% (was 74.5%).
- EirGrid runs unchanged (results identical).

## Reinforcement implied by EirGrid's results: 28 October 2026 (sensitivity)

Ported from closed PR #19 as a sensitivity only (PR #21).
- New scenario input `headroom_pipeline_cover_pct` (default 0): each IE zone's headroom also grows by this % of the onshore wind + solar MW connected there since 2026.
- Two runs use 40%: `Sensitivity_EirGrid_Reinforcement_2035` (as the validation run) and `Sensitivity_EirGrid_Reinforcement_2050` (as EirGrid_Extended, to 2050). Every other run uses 0.
- 40% is the value at which Gamma's Ireland constraint matches EirGrid GSS-1 (tested 15, 30, 40, 50, 80%). PR #19 had 15% on an older setup; on the current model 15% gives 11.6% constraint in 2035, not 6%.

| Ireland, % of available wind + solar | constraint | curtailment and surplus | total |
|---|---|---|---|
| EirGrid GSS-1 2030 (33% ECP + 2.6 GW offshore) | 5.7 | 21.1 | 26.8 |
| Gamma validation run, 2030 | 15.0 | 11.8 | 26.8 |
| Gamma with 40% cover, 2030 | 6.3 | 16.7 | 23.0 |
| EirGrid GSS-1 2035 (66% ECP + 4.7 GW offshore) | 6.0 | 22.4 | 28.5 |
| Gamma validation run, 2035 | 19.0 | 14.6 | 33.6 |
| Gamma with 40% cover, 2035 | 6.0 | 22.3 | 28.3 |

Findings for the paper:
- EirGrid's constraint forecasts imply Ireland's zonal network capacity rises from about 5.1 GW (2026) to about 9.7 GW by 2035. The published TID path gives about 5.4 GW.
- More reinforcement mostly moves losses from constraint to curtailment. In 2050 (EirGrid_Extended), the extra 10 GW of IE headroom cuts Ireland's constraint from 26.4% to 6.0% but raises curtailment from 19.2% to 33.0%; total dispatch down falls from 45.6% to 38.9%. Fossil share of primary energy in 2050: 67.3% -> 64.6%.

## EirGrid validation, historical trend and primary energy: 28 October 2026

Agreed in the group on 27-28 October: drop the TIM comparison, validate against EirGrid, add a run on recorded trends, report primary energy, and call the gap between renewables and demand 'firm'. Values marked VERIFY in the inputs still need checking.

### Scenarios (Data_inputs/scenariosXLSX.xlsx)
- Removed: Validation1_TIMES_CopperPlate, Validation2_EirGrid_ECP_GSS2, RUN1_Planned, RUN2_Historical_Actual, and the 'AIRAA ECP-GSS2 2035' sheet.
- **EirGrid_Validation_2030_Initial** and **EirGrid_Validation_2030_2035**: EirGrid's ECP-GSS-1 study portfolios (Initial; 33% ECP + 2.6 GW offshore in 2030; 66% ECP + 4.7 GW offshore in 2035), EirGrid's operating rules (2030: SNSP 95%, IE 2 + 2 Dublin must-run, NI 1; 2035: SNSP 100%, 1 Dublin unit) and EirGrid's 2020 weather. `python analysis/eirgrid_validation.py` compares their Ireland results with the published study.
- **EirGrid_Extended**: the same portfolios to 2035, then EirGrid's 2030-2035 build and demand rates carried on to 2100, all weather years.
- **Historical_Trend**: recorded 2019-2025 rates for onshore wind, solar, batteries and demand; offshore only for projects holding ORESS contracts, three to four years late; SNSP and minimum units on their ten-year trends; 0.5%/yr reinforcement plus the North-South interconnector; to 2100.
- 2026 batteries 550 MW / 1,330 MWh -> 1,000 MW / 1,600 MWh (over 800 MW connected in Ireland by June 2026, plus NI). VERIFY.
- 'Input Recommendations' rewritten with the source of every value. 'Field Guide' has the two new columns.
- Data_inputs/Eirgrid ECP Parameters Used.xlsx: Cian's sheet kept as 'Cian original'; 'Corrected GSS-1' gives the published GSS-1 inputs and results; 'What was corrected' lists the errors (results were ECP-2.5 and rounded down; wind/solar capacity split wrong; 2025 actuals).

### Code (Gamma.py)
- New scenario column `scenario_path`: year-by-year capacities, storage, demand, SNSP and minimum units from Data_inputs/scenario_paths/<name>.csv (straight lines between listed years; rates carry on afterwards). Replaces the hard-coded RUN2 offshore build.
- New scenario column `weather_years` (blank = all).
- Runs may end in any year from 2030 to 2100. Runs ending before 2050 write CSVs only.
- Headline shares (red box, `Overall_*_Pct`) are now **primary energy**, excluding aviation and marine: firm electricity counts as the gas burnt to make it (50% efficiency); wind, solar and heat-pump ambient heat count as delivered. The previous final-energy shares are kept as `Final_*_Pct`.
- Red box now shows: primary energy shares, firm capacity, firm generation (gas today) and the extra electricity needed to run that firm plant on green hydrogen (`Firm_On_H2_Electrolysis_TWh` = firm / (0.50 x 0.70)). Physical quantities only; costs are for paper 2.
- `Full_Decarbonisation_Year`: first year fossil is at or below 10% of primary energy (also 5%), in scenario_summary.csv.
- Charts: the area between renewables and demand is filled and labelled 'Firm (dispatchable: gas today)' in the daily and monthly charts. Chart-only interconnector sensitivities removed.
- Summary years: 2030, 2035, 2040, 2050, 2075, 2100 (up to the run's end).

### Validation result and open point
- Ireland total dispatch down, Gamma against EirGrid GSS-1 (`analysis/eirgrid_validation.py`): 2030 Initial 15.2 vs 17.6%; 2030 33% ECP + 2.6 GW offshore 26.8 vs 26.8%; 2035 66% ECP + 4.7 GW offshore 33.6 vs 28.5%.
- The split differs: Gamma constraint 10-19%, EirGrid 6-10%. Two causes: Gamma applies network constraint before system curtailment (EirGrid removes surplus first), and the TID path grows IE headroom only about 5% by 2035 while EirGrid connects the pipeline with its reinforcements. PR #19 showed that letting IE headroom grow by 15% of connected pipeline MW reproduces EirGrid's 2035 split. That was fitted to EirGrid, so it is not used in the validation runs; it is recorded here as the size of reinforcement EirGrid's results imply. PR #19 closed as superseded by this change.

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

### Interconnector dispatch reversed (24 October 2026)
- Interconnector imports and exports are removed from the 15-minute dispatch (`INTERCONNECTOR_DISPATCH = False`). Firm plant covers every shortfall and surplus wind/solar is curtailed, as before issue #5. The chart-only interconnector sensitivities (50% import, maximum export) are kept. The interconnector code and scenario columns remain for a later price-based version.
- Overall Transition Progress (red box): imported electricity is the remainder of 100%, fixed at 4% (`FIXED_IMPORT_SHARE_PCT`); fossil and renewables, on the RED gross final consumption basis, are scaled to 96%.
- Effect in 2050 (A): firm generation 20.9 → 30.3 TWh, fossil 69.2%, renewables 26.8%, imports 4.0%; wind + solar share of demand 55.6%. In B, min-gen curtailment returns to the level without exports. Firm capacity required is unchanged (it never counted interconnector flows).

### Solar capacity history and curtailment calibration (24 October 2026)
- `analysis/build_solar_capacity.py` builds `Data_inputs/solar_capacity_monthly.csv` (month-end MW, IE / NI) from the project lists in the SONI/EirGrid System and Renewable Data Summary Report. Fleet = solar that reports in the dispatch-down records: IE transmission and distribution projects (MEC, energisation date) and NI controllable projects. Rooftop, NI uncontrollable and NI 'other small scale' solar are excluded. Listed fleet: 0.58 GW end-2023, 0.89 GW end-2024, 1.48 GW end-2025, 1.70 GW at the latest listing (mid-2026).
- Observed solar CF (available energy / capacity, MEC basis): IE 13.1% (2024) and 14.8% (2025); NI 11.0–12.1% (2021–2025); pooled 2024–2025 13.7%. `SOLAR_CAPACITY_FACTOR` 0.11 → 0.137. The 2026 solar capacity now comes from the list (1.70 GW) instead of being inferred from availability at 11% (1.88 GW). Each GW of new solar now delivers about 25% more energy.
- Solar 'other' curtailment is calibrated to recorded solar curtailment over the last 12 months (7.58%) less the modelled 2026 solar SNSP curtailment: 7.38%, against 4.6% for wind. It keeps that offset to the wind path in later years (`SOLAR_OTHER_CURT_CALIBRATED`).
- Actual solar CF now appears in the evaluation table (2022–2026). Caveats: IE solar is in the dispatch-down records only from April 2023, so 2022–2023 actual CF is understated; recorded curtailment sub-reasons do not always sum to the total (2022).

### Curtailment and capacity-factor tracking (24 October 2026)
- New output `evaluation_curtailment_cf.csv` in each scenario folder and `all_scenarios_evaluation_curtailment_cf.csv`, with actual years (2021–2025, 2026 part year) above the forecast years. For wind and solar separately: capacity, available and delivered energy, exported energy, available CF (weather resource before dispatch-down), delivered CF (after constraint, curtailment and the fixed 'other' loss), constraint %, curtailment split into SNSP, min gen and other, total curtailment %, dispatch-down %, and TWh constrained and curtailed. Combined wind + solar curtailment and dispatch-down, and battery charging from surplus.
- Actual rows come from the EirGrid/SONI hourly dispatch-down records. Recorded SNSP maps to SNSP; high frequency, RoCoF, other and TSO test map to 'other'; minimum generation is not recorded separately. Actual solar CF is blank because solar capacity history is not in the inputs.
- New chart `scenario_outputs/evaluation_curtailment_cf.png` (wind and solar delivered CF, wind and solar curtailment, all scenarios, with actuals) and a CF and curtailment table at the end of the console readout.
- Points the tracking shows: modelled solar curtailment in 2026 (4.8%) is below the 2025 actual (6.7%), which rose from 0.6% in 2022; the 2026 forecast row uses 2026 weather only, so its CFs are high (wind available 32%).

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
