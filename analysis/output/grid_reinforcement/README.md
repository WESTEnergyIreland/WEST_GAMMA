# Grid reinforcement study, 30 October 2026 (fossil shares updated 1 November 2026 for the firm fleet efficiency, PR #32)

Runs: `python analysis/grid_reinforcement_study.py` and `python analysis/headroom_history.py`. All runs are EirGrid_Extended to 2050 unless named, residual curtailment on the delivered basis, main branch inputs otherwise unchanged. Percentages of available energy are all-island (IE and NI together), so they differ slightly from the IE-only figures in Table S8. Fossil share is of gross final energy as Gamma reports it (`Overall_Fossil_Fuel_Pct`).

## 1. Recorded headroom has not grown

Effective headroom that reproduces each year's recorded constraint, σ held at 0.88 (IE) and 1.13 (NI). File: `analysis/output/headroom_history.csv`.

| Area | 2021 | 2022 | 2023 | 2024 | 2025 | Trend (%/yr) |
|---|---:|---:|---:|---:|---:|---:|
| IE | 4,469 | 4,625 | 4,955 | 4,740 | 4,323 | −0.4 |
| NI | 1,130 | 1,120 | 681 | 427 | 559 | −21.1 |
| NW | 353 | 265 | 268 | 234 | 260 | −7.1 |
| W | 916 | 839 | 917 | 863 | 883 | −0.4 |
| MID | 1,554 | 1,766 | 1,399 | 1,151 | 647 | −19.6 |
| SW | 1,301 | 1,651 | 2,075 | 2,076 | 2,326 | +14.9 |
| SE | 645 | 803 | 714 | 785 | 521 | −4.4 |

NE is left out: it recorded no constraint in 2021, so its 2021 headroom is unbounded.

Ireland's effective limit was the same in 2025 as in 2021. H is the net of reinforcement and of capacity connecting behind existing bottlenecks, so it cannot say which projects did what. Zone values move by up to 20% a year in either direction. Five points per zone are too few, and too affected by single events, to give a zonal growth rate. The zone split also uses today's MW in every year, as the zonal backcast does.

## 2. Headroom growth: most of the gain moves into curtailment

EirGrid_Extended, 2050, no interconnector flows (the paper's setting).

| IE headroom growth (%/yr) | Constraint (%) | Curtailment (%) | Dispatch down (%) | W+S delivered (TWh) | Firm generation (TWh) | Fossil share (%) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 27.1 | 16.0 | 43.1 | 45.7 | 16.5 | 66.6 |
| 1 | 23.4 | 18.6 | 42.0 | 46.5 | 15.5 | 66.0 |
| 2 | 19.8 | 21.2 | 41.0 | 47.1 | 14.7 | 65.6 |
| 4 | 13.5 | 26.0 | 39.4 | 47.9 | 13.5 | 64.8 |
| 7.3 | 5.9 | 31.8 | 37.7 | 48.4 | 12.2 | 64.2 |

## 3. Why the fossil share hardly moves

In 2050 on EirGrid_Extended, fossil energy is 119.6 TWh. Of this, 103.1 TWh is heat and transport that has not been electrified, and 16.5 TWh is firm electricity generation. The 103.1 TWh is the same in every run, because the grid does not change the electrification path. If firm generation were zero, the fossil share would still be 57.5%. Reinforcing at 7.3% a year removes 4.2 TWh of firm generation.

The fossil share in 2050 is set by the pace of electrification of heat and transport, not by the grid. The sensitivity study shows this: heat and transport electrification at 2.5 times the EirGrid_Extended pace gives 53.3% (`analysis/output/sensitivity/`).

## 4. Interconnector exports

The same runs with interconnector flows in the dispatch (exports at 50% of capacity, imports at 70%, the group's 24 October values).

| IE headroom growth (%/yr) | Dispatch down, no flows (%) | Dispatch down, with flows (%) | Exports (TWh) | Fossil share, no flows (%) | Fossil share, with flows (%) |
|---:|---:|---:|---:|---:|---:|
| 0 | 43.1 | 40.2 | 3.2 | 66.6 | 65.1 |
| 7.3 | 37.7 | 33.0 | 4.7 | 64.2 | 63.6 |

Exports cut curtailment by 3 to 5 points. The fossil share falls by 0.6 to 1.5 points, mostly through imports replacing firm generation. The range across headroom growth narrows from 2.4 points to 1.5 points. Leaving interconnectors out of the dispatch does not change the conclusion.

## 5. Marginal yield of new wind, solar and batteries

Wind, solar and battery build ×1.5 and ×2.0, 2050. Yield is the extra wind and solar energy delivered per extra GW of wind and solar installed.

| IE headroom growth | Average yield, base fleet (TWh/GW) | Yield of next 10.5 GW (TWh/GW) | Yield of the 10.5 GW after that (TWh/GW) | Firm generation saved by each step (TWh) |
|---|---:|---:|---:|---:|
| 0%/yr | 1.01 | 0.27 | 0.20 | 3.4, 2.4 |
| 7.3%/yr | 1.07 | 0.22 | 0.16 | 2.9, 1.8 |

On EirGrid_Extended in 2050, an extra GW of wind and solar delivers a fifth to a quarter of what the average GW in the fleet delivers. The yield is lower with more reinforcement, because the limit is then system-wide (demand, SNSP and timing), which reinforcement does not relieve. The ratio of marginal to average yield is a candidate measure for the point of diminishing returns. We have not found a published threshold for Ireland.

## 6. Historical_Trend at 0% headroom growth

| Historical_Trend | Dispatch down 2050 (%) | Fossil share 2050 (%) |
|---|---:|---:|
| 0.5%/yr (current input) | 26.3 | 74.4 |
| 0%/yr (recorded 2021–2025) | 27.6 | 74.8 |

Setting Historical_Trend to the recorded 0% a year raises the 2050 fossil share by 0.3 points. Not applied: group decision.
