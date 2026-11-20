# WEST: project context

Read this before working on the code, the Phase 1 paper or the supplementary material. If you use an AI assistant, give it this file, `STYLE.md` and `WORKFLOW.md` at the start of every session.

Status: draft for group agreement, 30 October 2026; updated 20 November 2026. Change it by pull request.

## Who we are

WEST Energy Research Ireland: Niall Burke, Mark Kelly, Cian Murtagh, Marcel Sarnecki and Laurentiu Dimache. All five are authors of the Phase 1 paper (Laurentiu Dimache from 18 November 2026). The code in this repository is joint work by all five. Do not describe it as one person's code or address issues to one person.

## Aim

An independent, evidence-based assessment of Ireland's energy system, aiming for a system that is realistic, strong and secure.

- Pragmatic and open to renewables, but not at any cost. The price of the transition matters.
- All supply options are open, including nuclear. All demand options are open. Security of supply is the only priority.
- Carbon capture is out of scope.
- Comparisons with other countries are fine where the evidence supports them.
- Projected technology improvement (for example PV maturing) is acceptable if stated as an assumption.

## Scope of Phase 1

- Electricity grid only, with electrification of heat and transport kept in view as demand.
- Phase 1 output is a paper with two aims: (1) the method, our own open grid model (Gamma), built with open-source code rather than TIMES-Ireland (TIM) and validated against records and EirGrid; (2) where the energy transition is heading, from projections on the published plan and on recorded trends to date.
- Costs come later. Paper 1 has no costs and opens the economic argument on the cost of hydrogen. Paper 2 costs the transition from three angles: technology, monetary cost and energy return on investment (EROI).
- Main interest: how constraint and curtailment grow as the grid and interconnection grow, SNSP rises and minimum generation falls.

## Decisions to date

