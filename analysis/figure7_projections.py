"""Figure 7 of the Phase 1 paper: projections for EirGrid Extended (EE) and Historical Trend (HT).

Solid lines: the scenarios as defined (zonal network limits removed from 2036).
Dashed lines: the same scenarios with the published network path after 2035 (reinforcement_steps
'NI:2032:950' only), for comparison. Panel (a): wind and solar consumed as a share of demand,
including what reaches demand through batteries (Modelled_RES_E_Pct). Panel (d): electricity to run
the firm plant on green hydrogen at 70% electrolyser efficiency and the modelled fleet efficiency
(Firm_On_H2_Electrolysis_TWh), and all wind and solar dispatched down (available x total dispatch down).

Usage: python analysis/figure7_projections.py <outputs, no limits> <outputs, published path> [end year]
Writes analysis/output/paper/Figure_7.pdf and .png.
where each outputs folder holds EirGrid_Extended/ and Historical_Trend/ from Gamma.py.
The x axis runs to [end year] if given, otherwise to the last year in the outputs (the
scenarios' target_year). An end year later than the outputs is cut back to the outputs.
"""
import os, sys, pandas as pd
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_figures_common import save, BLUE, ORANGE, EE_LABEL, HT_LABEL
NEW, BASE = sys.argv[1], sys.argv[2]
END_ARG = int(sys.argv[3]) if len(sys.argv) > 3 else None
def load(run, sc):
    t=pd.read_csv(f'{run}/{sc}/summary_total.csv').set_index('Year')
    t['DD_TWh']=t['Available_TWh']*t['Total_Loss_%']/100
    f=pd.read_csv(f'{run}/{sc}/forecast_results.csv').drop_duplicates('Year',keep='last').set_index('Year')
    t['H2_TWh']=f['Firm_On_H2_Electrolysis_TWh'].reindex(t.index)
    return t
SC=('EirGrid_Extended','Historical_Trend')
data={(r,sc):load(r,sc) for r in (NEW,BASE) for sc in SC}
last=min(int(t.index.max()) for t in data.values())
END=min(END_ARG,last) if END_ARG else last
START=min(int(t.index.min()) for t in data.values())
data={k:t.loc[t.index<=END] for k,t in data.items()}
fig,ax=plt.subplots(2,2,figsize=(12,9.3))
panels=[('Modelled_RES_E_Pct','(a) Wind and solar consumed, incl. via batteries,\n% of demand',(0,100)),
        ('Total_Loss_%','(b) Dispatched-down wind and solar,\n% of available',(0,70)),
        ('Overall_Fossil_Fuel_Pct','(c) Fossil fuel,\n% of Total Primary Energy (TPE)',(0,100)),
        ('H2_TWh','(d) TWh: electricity to run firm plant on\nhydrogen (solid); all dispatched down (dotted)',(0,125))]
for k,(col,title,yl) in enumerate(panels):
    a=ax.flat[k]
    for sc,c in zip(SC,(BLUE,ORANGE)):
        n=data[(NEW,sc)]; b=data[(BASE,sc)]
        a.plot(b.index,b[col],color=c,lw=1.4,ls='--',alpha=0.8)
        a.plot(n.index,n[col],color=c,lw=2.6)
        if col=='H2_TWh':
            a.plot(n.index,n['DD_TWh'],color=c,lw=2.2,ls=':')
    a.set_title(title,loc='left',fontweight='bold',fontsize=12)
    a.set_ylim(*yl); a.set_xlim(START,END)
    if END>2035: a.axvline(2035.5,color='0.55',lw=0.9,ls=(0,(2,2)))
    a.grid(axis='y',color='0.9'); a.spines[['top','right']].set_visible(False)
    if col=='Overall_Fossil_Fuel_Pct':
        a.axhline(10,color='0.25',lw=1.2,ls='-.'); a.text(2028,12,'Full decarbonisation threshold (10%)',fontsize=10,color='0.25')
if END>2035: ax.flat[0].text(2036.5,4,'network limits\nremoved from 2036',fontsize=9,color='0.4')
from matplotlib.lines import Line2D
h=[Line2D([],[],color=BLUE,lw=2.6),Line2D([],[],color=ORANGE,lw=2.6),Line2D([],[],color='0.4',lw=1.4,ls='--')]
labels=[EE_LABEL,HT_LABEL,'Same scenario, published network path after 2035']
if END<=2035: h,labels=h[:2],labels[:2]   # dashed and solid lines coincide to 2035
fig.legend(h,labels,loc='lower center',ncol=len(h),frameon=False,fontsize=11)
fig.tight_layout(rect=(0,0.05,1,1)); save(fig, 7)
