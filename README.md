Public Description:

DemonstratorV3 is a Python-based energy model designed to evaluate Ireland’s 2050 Reneables (wind & solar & storage) integration via decarbonisation/electrification scenarios, without relying on simplified copper-plate grid assumptions.The script applies a lognormal transfer-limit formula (L, and sigma) calibrated against EirGrid and SONI historical dispatch data to account for localised transmission constraints. In each 15-minute interval, the dispatch engine calculates regional transmission bottlenecks first, then applies System Non-Synchronous Penetration (SNSP) operational limits to the remaining available wind or solar power. Featuring rolling one-year-ahead hindcast error bands and an automated multi-scenario batch engine for multiple user inputs (scenarios.csv), DemonstratorV3.py projects annual capacity factors, constraint and curtailment losses, and the firm backstop thermal generation required to meet projected demand growth out to 2050 or beyond. 




Technical Briefing: 
NEW Wind Capacity & Loss Modelling Engine

Subject: Methodology, Inputs, & Hindcasting Architecture for the Advanced SEM Wind Loss Demonstrator (Code name:  DemonstratorV2.py, with data builder build_all_island_dd.py)

1. Executive Summary
Linear loss assumptions in long-term capacity expansion frameworks (such as TIM/TIMES) significantly underestimate renewable energy losses as wind penetration scales. Standard energy models typically treat grid constraints and SNSP curtailment as static percentages or simple linear derating factors. 
The NEW Wind Capacity & Loss Modeling Engine (DemonstratorV3.py) demonstrates why these static assumptions fail. By combining historical All-Island Single Electricity Market (SEM) dispatch data, separate network-limit constraint models for Ireland (IE) and Northern Ireland (NI) fitted to hourly dispatch-down records, a dispatch engine that sums usable wind directly from 15-minute intervals, user-configurable operational SNSP limits, and a 15-minute weather-loop hindcasting engine, the model dynamically captures how operational dispatch down compounds under decarbonisation demand growth (+1.87 TWh/year) up to 2050. Scenarios can be run in batch from a scenarios.csv file, with results reported for IE, NI and all-island, and an uncertainty band taken from a rolling one-year-ahead hindcast. A version history for handover is kept in CHANGELOG.md. 

2. Import of Input Files
The model ingests three primary historical external datasets (A, B and C) from available Eirgrid.ie data at System and Renewable Data Reports | Grid Information | EirGrid 

A. Historical System Characteristics  
Local Filename:(Input - capacity, constraints, curtailment.xlsx)
This Excel workbook supplies the historical annual system baselines across four dedicated worksheets: 
	CapacityByYear: Total installed wind capacity in Northern Ireland (NI_MW), Republic of Ireland (ROI_MW), and combined All-Island (Total_MW). 
	ConstraintsbyYear: Historical annual grid bottleneck constraint losses (Constraint_Pct). 
	RawCurtailmentbyYear: Historical system-wide oversupply/SNSP curtailment percentages (Curtailment_Pct). 
	CapacityFactorbyYear: Overall fleet capacity factors (Capacity_Factor_Pct). 
Processing
The python script extracts the exact 2026 baseline anchor points e.g. (6.51" GW"  total capacity, 10.0%baseline constraint, 4.9%baseline curtailment, and 23.0%baseline capacity factor). 
Earlier versions of the model projected constraints with a 0.75 power-law exponent on the capacity ratio. That exponent was a forward-looking compromise: the historical record showed constraints growing faster than capacity (an exponent of roughly 1.3 to 1.4) because deployment outpaced transmission reinforcement, while extending that trend to an 18–20 GW fleet gave implausible losses.
The exponent has now been replaced by a constraint model fitted to hourly records (file C, Section 5B). The two effects the exponent blended are now separate: how constraints respond to more wind comes from the fitted network limit, and future grid reinforcement is an explicit user input (Section 3). The ConstraintsbyYear figure no longer drives the forecast; its 2026 value is printed next to the modelled 2026 constraint for comparison.
{L and sigma}

