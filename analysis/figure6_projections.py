"""Figure 6 of the Phase 1 paper: projections to 2100 for EirGrid_Extended and Historical_Trend.

Solid lines: the scenarios as defined (zonal network limits removed from 2036).
Dashed lines: the same scenarios with the published network path after 2035 (reinforcement_steps
'NI:2032:950' only), for comparison. Panel (d): electricity to run the firm plant on green hydrogen
(70% electrolysis, burnt at each year's firm fleet efficiency; Firm_On_H2_Electrolysis_TWh), and all
wind and solar dispatched down (available x total dispatch down).

Usage: python analysis/figure6_projections.py <outputs, no limits> <outputs, published path> <out.png>
where each outputs folder holds EirGrid_Extended/ and Historical_Trend/ from Gamma.py.
"""
import sys, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
NEW, BASE, out = sys.argv[1], sys.argv[2], sys.argv[3]
BLUE='#2a7bd9'; ORANGE='#e8673a'
def load(run, sc):
    t=pd.read_csv(f'{run}/{sc}/summary_total.csv').set_index('Year')
    t['DD_TWh']=t['Available_TWh']*t['Total_Loss_%']/100
    f=pd.read_csv(f'{run}/{sc}/forecast_results.csv').set_index('Year')
    t['H2_TWh']=f['Firm_On_H2_Electrolysis_TWh']
    return t
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
fig,ax=plt.subplots(2,2,figsize=(12,9.3))
panels=[('Share_of_Demand_%','(a) Delivered wind and solar,\n% of demand',(0,100)),
        ('Total_Loss_%','(b) Dispatched-down wind and solar,\n% of available',(0,70)),
        ('Overall_Fossil_Fuel_Pct','(c) Fossil fuel,\n% of primary energy',(0,100)),
        ('H2_TWh','(d) TWh: electricity to run firm plant on\nhydrogen (solid); all dispatched down (dotted)',(0,125))]
for k,(col,title,yl) in enumerate(panels):
    a=ax.flat[k]
    for sc,c in (('EirGrid_Extended',BLUE),('Historical_Trend',ORANGE)):
        n=load(NEW,sc); b=load(BASE,sc)
        a.plot(b.index,b[col],color=c,lw=1.4,ls='--',alpha=0.8)
        a.plot(n.index,n[col],color=c,lw=2.6)
        if col=='H2_TWh':
            a.plot(n.index,n['DD_TWh'],color=c,lw=2.2,ls=':')
    a.set_title(title,loc='left',fontweight='bold',fontsize=12)
    a.set_ylim(*yl); a.set_xlim(2026,2100)
    a.axvline(2035.5,color='0.55',lw=0.9,ls=(0,(2,2)))
    a.grid(axis='y',color='0.9'); a.spines[['top','right']].set_visible(False)
    if col=='Overall_Fossil_Fuel_Pct':
        a.axhline(10,color='0.25',lw=1.2,ls='-.'); a.text(2028,12,'Full decarbonisation threshold (10%)',fontsize=10,color='0.25')
ax.flat[0].text(2036.5,4,'network limits\nremoved from 2036',fontsize=9,color='0.4')
from matplotlib.lines import Line2D
h=[Line2D([],[],color=BLUE,lw=2.6),Line2D([],[],color=ORANGE,lw=2.6),Line2D([],[],color='0.4',lw=1.4,ls='--')]
fig.legend(h,['EirGrid’s plan, extended','Historical trend','Same pathway, published network path after 2035'],loc='lower center',ncol=3,frameon=False,fontsize=11)
fig.tight_layout(rect=(0,0.05,1,1)); fig.savefig(out,dpi=200)
