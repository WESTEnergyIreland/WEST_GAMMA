"""Figure 9 of the Phase 1 paper: 2 x 2 showcase of Gamma outputs, no data boxes, one legend.

(a) EirGrid_Extended, dunkelflaute day       (b) EirGrid_Extended, maximum wind (storm) day
(c) EirGrid_Extended, monthly 2019 to end     (d) Historical_Trend, monthly 2019 to end

Usage: python analysis/figure9_showcase.py <outputs> [end year] [day year]
Writes analysis/output/paper/Figure_9.pdf and .png. daily_panel() is also used by figure4_dunkelflaute.py.
<outputs> holds EirGrid_Extended/ and Historical_Trend/ from a Gamma.py run with charts on.
The daily panels read the chart_Daily_Dunkelflaute_<year>.csv and chart_Daily_Absolute_Storm_<year>.csv
files Gamma writes (it picks the days two years before target_year, so a run to 2035 gives 2033 days).
[day year] chooses among them if more than one exists; [end year] cuts the monthly panels
(default 2050, the paper horizon; the days need a run with target_year 2052).
"""
import glob, os, re, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_figures_common import save, EE_LABEL, HT_LABEL

OUT = sys.argv[1] if __name__ == '__main__' else None
END = int(sys.argv[2]) if __name__ == '__main__' and len(sys.argv) > 2 else 2050   # paper horizon
DAY_YEAR = int(sys.argv[3]) if __name__ == '__main__' and len(sys.argv) > 3 else None
EG, HT = 'EirGrid_Extended', 'Historical_Trend'
C = dict(wind='#90EE90', wind_e='#2CA02C', solar='#FFD54F', solar_e='#E0A800', dis='#9467BD',
         dis_e='#6F42A5', chg='#4C78A8', chg_e='#2F5D8A', firm='#D3D3D3', curt='#D62728', con='#FF8C00')


def daily_file(kind):
    files = sorted(glob.glob(os.path.join(OUT, EG, f'chart_Daily_{kind}_*.csv')))
    if DAY_YEAR:
        files = [f for f in files if f.endswith(f'_{DAY_YEAR}.csv')]
    if not files:
        sys.exit(f"No chart_Daily_{kind}_*.csv in {os.path.join(OUT, EG)}: run Gamma.py with charts on")
    return files[-1]


def daily_panel(ax, path, title):
    d = pd.read_csv(path)
    t = d['time_h']
    w, s = d['usable_wind_mw'], d['usable_solar_mw']
    top = w + s
    ax.fill_between(t, 0, w, color=C['wind'], edgecolor=C['wind_e'], lw=0.6)
    ax.fill_between(t, w, top, color=C['solar'], edgecolor=C['solar_e'], lw=0.5)
    ax.fill_between(t, top, top + d['battery_discharge_mw'], color=C['dis'], edgecolor=C['dis_e'], lw=0.5)
    stack = top + d['battery_discharge_mw']
    ax.fill_between(t, stack, d['demand_incl_charging_mw'], where=d['demand_incl_charging_mw'] > stack,
                    color=C['firm'], lw=0, zorder=0)
    ax.fill_between(t, 0, -d['battery_charge_mw'], color=C['chg'], edgecolor=C['chg_e'], lw=0.5, alpha=0.8)
    ax.fill_between(t, top, top + d['curtailment_oversupply_mw'], facecolor='none', edgecolor=C['curt'],
                    hatch='///', lw=0.6)
    ax.fill_between(t, top + d['curtailment_oversupply_mw'], d['available_wind_solar_mw'],
                    where=d['grid_constraint_mw'] > 0, facecolor='none', edgecolor=C['con'], hatch='...', lw=0.6)
    ax.plot(t, d['demand_incl_charging_mw'], color='black', lw=1.8)
    ax.plot(t, d['available_wind_solar_mw'], color=C['wind_e'], lw=1.4, ls='--')
    ax.axhline(0, color='0.4', lw=0.7)
    r = d.iloc[0]
    date = pd.Timestamp(int(r['year']), int(r['month']), int(r['day'])).strftime('%-d %B %Y')
    ax.set_title(f"{title}, {date}\nwind {r['wind_gw']:.1f} GW, solar {r['solar_gw']:.1f} GW, "
                 f"batteries {r['battery_mw'] / 1000:.1f} GW / {r['battery_mwh'] / 1000:.1f} GWh",
                 loc='left', fontsize=11, fontweight='bold')
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 25, 4)])
    ax.set_ylabel('MW')
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))