B. High-Granularity Historical Dispatch Data from 2019 - present
Filename:  (sem_demand_wind_from_2019.csv)
Contains 15-minute operational records for system demand (sem_demand), wind generation (sem_wind_generation), and wind availability (sem_wind_availability) spanning historical years (2019–present). 
Processing:
The python code  merges this 15-minute time-series with the historical capacity figures to establish a normalised specific Theoretical Wind Availability per GW of installed wind:
"spec_avail_mw_per_gw"="sem_wind_availability" /"installed_gw" 

This is a ‘foundational’ value that is used for scaling. E.g. This scaled theoretical availability is compared directly against 15-minute system demand and the user-configured SNSP limit at each 15-minute interval. Any megawatt-hours exceeding the SNSP threshold are clipped as raw operational curtailment.   Also used in the daily charts: On the granular daily charts, theoretical availability forms the top boundary line (the dashed green line). It serves as the starting baseline from which Grid Bottleneck Constraints and SNSP Curtailment are stripped away to reveal the final usable wind generation


C. Hourly Dispatch-Down Records by Jurisdiction (2021 – August 2026)
Source files:  Raw Data\DD-HH-<year>.xlsx  →  built into  system_dd_hourly_ie.csv, system_dd_hourly_ni.csv, system_dd_hourly_all_island.csv
EirGrid/SONI half-hourly dispatch-down workbooks, one per year (sheet "DD HH"), with rows for each jurisdiction (IE, NI) and unit type (wind, solar). Columns include availability (AV_MWH), actual output, total dispatch-down, constraints (transmission constraint and TSO testing) and curtailments (high frequency/minimum generation, RoCoF/inertia, SNSP). The 2026 workbook covers January to August.
Processing (build_all_island_dd.py):
	Reads every DD-HH workbook in the Raw Data folder and keeps the wind rows.
	Sums half-hours into local-time hours. hh_count records how many half-hours each hour contains: 2 normally, 4 for the repeated hour when clocks go back, 0 for the skipped hour when clocks go forward. The hourly grid is completed only on days the source covers, so a missing file does not become rows of zeros.
	Writes three hourly files: IE only, NI only and all-island (IE + NI), and prints a summary per year with a Months column so part-years are visible. The IE output reproduces the earlier system_dd_hourly.csv exactly.
DemonstratorV2.py converts each hour from energy to average MW before fitting:
"MW"="MWh"×2/"hh_count" 
The IE and NI files are used for the constraint model only: each region is fitted separately (Section 5B) and tested with a rolling hindcast (Section 4). A year is used once it has at least 60 days of data (MIN_HOURS_FOR_FIT), so part-year 2026 counts and is labelled "2026 (8 mo)" in the tables. The constraint column is set by CONSTRAINT_COLUMN; trans_constr_mwh restricts the model to transmission constraints.
Why the split matters: in 2024 IE lost 5.1% of its available wind to constraint and NI 26.4%. The all-island figure, 9.35%, matches the ConstraintsbyYear sheet, which confirms that sheet is all-island. Earlier versions fitted IE data only and applied the IE rate to the whole island, which understated constraint.
Availability check: the forecast runs on the all-island 15-minute availability from file B. The script compares it with the IE + NI hourly total on the hours they share (ratio 0.995 on the 2021–2025 data) and warns if the two differ by more than 10%.
3. Scenario Inputs, Prompts & Batch Mode
Each run takes five inputs. If scenarios.csv sits next to the script, every row is run without prompts; otherwise the script prompts for one scenario. Pressing Enter at a prompt, or leaving a cell blank, uses the default.
	Annual Wind Build-Out Rate (build_rate_gw):
	Default: ~0.534 GW/yr, sized to the demand growth.  Function: capacity starts at the 6.51 GW 2026 anchor and adds one full build increment each year from 2027 (Section 5A).
	System Non-Synchronous Penetration Limit (snsp_limit_pct):
	Default: 75%.  Function: the SNSP ceiling in each 15-minute interval is this share of demand. It is applied to the wind left after network constraint (Section 5C).
	IE Network Reinforcement Rate (ie_reinforcement_pct):
	Default: 0% (limit held at its fitted value).  Function: annual % change in IE’s effective network limit, compounded from the last fitted year (Section 5B). Negative values represent continued tightening, as seen in IE since 2023. One-off increases can be added in REINFORCEMENT_STEPS_MW.
	NI Network Reinforcement Rate (ni_reinforcement_pct):
	Default: 0%.  Function: as above, for NI’s effective limit.
	New-Build IE Share (new_build_ie_pct):
	Default: today’s IE share of all-island availability (about 81%).  Function: the share of capacity added after 2026 that connects in IE; the rest goes to NI. Because NI is far more constrained, this split has a large effect on the result.

