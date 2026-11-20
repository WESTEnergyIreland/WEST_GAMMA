"""Shared helpers for the Phase 1 paper figures.

Each figure is saved twice in analysis/output/paper/: Figure_<n>.pdf (vector, for submission)
and Figure_<n>.png at 600 dpi (for the working Google Doc). Energy Policy asks for vector
EPS/PDF or bitmaps of at least 300 dpi (1000 dpi for line drawings); no title is drawn on the
figure itself, because the caption carries it.
"""
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PAPER_OUT = os.path.join(HERE, 'output', 'paper')
EE, HT = 'EirGrid_Extended', 'Historical_Trend'
EE_LABEL, HT_LABEL = 'EirGrid Extended (EE)', 'Historical Trend (HT)'
BLUE, ORANGE = '#2a7bd9', '#e8673a'

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'pdf.fonttype': 42})


def save(fig, number, dpi=600):
    """Write Figure_<number>.pdf and Figure_<number>.png; return the PNG path."""
    os.makedirs(PAPER_OUT, exist_ok=True)
    base = os.path.join(PAPER_OUT, f'Figure_{number}')
    fig.savefig(base + '.pdf', bbox_inches='tight', pad_inches=0.2)
    fig.savefig(base + '.png', dpi=dpi, bbox_inches='tight', pad_inches=0.2)
    plt.close(fig)
    print(f'saved {base}.pdf and .png')
    return base + '.png'