- TIM comparison dropped (October 2026). TIM includes bioenergy, hydrogen, district heating and exports, so its results are not comparable with a grid-only model.
- Validation is against EirGrid only (ECP-GSS-1 and the PLEXOS 2028, 2030 and 2035 cases with offshore), plus a run at actual historical build rates.
- At most three scenarios in the paper, using SEAI projected demand and actual build rates.
- The paper says "full decarbonisation", not "net zero".
- Residual curtailment was held on the delivered basis (PRs #24 and #25, 30 October 2026) and was removed on 14 November 2026 (see below).
- Projections have no zonal network limits from 2036 (PR #30, 1 November 2026). This is a bounding case that favours renewables, not a forecast; it replaces any post-2035 reinforcement rate. The 40% headroom cover is not presented as EirGrid's implied network growth: it matches GSS-1 only when constraint is counted in Gamma's order (PR #29).
- Gamma keeps its own order of calculation (network, then system-wide limits). The paper validates on total dispatch down and reports the EirGrid-order split alongside.
- 2 November 2026: transport ceiling is land transport only (62.2 TWh all-island); EirGrid_Extended and Historical_Trend raise battery fleet duration to 4 h by 2035 with the MW build unchanged; the paper names each share by its denominator (primary energy, gross final energy, electricity demand) and uses SEAI's RES Overall only for the gross final share. See `CHANGELOG.md`.
- The ECP-GSS-2 prediction (`analysis/gss2_prediction_2035.csv`) was made before EirGrid publishes on 15 December 2026. Its central case is the published network path, from 7 November 2026 (it was cover 40% before the AIRAA demand correction); cover 40% is the other end of the range. The 7 November rows were registered as final. On 8 November an error was found in the constraint closed form (equation 3); corrected rows dated 8 November were added before publication, with the sigma interval, and the 7 November rows are kept as registered. The paper reports both.

- 12 November 2026: the headline fossil share counts no imported electricity. The fixed 4% allowance (`FIXED_IMPORT_SHARE_PCT`) is off by default, because the main runs have no imports in the dispatch and the allowance was larger than the imports the dispatch gives in 2050 even with interconnectors at full capacity. This reverses the decision of earlier the same day to keep it. Headline 2050 fossil share: 61.7% on EirGrid_Extended and 72.7% on Historical_Trend (59.2% and 69.8% with the allowance). Imports are shown only in the interconnector sensitivity, from the dispatch (60.2% and 68.4% at 70% of capacity). For group agreement.
- 12 November 2026: demand growth since 2026 that is neither heat-pump nor transport load is added as flat load, because most of it is data-centre demand. It was scaled on the recorded demand shape before, which overstated peak demand, firm capacity and the worst gas day. `GAMMA_FLAT_GROWTH=0` reproduces the earlier results.
- 14 November 2026: the fixed residual curtailment is removed from Gamma. Curtailment is only what the SNSP and minimum generation ceilings remove. 2026 dispatch down is now 12.3% against 15.2% recorded, and the validation against EirGrid falls about 3 points lower. For group agreement. See `CHANGELOG.md`.
- Target journal: Energy Policy (Elsevier), decided by 20 November 2026 (previously Energy Economics, before that Renewable Energy). Every quantity the model computes is written as an equation in `docs/model_equations.md` and Supplementary S2; keep them in step with `Gamma.py`.

- 13 November 2026: the paper names the scenarios EirGrid Extended (EE) and Historical Trend (HT) and states energy shares as shares of Total Primary Energy (TPE). The workbook rows keep the names EirGrid_Extended and Historical_Trend. Decent Living Energy content was removed from the paper.
- 14 November 2026: the ECP-GSS-2 prediction was removed from the paper. Its rows stay in this repository.
- 6 and 11 November 2026, gas: supply is Moffat entry capacity with the committed Scottish compressor upgrades (433 GWh/d rising to 475 GWh/d from winter 2027/28; the uncommitted EMD compressors are excluded), Corrib on GNI's decline and biomethane on GNI's Low scenario. Floating LNG (emergency only), linepack, distillate firing and any shortage of supply from Great Britain are excluded. The worst gas day is reported with interconnectors at 70% of capacity as the central case and 0% and 100% as bounds. Whether "without the planned Moffat upgrade" meant the EMD compressors is to be confirmed by the group.
- Headline after the 14 November change: 2050 fossil share of TPE 59.8% (EE) and 71.5% (HT), with no import allowance and zero interconnector flows; electricity-equivalent share 37.4% and 52.4%.
- 20 November 2026 (pre-submission review): the share of electricity demand met by wind and solar counts wind and solar delivered through batteries (EE 2050: 85.6%, previously reported as 78.1%); the fossil share of useful energy is a model output (`Useful_Fossil_Share_Pct`); the 40% headroom-cover case is dropped from the paper with Table S6; heat and transport electrification rates on EE are checked against SEAI NEP 2026 results data (`Data_inputs/nep26_sector_electricity.csv`).
- 20 November 2026: the repository is public at https://github.com/WESTEnergyIreland/WEST_GAMMA. Licence and Zenodo archive to be decided.

## Where things live

| Item | Location | Master copy |
|---|---|---|
| Model code and data | This repository, `main` branch | Yes |
| Results and their history | `CHANGELOG.md` (old and new values for each change) | Yes |
| Phase 1 paper | Google Doc: https://docs.google.com/document/d/15OlYty5Je8CPnB4lGJkW9Y26FSSnsYH9zvku88tn37A | Yes, the only copy. Do not edit downloaded or Markdown copies. |
| Supplementary material | Google Doc: https://docs.google.com/document/d/1IbNGp2xSkGT3SIYn8SkO0widaRZ0q4xgOtFwKjExPQc | Yes, the only copy. |
| Group discussion | Teams chat | |

## Key sources

- EirGrid and SONI dispatch-down reports and half-hourly workbooks
- EirGrid ECP-GSS-1 and GSS-2 generation lists and results
- SEAI National Energy Projections 2026
- CBWG report on the TIMES-Ireland Model (context only, not a validation target)
