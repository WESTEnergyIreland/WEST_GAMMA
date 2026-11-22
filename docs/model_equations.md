# Gamma: model equations

Source for Supplementary Section S2 and the equations in Section 4 of the Phase 1 paper. Every equation here is implemented in `Gamma.py`; the function is named after each block. 8 November 2026.

## Notation

| Symbol | Meaning | Unit |
|---|---|---|
| $t$ | 15-minute interval, $\Delta t = 0.25$ h | |
| $w$ | weather year, $w \in \mathcal{W} = \{2014,\dots,2026\}$ | |
| $y$ | simulated year | |
| $z$ | onshore zone (NW, W, MID, NE, SW, SE, NI) | |
| $x_{z,t}$ | available wind and solar output in zone $z$ | MW |
| $X_t$ | all-island available wind and solar, including offshore | MW |
| $H_z$ | median effective network limit (headroom) of zone $z$ | MW |
| $\sigma_z$ | log-spread of the effective limit | – |
| $\eta$ | lognormal factor, $\ln\eta \sim N(0,\sigma^2)$ | – |
| $C_{z,t}$ | expected constraint in zone $z$ | MW |
| $D_t$ | electricity demand (generated basis) | MW |
| $s$ | SNSP limit | – |
| $P^{\min}$ | minimum synchronous output (150 MW per required unit) | MW |
| $L_t$ | operating ceiling on non-synchronous output | MW |
| $P^{ch}_t, P^{dis}_t$ | battery charge and discharge | MW |
| $S_t$ | battery state of charge | MWh |
| $\bar P, \bar E$ | battery power and energy rating | MW, MWh |
| $\eta^{ch}, \eta^{dis}$ | charge and discharge efficiency (0.90 each) | – |
| $V_t$ | wind and solar delivered to demand | MW |
| $K_t$ | curtailment by the operating ceiling | MW |
| $F_t$ | firm (synchronous) output | MW |

## 1. Network constraint (`expected_constraint_mw`)

The effective limit of zone $z$ in an interval is $H_z\eta$. Output above it is constrained. The expected constraint for available output $x$ is

$$C_z(x) = \mathbb{E}\big[\max(0,\ x - H_z\eta)\big], \qquad \ln\eta \sim N(0,\sigma_z^2). \tag{2}$$

**Derivation of the closed form.** Write $\eta = e^{\sigma Z}$ with $Z \sim N(0,1)$. Constraint is positive when $x > H e^{\sigma Z}$, that is when $Z < a$, with

$$a = \frac{\ln(x/H)}{\sigma}.$$

Then

$$C(x) = \int_{-\infty}^{a} \big(x - H e^{\sigma z}\big)\,\phi(z)\,dz = x\,\Phi(a) - H \int_{-\infty}^{a} e^{\sigma z}\phi(z)\,dz .$$

Completing the square, $e^{\sigma z}\phi(z) = e^{\sigma^2/2}\,\phi(z-\sigma)$, so the second integral is $e^{\sigma^2/2}\,\Phi(a-\sigma)$ and

$$C(x) = x\,\Phi(a) - H\,e^{\sigma^2/2}\,\Phi(a - \sigma). \tag{3}$$

Properties used in the paper:
- $C'(x) = \Phi(a)$. Each further MW in the zone is constrained with probability $\Phi(a)$, the probability that the limit is below $x$. $C$ is increasing and convex in $x$, so marginal constraint exceeds average constraint.
- $C'(H) = \Phi(0) = 1/2$: at the median limit half of each extra MW is lost.
- $0 \le C(x) \le x$, $C(x) \to 0$ as $x/H \to 0$, and $C(x) \to x - H e^{\sigma^2/2}$ as $x/H \to \infty$, where $He^{\sigma^2/2}$ is the mean limit.
- $\partial C/\partial H = -e^{\sigma^2/2}\Phi(a-\sigma) < 0$: reinforcement lowers constraint at every output level.

