# Context for the validation exercises

Written by `analysis/validation_context.py`.

## 1. One-year-ahead constraint hindcast against persistence

Error in constraint energy, %. Persistence applies the previous year's constraint share to the year's available output. The last year covers the months on record.

| Year | IE model | IE persistence | NI model | NI persistence | All-island model | All-island persistence |
|---|---|---|---|---|---|---|
| 2022 | +7.3 | -7.4 | -18.0 | -27.8 | +1.2 | -12.3 |
| 2023 | +16.0 | +12.3 | -60.2 | -58.5 | -16.6 | -18.0 |
| 2024 | -12.0 | -12.2 | -45.5 | -47.1 | -30.9 | -31.9 |
| 2025 | -22.2 | -25.8 | +40.1 | +42.1 | +1.6 | +0.1 |
| 2026 | -1.3 | -6.9 | -1.0 | -5.7 | -1.2 | -6.4 |
| Mean absolute error | 11.8 | 12.9 | 33.0 | 36.2 | 10.3 | 13.8 |

Hourly fit of the constraint curve on its fit years:

| Region | Fit years | Median limit (MW) | sigma | Highest available output (MW) | RMSE (MW) | Mean constraint (MW) | R2 | R2 of a flat share |
|---|---|---|---|---|---|---|---|---|
| IE | 2024-2026 | 7,982 | 1.17 | 5,038 | 139.2 | 97.9 | 0.502 | 0.339 |
| NI | 2024-2026 | 1,115 | 1.89 | 1,211 | 105.7 | 79.8 | 0.451 | 0.393 |

## 2. EirGrid ECP-GSS-1 offshore cases by weather year

`EirGrid_Validation_2030_2035` run on each complete weather year. Ireland, % of available wind and solar. EirGrid's study uses 2020 weather.

| Weather year | 2030 total | of which residual | 2035 total | of which residual |
|---|---|---|---|---|
| 2014 | 19.1 | 3.1 | 23.6 | 3.0 |
| 2015 | 23.4 | 2.9 | 28.2 | 2.8 |
| 2016 | 18.0 | 3.2 | 22.3 | 3.1 |
| 2017 | 18.3 | 3.2 | 22.4 | 3.0 |
| 2018 | 19.9 | 3.1 | 24.5 | 2.9 |
| 2019 | 20.3 | 3.0 | 24.9 | 2.9 |
| 2020 | 23.7 | 2.9 | 28.3 | 2.7 |
| 2021 | 20.4 | 3.1 | 24.7 | 3.0 |
| 2022 | 23.6 | 2.9 | 28.5 | 2.8 |
| 2023 | 21.7 | 3.0 | 26.7 | 2.8 |
| 2024 | 21.3 | 3.0 | 26.0 | 2.9 |
| 2025 | 21.2 | 3.0 | 26.0 | 2.9 |
| Mean (standard deviation) | 20.9 (2.0) | | 25.5 (2.2) | |
| Range | 18.0 to 23.7 | | 22.3 to 28.5 | |
| EirGrid (2020 weather) | 26.8 | | 28.5 | |