def monthly_panel(ax, sc, title, end):
    m = pd.read_csv(os.path.join(OUT, sc, 'chart_monthly_overview.csv'), parse_dates=['date'])
    m = m[m['date'].dt.year <= end]
    w = m['usable_wind_gwh'].fillna(0)
    s = w + m['usable_solar_gwh'].fillna(0)
    st = s + m['storage_discharge_gwh'].fillna(0)
    ax.fill_between(m['date'], 0, w, color=C['wind'], edgecolor=C['wind_e'], lw=0.6)
    ax.fill_between(m['date'], w, s, color=C['solar'], edgecolor=C['solar_e'], lw=0.5)
    ax.fill_between(m['date'], s, st, color=C['dis'], edgecolor=C['dis_e'], lw=0.5)
    ax.fill_between(m['date'], 0, -m['storage_charge_gwh'].fillna(0), color=C['chg'], edgecolor=C['chg_e'],
                    lw=0.5, alpha=0.8)
    ax.fill_between(m['date'], st, m['demand_gwh'].where(m['demand_gwh'] > st, st), color=C['firm'], lw=0,
                    zorder=0)
    ax.plot(m['date'], m['demand_gwh'], color='black', lw=1.6)
    ax.axhline(0, color='0.4', lw=0.7)
    ax.axvline(pd.Timestamp(2026, 1, 1), color='0.5', lw=0.8, ls=':')
    ax.set_title(f"{title}, January 2019 to December {end}", loc='left', fontsize=11, fontweight='bold')
    ax.set_xlim(m['date'].iloc[0], m['date'].iloc[-1])
    # About eight to ten labels whatever the span: every 2 years to 2035, 5 to 2059, 10 beyond.
    span = end - m['date'].iloc[0].year
    step = 2 if span <= 16 else 5 if span <= 40 else 10
    ax.xaxis.set_major_locator(mdates.YearLocator(step))
    ax.xaxis.set_minor_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.set_ylabel('GWh per month')
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:,.0f}'))


def legend_handles():
    return [Patch(facecolor=C['wind'], edgecolor=C['wind_e'], label='Wind delivered'),
            Patch(facecolor=C['solar'], edgecolor=C['solar_e'], label='Solar delivered'),
            Patch(facecolor=C['dis'], edgecolor=C['dis_e'], label='Battery discharge'),
            Patch(facecolor=C['chg'], edgecolor=C['chg_e'], label='Battery charging (negative)'),
            Patch(facecolor=C['firm'], label='Firm plant (gas today)'),
            Patch(facecolor='none', edgecolor=C['curt'], hatch='///', label='Curtailment and surplus'),
            Patch(facecolor='none', edgecolor=C['con'], hatch='...', label='Network constraint')]


if __name__ == '__main__':
    last = min(int(pd.read_csv(os.path.join(OUT, sc, 'chart_monthly_overview.csv'))['year'].max()) for sc in (EG, HT))
    end = min(END, last) if END else last

    fig, ax = plt.subplots(2, 2, figsize=(14, 9.5))
    daily_panel(ax[0, 0], daily_file('Dunkelflaute'), f'(a) {EE_LABEL}: cold, still day')
    daily_panel(ax[0, 1], daily_file('Absolute_Storm'), f'(b) {EE_LABEL}: windiest day')
    monthly_panel(ax[1, 0], EG, f'(c) {EE_LABEL}', end)
    monthly_panel(ax[1, 1], HT, f'(d) {HT_LABEL}', end)
    ylim = max(a.get_ylim()[1] for a in ax[1]), min(a.get_ylim()[0] for a in ax[1])
    for a in ax[1]:
        a.set_ylim(ylim[1], ylim[0])
    for a in ax.flat:
        a.grid(axis='y', color='0.9')
        a.spines[['top', 'right']].set_visible(False)

    handles = [Patch(facecolor=C['wind'], edgecolor=C['wind_e'], label='Wind delivered'),
               Patch(facecolor=C['solar'], edgecolor=C['solar_e'], label='Solar delivered'),
               Patch(facecolor=C['dis'], edgecolor=C['dis_e'], label='Battery discharge'),
               Patch(facecolor=C['chg'], edgecolor=C['chg_e'], label='Battery charging (negative)'),
               Patch(facecolor=C['firm'], label='Firm plant (gas today)'),
               Patch(facecolor='none', edgecolor=C['curt'], hatch='///', label='Curtailment and surplus'),
               Patch(facecolor='none', edgecolor=C['con'], hatch='...', label='Network constraint'),
               Line2D([], [], color='black', lw=1.8, label='Demand (incl. battery charging in a, b)'),
               Line2D([], [], color=C['wind_e'], lw=1.4, ls='--', label='Available wind and solar (a, b)')]
    fig.legend(handles=handles, loc='lower center', ncol=5, frameon=False, fontsize=10)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, 9)
    print(f"monthly panels to {end}")
