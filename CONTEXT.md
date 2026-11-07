# WEST: project context

Read this before working on the code, the Phase 1 paper or the supplementary material. If you use an AI assistant, give it this file, `STYLE.md` and `WORKFLOW.md` at the start of every session.

Status: draft for group agreement, 30 October 2026. Change it by pull request.

## Who we are

WEST Energy Research Ireland: Niall Burke, Mark, Cian, Marcel Sarnecki and Laurentiu. The code in this repository is joint work by all five. Do not describe it as one person's code or address issues to one person.

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
- Residual curtailment is held on the delivered basis (PRs #24 and #25, 30 October 2026). See `CHANGELOG.md`.
- Projections have no zonal network limits from 2036 (PR #30, 1 November 2026). This is a bounding case that favours renewables, not a forecast; it replaces any post-2035 reinforcement rate. The 40% headroom cover is not presented as EirGrid's implied network growth: it matches GSS-1 only when constraint is counted in Gamma's order (PR #29).
- Gamma keeps its own order of calculation (network, then system-wide limits). The paper validates on total dispatch down and reports the EirGrid-order split alongside.
- 2 November 2026: transport ceiling is land transport only (62.2 TWh all-island); EirGrid_Extended and Historical_Trend raise battery fleet duration to 4 h by 2035 with the MW build unchanged; the paper names each share by its denominator (primary energy, gross final energy, electricity demand) and uses SEAI's RES Overall only for the gross final share. See `CHANGELOG.md`.
- The ECP-GSS-2 prediction (`analysis/gss2_prediction_2035.csv`) was made before EirGrid publishes on 15 December 2026. Its central case is the published network path, from 7 November 2026 (it was cover 40% before the AIRAA demand correction); cover 40% is the other end of the range. The 7 November rows are final: no further revisions.

## Where things live

| Item | Location | Master copy |
|---|---|---|
| Model code and data | This repository, `main` branch | Yes |
| Results and their history | `CHANGELOG.md` (old and new values for each change) | Yes |
| Phase 1 paper | Google Doc: https://docs.google.com/document/d/15OlYty5Je8CPnB4lGJkW9Y26FSSnsYH9zvku88tn37A | Yes, the only copy. Do not edit downloaded or Markdown copies. |
| Supplementary material | To be confirmed | |
| Group discussion | Teams chat | |

## Key sources

- EirGrid and SONI dispatch-down reports and half-hourly workbooks
- EirGrid ECP-GSS-1 and GSS-2 generation lists and results
- SEAI National Energy Projections 2026
- CBWG report on the TIMES-Ireland Model (context only, not a validation target)
