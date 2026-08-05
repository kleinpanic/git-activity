"""Tests for gradient-mode math."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_gradient as gg


def _ns(start: str, end: str, **kw) -> object:
    """Build a minimal argparse-like object."""
    class NS:
        pass

    ns = NS()
    ns.start = date.fromisoformat(start)
    ns.end = date.fromisoformat(end)
    ns.min_commits = kw.get("min_commits", 1)
    ns.max_commits = kw.get("max_commits", 12)
    ns.max_per_day = kw.get("max_per_day", 12)
    return ns


def test_gradient_full_year_366_days():
    # 2024 is leap year: 366 days inclusive.
    plan = gg.plan_gradient(_ns("2024-01-01", "2024-12-31"))
    assert plan.days == 366
    assert plan.start == date(2024, 1, 1)
    assert plan.end == date(2024, 12, 31)


def test_gradient_endpoints_match_min_max():
    plan = gg.plan_gradient(_ns("2024-01-01", "2024-12-31"))
    assert plan.counts[date(2024, 1, 1)] == 1   # day 0
    assert plan.counts[date(2024, 12, 31)] == 12  # day 365


def test_gradient_monotonic_nondecreasing():
    plan = gg.plan_gradient(_ns("2024-01-01", "2024-12-31"))
    last = -1
    for d in sorted(plan.counts):
        assert plan.counts[d] >= last
        last = plan.counts[d]


def test_gradient_total_within_range():
    # Total commits across N days with linear ramp 1..max is roughly (N*mean).
    plan = gg.plan_gradient(_ns("2024-01-01", "2024-12-31"))
    # Mean of 1..12 over 366 days ~ 6.5, so total ~ 2,379
    assert 2300 < plan.total < 2500


def test_gradient_single_day_range():
    # Same start and end should produce exactly one entry.
    plan = gg.plan_gradient(_ns("2024-06-15", "2024-06-15"))
    assert plan.days == 1
    assert plan.counts[date(2024, 6, 15)] == 12  # t=1.0 -> max


def test_gradient_default_range_uses_kwargs():
    plan = gg.plan_gradient(_ns("2024-01-01", "2024-01-10", min_commits=2, max_commits=4))
    assert plan.counts[date(2024, 1, 1)] == 2
    assert plan.counts[date(2024, 1, 10)] == 4


def test_cap_counts_drops_zero():
    from _commits import cap_counts
    counts = {
        date(2024, 1, 1): 0,
        date(2024, 1, 2): 5,
        date(2024, 1, 3): 50,
    }
    capped = cap_counts(counts, max_per_day=12)
    assert date(2024, 1, 1) not in capped
    assert capped[date(2024, 1, 2)] == 5
    assert capped[date(2024, 1, 3)] == 12
