# EirGrid ECP constraint forecasts (PLEXOS): benchmark notes for Gamma

These notes support the EirGrid validation exercise for the Phase 1 paper: comparing Gamma with EirGrid's PLEXOS results for 2028, 2030 and 2035 with offshore.

## Sources

- ECP-2.5 Constraints Analysis Excel for Publication (data freeze Q3 2025, results February 2026)
- ECP-2.5 Assumptions Document, final update (24 February 2026)
- ECP-GSS-1 Constraint Analysis Excel Report (data freeze 27 March 2026, results Q3 2026)
- Constraint Forecast Studies for ECP: Methodology Statement (v2.0, Q3 2026)

All are on the [ECP Constraint Forecast Reports page](https://www.eirgrid.ie/industry/customer-information/ecp-constraint-forecast-reports).

The scenario totals below are summed from the node-level rows in the two workbooks (25 October 2026). The results cover Ireland only: Northern Ireland is modelled but not reported. Percentages are of available controllable wind and solar energy. All study years use 2020 weather profiles.

`ecp25_summary.csv` and `gss1_summary.csv` in this folder hold the full totals, including wind and solar separately.

## Method points that matter for comparison

- EirGrid runs PLEXOS three times in sequence: surplus, then curtailment (operational limits), then constraint (N-1 network). Gamma applies constraint before curtailment, so the split will differ even where totals agree.
- Grandfathering and pro-rata allocation give identical Ireland totals in both workbooks, so the headline results can be used directly.
- Interconnector flows come from a GB and France price model, are fixed after the surplus run and are published hourly. Use them as an exogenous input to Gamma.
- Available energy implies an onshore wind capacity factor of about 36% and solar of about 14% (2020 profiles). Offshore is about 39–41%.

## ECP-2.5 (Ireland, % of available)

| Case | Installed GW | Surplus | Curtailment | Constraint | Total |
|---|---|---|---|---|---|
| 2028 Initial | 6.8 | 6.1 | 8.0 | 10.5 | 24.6 |
| 2028 50% | 11.9 | 11.0 | 6.3 | 10.3 | 27.6 |
| 2028 ECP | 17.0 | 17.9 | 6.6 | 11.2 | 35.7 |
| 2030 Initial | 6.8 | 5.0 | 5.5 | 5.8 | 16.2 |
| 2030 50% | 11.9 | 12.0 | 4.0 | 6.4 | 22.3 |
| 2030 ECP | 17.0 | 19.3 | 4.0 | 7.4 | 30.6 |
| 2030 ECP without batteries | 17.0 | 24.0 | 5.4 | 7.6 | 37.0 |
| 2030 ECP + 3.1 GW offshore | 20.1 | 29.2 | 3.9 | 4.9 | 38.0 |
| 2035 ECP + 5 GW offshore | 22.0 | 23.9 | 2.6 | 6.2 | 32.7 |
| 2035 same, without France 2, LirIC, MaREs | 22.0 | 28.2 | 2.8 | 4.4 | 35.5 |
| 2035 same, ECP-2.4 interconnector method | 22.0 | 15.7 | 2.0 | 5.1 | 22.8 |

## ECP-GSS-1 (Ireland, % of available)

| Case | Installed GW | Surplus | Curtailment | Constraint | Total |
|---|---|---|---|---|---|
| 2030 Initial | 7.7 | 5.4 | 2.2 | 10.0 | 17.6 |
| 2030 33% ECP | 12.4 | 10.0 | 2.3 | 8.0 | 20.2 |
| 2030 33% + 1.3 GW offshore | 13.3 | 14.0 | 2.4 | 7.0 | 23.4 |
| 2030 33% + 2.6 GW offshore | 14.3 | 18.7 | 2.4 | 5.7 | 26.8 |
| 2030 33% + 2.6 GW offshore, reduced batteries | 14.3 | 20.4 | 2.5 | 6.4 | 29.3 |
| 2030 100% ECP | 21.7 | 22.8 | 2.4 | 8.2 | 33.4 |
| 2035 66% ECP | 17.1 | 11.6 | 0.6 | 11.3 | 23.5 |
| 2035 66% + 4.7 GW offshore | 20.3 | 21.5 | 0.9 | 6.0 | 28.5 |
| 2035 100% ECP | 21.7 | 15.6 | 0.7 | 12.5 | 28.8 |

The maintenance programme adds about 1.1–2.4 points of constraint (2030 33%, 2030 100% and 2035 66% cases).

## Findings

1. The 2028 and 2030 Initial cases (6.8–7.7 GW controllable, close to today's fleet) give 16–25% total dispatch down. Recorded Ireland wind dispatch down was 12.8% in January to August 2026.
2. The constraint and surplus split is driven by the run order. Adding offshore lowers the constraint percentage (8.0 to 5.7 in GSS-1 2030), and 2035 100% ECP shows more constraint than 2030 despite reinforcement, because less energy is removed at the surplus and curtailment stages. EirGrid notes this itself.
3. Two rounds six months apart differ by several points for similar Initial portfolios: 2030 curtailment is 5.5% in ECP-2.5 and 2.2% in GSS-1; constraint is 5.8% and 10.0%. This gives a natural tolerance for the benchmark.
4. The interconnector method alone moves the 2035 total from 32.7% to 22.8% (ECP-2.5).
5. In hours flagged as surplus dispatch down, the published flows show net imports on average in the smaller portfolios: ECP-2.5 2028 Initial 834 MW and 2030 Initial 1,143 MW; GSS-1 2030 Initial 793 MW, 33% 454 MW and 2035 66% 498 MW. Only the large portfolios are net exporters in those hours. To query with EirGrid.
6. ECP-2.5 2030 Initial imports 24 TWh over the year (2028 Initial 12 TWh, GSS-1 2030 Initial 10 TWh) and has the same surplus-hour count as 2030 50% (1,785). Possibly a workbook error.
7. ECP-2.5 2028 and 2030 Initial use the same portfolio, but 2030 curtailment is 2.5 points lower. Between them, minimum sets fall from six units to three and SNSP rises from 85% to 95%. This pair isolates the effect of the operating rules.

## ECP-2.5 final assumptions

- Minimum sets (IE, NI): 2028 4,2; 2030 2,1; 2035 0,0. The August 2025 draft gave all-island 7, 3 and 0.
- SNSP 85% (2028), 95% (2030) and 100% (2035). Inertia floor 23,000 MWs in all years. Synchronous condensers: 7,000 MWs in IE and 4,000 MWs in NI.
- Reserve 500 MW, or 700 MW once Celtic is on (largest single infeed). Dynamic line rating up to 30%.
- Not included: renewable hubs, short and long-duration storage classes, hybrid connections.
- Interconnectors: 2028 EWIC, Greenlink, Moyle (400 MW export, 450 MW import) and Celtic from Q2; 2030 Moyle at 500 MW both ways; Future Grid adds LirIC and a second France link (700 MW each), MaREs and the second North–South.
- Network: NDP Q3 2025 for 2028 and 2030; NDP Q4 2025 and SOEF 1.1 for Future Grid. The assumptions document lists 32 reinforcement projects for 2028, about 42 more for 2030 and 17 for Future Grid, including the North South 400 kV interconnector. It also gives the outage programme by month.

Capacity in Ireland (MW, all units including uncontrolled):

| | Initial | 50% | ECP | ECP + 3.1 GW | ECP + 5 GW |
|---|---|---|---|---|---|
| Battery | 1,018 | 2,724 | 4,429 | 4,429 | 4,429 |
| Solar | 1,757 | 5,535 | 9,312 | 9,312 | 9,312 |
| Onshore wind | 5,483 | 6,827 | 8,172 | 8,172 | 8,172 |
| Offshore wind | 25 | 25 | 25 | 3,099 | 5,025 |

Northern Ireland: onshore wind 1,425, 1,723, 2,021, 2,021 and 2,342 MW across the same cases; solar 156, 268 and 380 MW; batteries 200, 645 and 1,090 MW; offshore 500 MW in the ECP + 5 GW case only. GSS-1 2030 Initial gives NI onshore wind of 1,656 MW.

At 150 MW per unit, the synchronous floor is 900 MW in 2028 (six units), 450 MW in 2030 (three units) and zero in 2035. GSS-1 adds two must-run units in Dublin in 2030 and one in 2035 for voltage control.

## Inputs in the GSS-1 workbook

Asset list with node, area, MEC, controllability, priority and battery MWh; area capacity tables for IE and NI by scenario; network reinforcements by area and year with CP numbers; transmission outage programme by month; binding contingencies; hourly interconnector flows with a surplus flag.

## Model changes needed for the benchmark

1. Option to run a single weather year (2020). Gamma's 2020 solar is the synthetic average shape, because the quarter-hourly solar series starts in 2022.
2. Hourly interconnector flows as an exogenous input, with a switch for EirGrid's SNSP formula (imports in the numerator, exports in the denominator).
3. A separate surplus step: available output above demand plus exports plus battery charging, less imports and must-run output.
4. An explicit synchronous floor in place of κ: minimum sets by jurisdiction and year, the Dublin must-run units for GSS-1, and the reserve requirement.
5. Offshore on its own connection nodes: Poolbeg, Belcamp, Carrickmines, Arklow, Great Island, Knockraha, Moneypoint and Oriel.
6. A run-order switch (surplus, then curtailment, then constraint) so the split can be compared like for like. Report total dispatch down first either way.

Also: EirGrid's battery parameters (81% round trip, two cycles a day), Ireland-only reporting on controllable capacity, area capacities mapped to Gamma's zones, and demand from the AIRAA 2026–2035 median forecast (workbook still to be obtained).

## Decisions for the group before running

- How headroom is set. Suggested: calibrate on EirGrid's Initial case for a year, then test on the 50% and ECP cases for the same year and network.
- The tolerance that counts as a pass. EirGrid's own rounds differ by 3–4 points.
- Whether to query EirGrid (ecp_constraintsanalysis@eirgrid.com) on findings 5 and 6.