Before 8 November 2026 the code used $x\Phi(a+\sigma/2) - He^{\sigma^2/2}\Phi(a-\sigma/2)$. That is not the expectation of any lognormal and went negative for $x$ below about $0.3$–$0.4\,H$ (clipped to zero). It was corrected on 8 November 2026; see `CHANGELOG.md`.

Zonal output shares installed capacity: $x_{z,t} = X^{on}_t\,G^{on}_z/G^{on} + X^{s}_t\,G^{s}_z/G^{s}$, where $G$ is installed GW. Offshore wind has its own connection, rated at its installed capacity, so only output above that rating is constrained (none at a ratio of 1). Constraint in a zone is split between wind and solar in proportion to their available output.

## 2. Estimation of $H$ and $\sigma$ (`fit_constraint_model`, `calibrate_headroom`)

For each jurisdiction $r$ (IE, NI) and set of fit years $\mathcal{T}$, with recorded hourly available output $x_t$ and constraint $c_t$:

$$\hat\sigma_r = \arg\min_{\sigma \in [0.2,\,2.5]} \ \frac{1}{|\mathcal{T}|}\sum_{t\in\mathcal{T}} \big(C(x_t; H(\sigma), \sigma) - c_t\big)^2 \quad\text{subject to}\quad \sum_{t\in\mathcal{T}} C(x_t; H(\sigma),\sigma) = \sum_{t\in\mathcal{T}} c_t . \tag{S2.1}$$

The constraint defines $H(\sigma)$ uniquely, because $\sum_t C$ is strictly decreasing in $H$; it is solved by Brent's method on $\ln H$, and $\sigma$ by bounded scalar minimisation. The estimator is a constrained least-squares (method-of-moments plus hourly fit) estimator: annual constrained energy is matched exactly and $\sigma$ sets the shape across hours. Every IE zone takes $\hat\sigma_{IE}$ (fitted on 2024–2026); NI takes $\hat\sigma_{NI}$. Each zone's headroom then solves

$$\sum_{t \in 2025} C(x_{z,t}; H_z, \hat\sigma) = c_z \sum_{t \in 2025} x_{z,t}, \tag{4}$$

where $c_z$ is the zone's recorded 2025 constraint share.

In projections $H_{z,y} = H_{z,2026}\,g_{r(z),y} + \Delta_{z,y}$, where $g$ is the growth index of the network path (`zonal_headroom_by_year.csv`) and $\Delta$ is a step (950 MW in NI from 2032 for the second North–South interconnector). From 2036, $H_{z,y} = \infty$ ($C = 0$) in the bounding case.

## 3. Operating ceiling and curtailment (`dispatch`)

Post-constraint output is $\tilde X_t = X_t - \sum_z C_{z,t}$. With net interconnector flow zero and battery charging counted as demand, the ceiling on non-synchronous output is

$$L_t = \min\big(s\,(D_t + P^{ch}_t),\ D_t + P^{ch}_t - P^{\min}\big). \tag{5}$$

Each interval is solved in this order.

