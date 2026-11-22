"""Interval checks on wind, solar, battery and interconnector dispatch (Gamma.dispatch_interval).

The annual energy balance passes whether or not the operating limits hold in each interval,
so these tests check every limit directly: the SNSP numerator including battery charging,
the synchronous floor, both sides of the power balance and the reported SNSP.
"""
import numpy as np
from Gamma import dispatch_interval

TOL = 1e-6


def check(r, d, post, f, floor, fi=0.0):
    c, e = r['charge'], r['export']
    den = d + c + e
    nonsync = r['direct'] + c + r['export_vre'] + r['discharge'] + r['imp'] + fi
    assert abs(nonsync - r['nonsync']) < TOL
    # SNSP: all non-synchronous output, charging included, within the limit (recorded
    # imports are exogenous and may exceed it on their own).
    assert nonsync <= max(f * den, fi) + TOL
    # Synchronous output on the island covers what non-synchronous output does not.
    sync = den - nonsync
    assert sync >= min(floor, d - fi) - TOL
    # Wind and solar are fully accounted for.
    assert abs(r['direct'] + c + r['export_vre'] + r['curt'] - post) < TOL
    # Domestic supply does not exceed native demand; exports split into VRE and synchronous parts.
    assert r['direct'] + r['discharge'] + r['imp'] + fi <= d + TOL
    assert abs(r['export_vre'] + r['export_sync'] - e) < TOL
    assert min(r['direct'], r['curt'], r['export_vre'], r['export_sync'],
               r['discharge'], r['imp']) >= -TOL
    # Reported SNSP is the physical one.
    if den > 0:
        assert abs(r['snsppct'] - 100.0 * nonsync / den) < 1e-6


def test_audit_example_snsp_with_charging():
    # 1,000 MW demand, 1,200 MW wind and solar, 200 MW charging, 75% SNSP.
    r = dispatch_interval(1000, 1200, 200, 0, 0.75, 0.0)
    assert abs(r['direct'] - 700) < TOL
    assert abs(r['snsppct'] - 75.0) < TOL
    check(r, 1000, 1200, 0.75, 0.0)


def test_audit_example_floor_with_charging():
    # 100% SNSP and a 150 MW synchronous floor: direct delivery is 850 MW, not 1,000.
    r = dispatch_interval(1000, 1200, 200, 0, 1.0, 150.0)
    assert abs(r['direct'] - 850) < TOL
    check(r, 1000, 1200, 1.0, 150.0)


def test_recorded_imports_limit_discharge():
    # 1,000 MW load, 500 MW wind, 200 MW recorded imports, 300 MW battery, 75% SNSP, 150 MW floor.
    r = dispatch_interval(1000, 500, 0, 300, 0.75, 150.0, forced_import_mw=200)
    assert abs(r['discharge'] - 50) < TOL
    assert abs(r['snsppct'] - 75.0) < TOL
    check(r, 1000, 500, 0.75, 150.0, fi=200)


def test_exports_need_synchronous_share():
    # Exports raise the SNSP denominator, so (1 - SNSP) of the export flow is synchronous.
    r = dispatch_interval(1000, 1000, 0, 0, 0.75, 0.0, export_cap_mw=400)
    assert abs(r['export'] - 1000 / 3) < 1e-6
    assert abs(r['export_vre'] - 250) < 1e-6
    assert abs(r['export_sync'] - 250 / 3) < 1e-6
    assert r['curt'] < 1e-6
    check(r, 1000, 1000, 0.75, 0.0)


def test_random_intervals_respect_all_limits():
    rng = np.random.default_rng(42)
    for _ in range(20000):
        d = rng.uniform(0, 8000)
        post = rng.uniform(0, 12000)
        f = rng.choice([0.6, 0.75, 0.8, 0.95, 1.0])
        floor = rng.choice([0.0, 150.0, 450.0, 1050.0])
        c = rng.uniform(0, 2000) * (rng.random() < 0.5)
        dis = rng.uniform(0, 2000) * (rng.random() < 0.5)
        mode = rng.integers(3)
        fi = rng.uniform(0, 0.3 * d) if mode == 0 else 0.0
        exp_cap = rng.uniform(0, 2000) if mode == 1 else 0.0
        imp_cap = rng.uniform(0, 2000) if mode == 2 else 0.0
        r = dispatch_interval(d, post, c, dis, f, floor, fi, exp_cap, imp_cap)
        check(r, d, post, f, floor, fi)
        assert r['discharge'] <= dis + TOL
        assert r['export'] <= exp_cap + TOL and r['imp'] <= imp_cap + TOL