Scenario batch mode (scenarios.csv)
One row per scenario, with these columns:
Column	Meaning	Default when blank
scenario	Name; also the output folder name	scenario_<row>
build_rate_gw	Annual wind build-out (GW/yr)	0.534
snsp_limit_pct	SNSP limit (% of demand)	75
ie_reinforcement_pct	Annual % change in IE effective limit	0
ni_reinforcement_pct	Annual % change in NI effective limit	0
new_build_ie_pct	Share of new capacity located in IE (%)	Today's split (≈81%)
description	Free text, copied to the summary	(empty)

Outputs:
	scenario_outputs/<scenario>/forecast_results.csv: every forecast year, with the IE/NI split and the uncertainty band, plus that scenario’s six charts.
	scenario_outputs/all_scenarios_by_year.csv: every year of every scenario in one table.
	scenario_summary.csv: inputs and key results for 2030, 2040 and 2050, one row per scenario per year.
	Set SCENARIO_CHARTS = False for CSV outputs only (much faster for many scenarios). In prompt mode, results go to forecast_results.csv and the charts to the script folder.
The supplied scenarios.csv contains optimistic (+3%/yr reinforcement in both regions), central (0%), pessimistic (−3%/yr), an SNSP 90% variant and a 1 GW/yr build variant. Note that raising the SNSP limit has no effect when the network is not reinforced: constraint removes the wind before the SNSP ceiling is reached, so SNSP variants are best paired with a reinforced network.

4. Hindcasting Engine & Baseline Calibration
Annual results average every complete historical weather year (2019–2025), so each forecast year reflects the full range of weather on record. For the charts, each forecast year is assigned one weather year in rotation:
Forecast Year:  2026   2027   2028   2029   2030   2031   2032   2033   ...   2048   2049   2050
Weather Ref:    2019   2020   2021   2022   2023   2024   2025   2019   ...   2020   2021   2022
Baseline Calibration Procedure
	Demand Scaling: for each complete historical weather year (before 2026), historical demand is scaled to the forecast year’s demand (42.0 TWh in 2026, rising by 1.87 TWh/yr to 2050).
	2026 Baseline Run: the weather years are run against the 2026 fleet (6.51 GW) at the SNSP limit actually in force when the 2026 curtailment was recorded (HISTORICAL_SNSP_PCT, 75%). IE and NI constraint are removed first, then SNSP is applied to the remaining wind.
	Curtailment Split: the recorded 2026 curtailment (4.9%) is split into the part the SNSP rule explains and everything the model does not simulate (RoCoF, minimum generation, high frequency). The second part is held fixed; the SNSP part is recalculated each year at the scenario’s limit, so a higher limit can reduce curtailment. This replaces the earlier delta formula, which could never fall below 4.9%.
"RawCurt %" (t)="Other %"+"SNSP %" (t),  "Other %"=max(0, 4.9%-〖"SNSP %" 〗_2026 )
	Constraint Baseline: the same run gives the modelled 2026 constraint (all-island, IE and NI), printed next to the spreadsheet figure for comparison.

Constraint Model: Per-Year Fits and Rolling Hindcast
Each region is first fitted on each year separately, to show how its effective network limit has moved (fitting method in Section 5B):
Republic of Ireland (IE)
Year	Limit L (MW)	σ	Available (TWh)	Constraint (GWh)	Constraint %
2021	4,391	0.81	10.32	461	4.46
2022	4,599	0.85	11.93	575	4.82
2023	4,947	0.85	12.61	529	4.20
2024	4,583	0.86	12.48	639	5.12
2025	4,203	0.90	12.90	862	6.68
2026 (Jan–Aug)	4,012	0.91	8.59	646	7.52

Northern Ireland (NI)
Year	Limit L (MW)	σ	Available (TWh)	Constraint (GWh)	Constraint %
2021	1,191	0.84	2.37	100	4.22
2022	1,171	0.85	3.09	179	5.77
2023	700	1.02	2.90	409	14.08
2024	405	1.19	3.09	817	26.42
2025	552	1.11	3.02	562	18.65
2026 (Jan–Aug)	562	1.10	2.21	436	19.72