1. **Potential curtailment** with no charging: $K^0_t = \max\big(0,\ \tilde X_t - \min(sD_t,\ D_t - P^{\min})\big)$.
2. **Charge** from the part of $K^0_t$ the fleet can reach:
$$P^{ch}_t = \min\Big(\bar P,\ \frac{\bar E - S_{t-1}}{\eta^{ch}\Delta t},\ \alpha\,\frac{\tilde X_t}{X_t}\,K^0_t,\ \tilde X_t,\ \frac{sD_t}{1-s}\Big), \qquad \alpha = \min\big(1,\ 1.10\,h + 0.90\,(1-h)\big),$$
where $h$ is the co-located share of battery MW. The factor $\tilde X_t/X_t$ stands for the share of surplus that is not behind a network constraint.
3. **Delivered and curtailed output**. The wind and solar charging the battery are non-synchronous output, so they count against $L_t$ as well as adding to its denominator:
$$V_t = \min\big(\tilde X_t - P^{ch}_t,\ L_t - P^{ch}_t,\ D_t\big), \qquad K_t = \tilde X_t - P^{ch}_t - V_t .$$
Before 22 November 2026 the second term was $L_t$, so in charging intervals SNSP could exceed $s$ and synchronous output fall below $P^{\min}$. The SNSP diagnostic is now $(V_t + P^{ch}_t + P^{dis}_t)/(D_t + P^{ch}_t)$, with exports and imports added where they are dispatched.
Curtailment is shared between wind and solar in proportion to their post-constraint output.
4. **Discharge**, only when not charging:
$$P^{dis}_t = \min\Big(\bar P,\ \frac{\eta^{dis} S_{t-1}}{\Delta t},\ D_t - I^{rec}_t - V_t,\ sD_t - I^{rec}_t - V_t,\ D_t - P^{\min} - I^{rec}_t - V_t\Big)^{+},$$
where $I^{rec}_t$ is recorded HVDC imports in the historical flow sensitivity (zero in all projections). Before 22 November 2026 the SNSP and floor terms left out $I^{rec}_t$.
5. **State of charge**:
$$S_t = \min\Big(\bar E,\ \max\big(0,\ S_{t-1} + \eta^{ch}P^{ch}_t\Delta t - P^{dis}_t\Delta t/\eta^{dis}\big)\Big), \qquad S_0 = 0.5\,\bar E .$$
6. **Firm output**: $F_t = D_t - V_t - P^{dis}_t$.

Dispatch down in the interval is $\sum_z C_{z,t} + K_t$, and by construction
$$X_t = \sum_z C_{z,t} + K_t + P^{ch}_t + V_t .$$

