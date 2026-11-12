# Robustness of the 2050 results

Written by `analysis/robustness_study.py`. One assumption is changed at a time; every other input is as in the scenario workbook. All thirteen weather years.

| Case | Group | Fossil share 2050, EirGrid_Extended (%) | Fossil share 2050, Historical_Trend (%) | Dispatch down 2050, EirGrid_Extended (%) | Fossil firm generation 2050, EirGrid_Extended (TWh) |
|---|---|---|---|---|---|
| Base (as in the paper) | base | 59.2 | 69.8 | 32.1 | 13.0 |
| Residual curtailment set to zero (wind and solar) | dispatch down | 57.5 | 68.7 | 29.5 | 10.7 |
| Residual curtailment doubled | dispatch down | 60.9 | 70.9 | 34.7 | 15.4 |
| 400 MW per minimum unit (residual recalibrated) | dispatch down | 58.6 | 69.2 | 31.1 | 12.2 |
| No zonal network limits from 2027 | dispatch down | 59.2 | 69.8 | 32.1 | 13.0 |
| Network limits kept after 2035 | dispatch down | 61.6 | 71.1 | 37.1 | 17.2 |
| Network frozen at 2026 headroom | dispatch down | 62.0 | 71.4 | 37.7 | 17.7 |
| Network frozen, sigma low (IE 0.8, NI 1.2) | dispatch down | 63.0 | 72.0 | 39.7 | 19.4 |
| Network frozen, sigma high (IE 2.0, NI 2.5) | dispatch down | 60.7 | 70.9 | 35.4 | 15.8 |
| Firm efficiencies 60% and 42% | driver | 58.7 | 69.4 | 32.1 | 13.0 |
| Firm efficiencies 50% and 34% | driver | 59.8 | 70.3 | 32.1 | 13.0 |
| Heat COP 2.5 | driver | 61.6 | 71.8 | 32.1 | 13.0 |

EirGrid_Extended: fossil share 2050 is 59.2% in the base case and 57.5% to 63.0% across the dispatch-down cases; fossil firm generation 10.7 to 19.4 TWh.

Historical_Trend: fossil share 2050 is 69.8% in the base case and 68.7% to 72.0% across the dispatch-down cases; fossil firm generation 16.7 to 22.2 TWh.