Both networks have tightened. IE’s effective limit has fallen about 19% since 2023, and its January–August 2026 constraint (7.5%) is about 50% higher than the same months of any earlier year. NI’s limit fell from about 1,180 MW (2021–2022) to 405 MW in 2024 and has partly recovered to about 560 MW, with constraint near 20% of its wind. Available wind was roughly flat over this period, so the change is in the networks (and where capacity connects), not in the weather.
The hindcast is rolling and one year ahead: each year is predicted from a fit on the previous year (HINDCAST_LOOKBACK_YEARS = 1), using that year’s actual hourly availability. This mirrors how the model is used for forecasting. IE results:
Predicted year	Fitted on	Actual (GWh)	Predicted (GWh)	Error
2022	2021	575	623	+8.3%
2023	2022	529	634	+19.8%
2024	2023	639	529	−17.2%
2025	2024	862	704	−18.3%
2026 (Jan–Aug)	2025	646	588	−9.1%

IE’s typical one-year-ahead error is about ±15% (mean absolute error 14.5%, bias −3.3%). Errors run in both directions, which is the normal year-to-year movement of the effective limit, but every year since 2023 is negative, which is the tightening trend. The script prints the same table for NI and all-island. The typical all-island error is applied to the forecast as a ± band:
〖"GridCon" 〗_"Low" ="GridCon"×(1-ε),  〖"GridCon" 〗_"High" ="GridCon"×(1+ε)
An earlier version trained once on 2021–2023 and held the limits fixed. It underpredicted all-island constraint by 35–40% in 2024–2026, almost entirely because of NI. That was a change in the networks, not a fault in the model’s shape, so the hindcast was redesigned rather than tuned.
Forecast fit years: both regions are fitted on 2024–2026 by default (CONSTRAINT_FIT_YEARS), so the forecast starts from today’s networks. On this basis IE’s limit is about 4,275 MW (σ = 0.89). NI’s is printed at run time; on 2024–2025 alone it was 471 MW (σ = 1.15). Whether recent tightening continues is a scenario choice (Section 3).

5. Mathematical Modeling & Loss Escalation Mechanics
As installed wind capacity grows relative to grid transmission capacity, losses escalate nonlinearly. The engine calculates annual outcomes through four interconnected mechanics: 
A. Capacity Build Trajectory
Fleet capacity starts at the 6.51 GW 2026 anchor and adds one full build increment each year from 2027, at the scenario’s build rate. Earlier versions gave 2027 and 2028 the same capacity, which left 2050 one increment short; this has been fixed.
"Capacity" (yr)=6.51+(yr-2026)×"build_rate_gw" 

B. Fitted Network-Limit Model (Constraints), Ireland and Northern Ireland
Constraint is modelled separately for IE and NI, interval by interval, as the available wind above each region’s effective network limit. The limit is not fixed: it varies from hour to hour, standing in for the local constraint groups the model does not represent, along with outages and system conditions. For region r in forecast year t, the expected constraint for available wind x is:
〖"Con" 〗_r (x)=E[max(0, x-L_(r,t) η)],  η∼"Lognormal" (0, σ_r^2 ),  r∈{"IE","NI"}
which has a closed form (the put-option formula, with the limit as the underlying and available wind as the strike):
〖"Con" 〗_r (x)=x Φ(-d_2 )-L_(r,t) e^(σ_r^2/2) Φ(-d_1 ),  d_1=(ln(L_(r,t)/x)+σ_r^2/2)/σ_r , d_2=d_1-σ_r
	x: the region’s available wind in the interval (MW).
	Lr,t: the region’s median effective limit in year t (MW). In half of hours the network can take more than L, in half less.
	σ: how much the limit varies from hour to hour. A large value means constraint often happens at moderate output, when local areas are windy even though the regional total is not.
	Φ: the standard normal cumulative distribution.