**Reporting split (EirGrid's order).** The part of constraint that would be curtailed anyway, $\min\big(\sum_z C_{z,t},\ \max(0, X_t - L_t)\big)$, is reported as curtailment in the EirGrid-order columns. Totals are unchanged.

## 4. Residual curtailment (removed)

From 14 November 2026 Gamma has no residual curtailment. Curtailment is only what the operating ceiling $L_t$ removes, and delivered energy is what the dispatch delivers. The recorded high frequency, RoCoF and other curtailment that the ceiling does not reproduce is not modelled (see `CHANGELOG.md`). Equation (6) is not used.

## 5. Weather years and annual results

For each simulated year $y \ge 2027$, the dispatch is run once per weather year $w$, with that year's profiles scaled to year $y$'s capacity and demand. Energy results are the mean over $w$:
$$\bar Q_y = \frac{1}{|\mathcal W|}\sum_{w} \sum_{t \in w} Q_{t,w}\,\Delta t \cdot \frac{8760}{n_w\Delta t}.$$
2026 uses its own weather year for energy and all weather years for the adequacy quantities below.

## 6. Demand (`scenario_demand_mw`)

$$D_t = \underbrace{d_t\,\frac{(E_y - E^{hp}_y)\cdot 10^6/8760}{\bar d}}_{\text{recorded shape}} + \underbrace{\frac{\omega_t}{\sum_t \omega_t}\,\frac{E^{hp}_y\cdot 10^6}{\Delta t}\cdot\frac{n\Delta t}{8760}}_{\text{added heat pumps}}, \qquad \omega_t = \frac{\max(0,\ 15.5 - T_t)}{1 + 0.025\,(T_t - \bar T)},$$

where $d_t$ is recorded demand in weather year $w$, $E_y$ is annual demand (TWh), $E^{hp}_y$ is heat-pump electricity added since 2026, $T_t$ is hourly temperature at Dublin Airport and $\bar T$ is its heating-weighted mean (the COP factor in the denominator is clipped to $[0.5, 1.5]$). Heat and transport electricity are capped at $E^{heat}/\mathrm{COP} = 70.6/3.5$ TWh and $E^{tr}/3.0 = 62.2/3.0$ TWh.

Annual demand (`demand_for_year`) is background demand plus heat and transport electricity added since 2026, each capped:
$$E_y = B_y + \min\big(\bar H,\ H_0 + n\,g^{h}\big) - H_0 + \min\big(\bar T,\ T_0 + n\,g^{tr}\big) - T_0, \qquad n = y - 2026,$$
where $\bar H$ and $\bar T$ are the caps above. Without a demand path $B_y = E_{2026} + n\,g^{b}$. With a path $P_y$ (`scenario_path` column `demand_twh`) $B_y = P_y - n\,(\hat g^{h} + \hat g^{tr})$, where $\hat g$ are the heat and transport rates the path was built with (`path_heat_growth_twh_per_year`, `path_transport_growth_twh_per_year`; blank means the scenario's own rates). Before 22 November 2026 a sensitivity that changed $g^{h}$ or $g^{tr}$ kept $E_y = P_y$ to the path's last year, so faster electrification displaced background demand.

## 7. Firm capacity

$$F^{cap}_y = \max_{w \in \mathcal W}\ \max_{t \in w}\ F_{t,w} \;+\; \max(\text{largest unit},\ \text{largest interconnector}) \;+\; 500\ \text{MW}.$$

Interconnectors get no capacity credit in this figure.

## 8. Firm tranches and fleet efficiency (`firm_tranche_split`, `fleet_efficiency`)

For each weather year let $\beta$ be the level that firm output reaches or exceeds in 1,500 hours a year (the $k$-th largest $F_t$, $k = \lceil n \cdot 1500/8760\rceil$). Then
$$E^{base} = \sum_t \min(F_t, \beta)\,\Delta t, \qquad E^{peak} = \sum_t F_t\,\Delta t - E^{base}, \qquad p = \frac{E^{peak}}{E^{base}+E^{peak}},$$
$$\eta^{fleet} = \left(\frac{1-p}{0.55} + \frac{p}{0.38}\right)^{-1}.$$

## 9. Energy shares

Electricity from firm plant counts as gas burnt, $G_y = F^{cons}_y/\eta^{fleet}_y$. With remaining fossil heat $H^{f}_y$ and transport fuel $T^{f}_y$, ambient heat $A^{hp}_y = (\mathrm{COP}-1)E^{heat,el}_y$, and wind, solar and battery output consumed $V^{cons}_y$:

$$\text{fossil share of primary energy} = \frac{H^f_y + T^f_y + G_y}{H^f_y + T^f_y + G_y + A^{hp}_y + V^{cons}_y + M_y} .$$

The share of gross final energy is the same with $G_y$ replaced by $F^{cons}_y$.

The electricity-equivalent share counts fuel for heat and transport not yet electrified as the electricity that would replace it, and firm and imported electricity as electricity delivered. Ambient heat is not counted, because the heat pump's electricity is already in $V^{cons}_y$ or $F^{cons}_y$:

$$\text{fossil share, electricity equivalent} = \frac{H^f_y/\mathrm{COP} + T^f_y/k^{tr} + F^{cons}_y}{H^f_y/\mathrm{COP} + T^f_y/k^{tr} + F^{cons}_y + V^{cons}_y + M_y},$$

with $\mathrm{COP} = 3.5$ and the transport displacement factor $k^{tr} = 3.0$. It is the fossil share of the electricity a fully electrified system would need, and removes the primary energy fallacy for heat and transport as well as for firm plant (output `Elec_Equiv_Fossil_Share_Pct`). Full decarbonisation is the first $y$ with fossil share $\le 10\%$. $M_y$ is the electricity imported in the dispatch: zero in the main runs, which have no interconnector flows, and the dispatched imports in the interconnector runs (`GAMMA_IC_DISPATCH=1`). Until 12 November 2026 the main runs multiplied the share by $(1 - m)$ with $m = 0.04$, a fixed allowance for imported electricity; `GAMMA_IMPORT_SHARE=4` restores it and multiplies every fossil share by 0.96.

The useful-energy share (added 20 November 2026) is a simple proxy for the energy services delivered. Heat counts as heat delivered: remaining fossil heat fuel at its energy content, and heat-pump heat at $\mathrm{COP}$ times its electricity, $E^{heat}_y$. Remaining transport fuel counts at $1/k^{tr}$, the work an electric vehicle would do with it. All other electricity counts as delivered. With demand $D_y$, heat-pump electricity $E^{heat,el}_y$ and transport electricity $E^{tr,el}_y$:

$$U_y = (D_y - E^{heat,el}_y - E^{tr,el}_y) + E^{heat}_y + H^f_y + E^{tr,el}_y + T^f_y/k^{tr}, \qquad \text{fossil share of useful energy} = \frac{H^f_y + T^f_y/k^{tr} + F^{cons}_y}{U_y}$$

(outputs `Useful_Energy_TWh`, `Useful_Fossil_Share_Pct`). Firm electricity counts at the electricity delivered even where it drives heat pumps or vehicles, so the share is a proxy, not an end-use balance.

Wind and solar as a share of demand (`RES_E_RED_%`, renamed `Modelled_RES_E_Pct`) is $(W_y + S_y + B^{dis}_y)/D_y$, where $W_y$ and $S_y$ are wind and solar delivered directly and $B^{dis}_y$ is battery discharge. Batteries charge only from output that would otherwise be curtailed, and that charging is not in $W_y$ or $S_y$, so the discharge is wind and solar delivered later. The paper reports this share from 20 November 2026; before, it reported $(W_y + S_y)/D_y$ (`Share_of_Demand_%` in `summary_total.csv`).

## 10. Hydrogen for firm plant

$$E^{elec}_{H_2,y} = \frac{F_y}{\eta^{fleet}_y\,\eta^{el}}, \qquad \eta^{el} = 0.70 .$$

A lower bound: compression, storage and transport are excluded.

## 11. Worst gas day (`gas_power_fuel_mw`)

For day $d$, with non-gas firm output $N = 400$ MW and $\beta'$ the tranche level of Section 8 recomputed on $(F_t - N)^+$:
$$\text{Gas}_d = \frac{1}{0.90}\sum_{t\in d}\Big(\frac{\min(F_t - N, \beta')^+}{0.55} + \frac{(F_t - N - \beta')^+ - O_t}{0.38}\Big)\Delta t + 37.6 + 6.51\,\mathrm{HDD}_d\,\lambda_y + 5,$$
where $O_t$ is peaking output met by Moneypoint on oil (to 2029), $\lambda_y$ is the share of non-power heat not yet electrified and 0.90 converts LHV to GCV. The worst day is $\max_{w}\max_d \text{Gas}_d$, compared with daily entry capacity (Moffat 433.4 GWh/d plus Corrib, falling 15.6% a year).

## 12. Validation measures

For predicted $\hat c$ and recorded $c$ constraint energy: error $= 100(\hat c - c)/c$ (%); for shares of available energy, error $= \hat c - c$ (percentage points). The hindcast band for each jurisdiction is the mean absolute one-year-ahead error over 2022–2026.

## 13. Two properties of the model

**Proposition 1 (network relief moves losses to curtailment).** Without batteries, delivered output in an interval is $V = \min(X - C,\ L,\ D)$. Reducing constraint from $C$ to $C' < C$ raises delivered output by
$$\Delta V = \min(X - C', L, D) - \min(X - C, L, D) \le C - C',$$
with $\Delta V = 0$ whenever $X - C \ge \min(L, D)$. The rest of the released energy, $(C - C') - \Delta V$, is curtailed. Total dispatch down $X - V \ge X - \min(L, D)$ for any network. So network reinforcement can lower dispatch down only in intervals where post-constraint output is below the operating ceiling, and the floor on dispatch down is set by $s$, $P^{\min}$ and demand alone. The projections in Section 7.3 quantify this; the result is not an artefact of applying constraint first, because the floor $X - \min(L,D)$ does not depend on the order.

**Proposition 2 (using expected constraint understates dispatch down).** Total dispatch down for a realised constraint $C^\ast$ is $\max(C^\ast,\ X - \min(L,D))$, which is convex in $C^\ast$. By Jensen's inequality,
$$\mathbb{E}\big[\max(C^\ast, X - \min(L,D))\big] \ \ge\ \max\big(\mathbb{E}[C^\ast],\ X - \min(L,D)\big),$$
so a dispatch run on the expected constraint gives a lower bound on expected dispatch down in each interval. The size of the gap is reported in Supplementary S2.3.
