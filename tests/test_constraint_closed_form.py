"""Closed form of E[max(0, x - H*eta)], ln(eta) ~ N(0, sigma^2), against Monte Carlo."""
import numpy as np
from Gamma import expected_constraint_mw

def test_closed_form_matches_monte_carlo():
    z = np.random.default_rng(0).standard_normal(2_000_000)
    for x, h, s in [(1000, 800, 0.88), (600, 494, 1.13), (300, 800, 0.88), (4000, 9000, 1.33)]:
        mc = np.maximum(0.0, x - h * np.exp(s * z)).mean()
        assert abs(expected_constraint_mw(x, h, s) - mc) < 0.01 * max(mc, 1.0) + 0.5

def test_nonnegative_and_monotone():
    x = np.linspace(1, 5000, 5000)
    c = expected_constraint_mw(x, 1000.0, 1.2)
    assert (c >= 0).all() and (np.diff(c) >= -1e-9).all()