How L and σ are derived: from the region’s hourly records (available MW and constrained MW for every hour of the fit years). Two conditions pin them down. First, total energy must match: for any σ, lowering L always increases modelled constraint, so exactly one L makes the modelled total equal the recorded total (found by bisection). Second, the hourly pattern must match as closely as possible: a small σ concentrates constraint sharply in the windiest hours and a large σ spreads it into moderate hours, so the σ with the smallest hourly squared error is kept. No separate calibration factor is needed; an earlier version fitted L and σ first and then scaled by a factor k of 1.1–1.5, which fitted no better and slightly exaggerated how fast constraint grows.
What L represents: not a physical line rating, but an effective, aggregate limit: roughly how much of the region’s wind the network can typically carry, blending every local bottleneck. It depends on where wind is connected as well as on the grid, so it can fall when new capacity connects behind existing bottlenecks. Example: with IE’s 2025 fit (L = 4,203 MW, σ = 0.90), an hour with 3,000 MW available meets the limit about 35% of the time.
Regional split: the all-island 15-minute availability is divided between IE and NI. Existing capacity keeps today’s split s0 (IE share of availability in the latest full year, about 81%); capacity added after 2026 follows the scenario’s new-build share s_new:
x_("IE" ,i,t)=s_t x_(i,t),  x_("NI" ,i,t)=(1-s_t ) x_(i,t),  s_t=(s_0 C_0+s_"new"  (C_t-C_0 ))/C_t 
Network reinforcement: each region’s limit changes at its own annual rate g (Section 3), compounded from the last fitted year, plus any one-off steps ΔL in REINFORCEMENT_STEPS_MW:
L_(r,t)=L_(r,0)×(1+g_r )^( t-t_"fit"  )+∑_(s≤t)^▒Δ L_(r,s)
Annual constraint: for each weather year, both regions’ constraint is summed over every interval and divided by all-island available wind, then averaged across weather years. The results table reports each region’s constraint as a share of its own wind (Con_IE_%, Con_NI_%), each region’s contribution in percentage points of all-island wind (GridCon_IE_pts, GridCon_NI_pts) and their sum (GridCon_%):
"GridCon %" (t)=100×(∑_i^▒[〖"Con" 〗_"IE"  (x_("IE" ,i,t) )+〖"Con" 〗_"NI"  (x_("NI" ,i,t) )] )/(∑_i^▒x_(i,t) )
How capacity drives constraint: growth pushes the whole availability distribution up, so more intervals cross the limit and those already above it go deeper. With IE’s 2021–2025 fit and a fixed limit, constraint rises from 5.1% of available wind at today’s capacity to 11.5% at 1.5×, 17.9% at 2× and 29.1% at 3×. When capacity and the limit grow at the same rate, the percentage levels off.
Assumptions:
	New capacity in each region sits behind the same mix of bottlenecks as today (σ is held at its fitted value).
	The per-GW availability profile is the current all-island fleet’s and is the same in both regions. Offshore wind, with different timing, is not represented separately.
	Demand does not affect constraint in the model, only SNSP curtailment.
	Each reinforcement rate is one number standing in for a region’s whole grid development plan, so results should be shown as a range of scenarios. The effective limit has moved about 10–20% a year historically, which is the source of the forecast band.
Why the power law was replaced: the original formula, 10.0% × (Scaling Ratio)^0.75, used one fixed elasticity that was never fitted, ignored weather and the network, and blended grid response with an assumed amount of reinforcement. The fitted model separates them and is tested against data (Section 4).

C. Operational SNSP Curtailment
In 15-minute resolution, operational curtailment occurs whenever the wind left after network constraint (Section 5B) exceeds the user-configured system limit. The annual loop and the daily charts both apply constraint first and SNSP second: 

"Max Allowed Wind (MW)"="Scaled Demand (MW)"×"snsp_limit_fraction" 
"Excess (MW)"=max⁡(0,"Post-Constraint Wind (MW)" -"Max Allowed Wind (MW)" )


