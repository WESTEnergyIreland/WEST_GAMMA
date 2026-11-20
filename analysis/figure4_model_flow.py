"""Figure 4 of the Phase 1 paper: flow of the Gamma model (inputs, the order of calculation in each
15-minute interval, annual outputs).

Usage: python analysis/figure4_model_flow.py
"""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from paper_figures_common import save

ROWS = [
    ('Inputs, per scenario', '#f3f7fc',
     ['13 weather years:\nwind, solar, demand\n(15-minute records)', 'Fleet by zone:\nonshore, offshore,\nsolar, batteries',
      'Demand growth:\nbackground, heat,\ntransport', 'Operating rules:\nSNSP limit,\nminimum units',
      'Network headroom\nby zone and year']),
    ('Each 15-minute interval, in order', '#fbf1ec',
     ['1. Available output\nin 7 zones\nand offshore', '2. Network\nconstraint:\nlimit per zone',
      '3. Batteries charge\nfrom output that\nwould be curtailed', '4. Curtailment at\nSNSP and minimum\nunits ceilings',
      '5. Batteries\ndischarge into\nremaining headroom']),
    ('Annual outputs', '#eef6ef',
     ['Constraint and\ncurtailment\nby zone', 'Delivered wind and\nsolar, capacity factor,\nshare of demand',
      'Firm capacity\nand generation', 'Fossil share of\nprimary energy', 'Electricity to run\nfirm plant on\nhydrogen']),
]
fig, ax = plt.subplots(figsize=(12, 6.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 66); ax.axis('off')
for r, (title, fill, boxes) in enumerate(ROWS):
    y0 = 46 - r * 22
    ax.add_patch(FancyBboxPatch((0.5, y0), 99, 19, boxstyle='round,pad=0,rounding_size=1.2',
                                fc=fill, ec='#a7a7a7', lw=1.2))
    ax.text(2, y0 + 17, title, fontsize=12, fontweight='bold', va='center', color='#333333')
    for i, t in enumerate(boxes):
        x0 = 2 + i * 19.5
        ax.add_patch(FancyBboxPatch((x0, y0 + 1.5), 17.5, 12.5, boxstyle='round,pad=0,rounding_size=0.8',
                                    fc='white', ec='#2a78d6', lw=1.4))
        ax.text(x0 + 8.75, y0 + 7.75, t, ha='center', va='center', fontsize=9.6)
        if r == 1 and i < 4:
            ax.annotate('', xy=(x0 + 19.4, y0 + 7.75), xytext=(x0 + 17.6, y0 + 7.75),
                        arrowprops=dict(arrowstyle='-|>', color='#444444', lw=1.2))
    if r < 2:
        ax.annotate('', xy=(50, y0 - 2.6), xytext=(50, y0 - 0.3),
                    arrowprops=dict(arrowstyle='-|>', color='#444444', lw=1.4))
save(fig, 4)
