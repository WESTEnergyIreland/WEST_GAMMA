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
- Phase 1 output is a methodology paper on our own grid model (Gamma), built with open-source code rather than TIMES-Ireland (TIM).
- Costs come later. Paper 1 opens the economic argument on the cost of hydrogen; paper 2 makes it.
- Main interest: how constraint and curtailment grow as the grid and interconnection grow, SNSP rises and minimum generation falls.

## Decisions to date

- TIM comparison dropped (October 2026). TIM includes bioenergy, hydrogen, district heating and exports, so its results are not comparable with a grid-only model.
- Validation is against EirGrid only (ECP-GSS-1 and the PLEXOS 2028, 2030 and 2035 cases with offshore), plus a run at actual historical build rates.
- At most three scenarios in the paper, using SEAI projected demand and actual build rates.
- The paper says "full decarbonisation", not "net zero".
- Residual curtailment is held on the delivered basis (PRs #24 and #25, 30 October 2026). See `CHANGELOG.md`.
- The ECP-GSS-2 prediction (`analysis/gss2_prediction_2035.csv`) was made before EirGrid publishes on 15 December 2026. Do not revise those rows after that date.

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