D. Usable Generation & Capacity Factor (Interval-Summed Dispatch)
Usable wind is summed directly from the 15-minute dispatch: available wind, less IE and NI constraint, capped at the SNSP ceiling. Each weather year is a sample of days, so the sum is scaled to a full year by that sample’s length. The fixed "other" curtailment is then subtracted, so generation is consistent with the RawCurt_% column:
"Usable Gen" (t)=∑_i^▒min (x_(i,t)-〖"Con" 〗_(i,t), "snsp_limit_fraction" ×D_(i,t) )×Δt×365.25/"days in sample"  - "Other %"×"Avail" (t)
Capacity factor is reported from the result rather than assumed:
"CF" (t)="Usable Gen" (t)/("Capacity" (t)×8760)
This replaces the earlier approach, which scaled 2026 generation by capacity and an "efficiency factor" that included an assumed capacity-factor decline (Scaling Ratio^−0.12). That decline counted losses already captured by constraint and curtailment. Wind % of demand is reported as calculated each year, so it can fall when losses outpace new capacity (an earlier version held it at its previous peak). The monthly charts (Graphs 1, 2 and 6) are built from the same interval dispatch, so losses appear in the months where they happen, and all charts share one weather-year assignment.

6. Daily 15-Minute Dispatch Down Engine
For operational daily profiles, the model separates the two primary components of Dispatch Down on a 15-minute timestep: Constraints & Curtailment, and applies the following hierarchy: 

Top Boundary (Available Wind Potential): The maximum theoretical generation output based on prevailing weather conditions and installed capacity.
First Reduction (Grid Bottleneck Constraint): The top section is trimmed by the expected constraint from the IE and NI network-limit models (Section 5B), each applied to its share of available wind. Constraint appears mainly in intervals where a region’s wind approaches or exceeds its effective limit, leaving the Constrained Available Wind.
Second Reduction (SNSP Curtailment): The constrained wind profile is capped against the user-configured operational SNSP limit line. Any generation exceeding this stability limit is clipped as SNSP curtailment.
Bottom Boundary (Usable Dispatched Wind): The remaining volume successfully delivered to the grid down to the Zero MW baseline.


	Grid Bottleneck Constraint (MW): calculated first in every 15-minute interval as the sum of the IE and NI constraint, using that year’s limits (shown in each chart’s text box, with the constraint split between IE and NI): 
"Grid Constraint (MW)"=〖"Con" 〗_"IE"  (s_t×"Available Wind (MW)" )+〖"Con" 〗_"NI"  ((1-s_t )×"Available Wind (MW)" )

"Constrained Available Wind (MW)"="Available Wind (MW)"-"Grid Constraint (MW)" 

	SNSP Curtailment (MW): Applied to the remaining constrained wind profile whenever it exceeds the user-selected SNSP limit line: 
"SNSP Limit (MW)"="System Demand (MW)"×"snsp_limit_fraction" 
"SNSP Curtailment (MW)"=max⁡(0,"Constrained Available Wind (MW)" -"SNSP Limit (MW)" )

	Usable Dispatched Wind (MW): The remaining wind power delivered to the grid: 

"Usable Wind (MW)"=min⁡("Constrained Available Wind (MW)" ,"SNSP Limit (MW)" )

Summary of Parameters
Parameter	Baseline / Formula	Description
Baseline Fleet	6.51" GW" 	Current All-Island SEM installed wind capacity (2026 anchor). 

Demand Expansion	+1.87" TWh/year" 	Decarbonisation electrification demand scaling (42.0" TWh"  in 2026 →86.88" TWh" in 2050). 
Build Rate (Input)	Prompt / scenarios.csv (0.534 GW/yr default)	Annual wind build-out; one full increment added each year from 2027.
SNSP Limit (Input)	Prompt / scenarios.csv (75% default)	Operational SNSP ceiling, applied to wind left after constraint.
IE / NI Reinforcement (Inputs)	Prompt / scenarios.csv (0%/yr default)	Annual % change in each region’s effective limit; negative = continued tightening. One-off steps via REINFORCEMENT_STEPS_MW.
Constraint Model	E[max(0, x − L·η)] per region	IE and NI fitted separately on 2024–2026 hourly records (IE L ≈ 4,275 MW, σ ≈ 0.89; NI printed at run time). Energy matched exactly; no calibration factor.
New-Build IE Share (Input)	Prompt / scenarios.csv (≈81% default)	Share of capacity added after 2026 that connects in IE; the rest connects in NI.
Forecast Band	± typical one-year-ahead hindcast error	GridCon_Low_% / GridCon_High_%; about ±15% on the IE data.
Scenario File	scenarios.csv (optional)	Runs every row without prompts; outputs per scenario plus scenario_summary.csv.
Weather Loop	2019–2025	Rolling 6-year historical weather dataset preserving 15-minute seasonality. 


 

