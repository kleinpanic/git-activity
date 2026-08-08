"""Tests for the profile-verification script (T-001).

Covers the diff logic on fixture calendars, including edge weeks
(partial weeks at the start/end of the comparison range).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import verify_profile as vp


# -- parse_calendar_response --

def _calendar_response(weeks_data, total=0):
    """Build a raw GraphQL JSON response from a list of (firstDay, days) tuples."""
    weeks = []
    for first_day, days in weeks_data:
        weeks.append({
            "firstDay": first_day,
            "contributionDays": [
                {"date": d, "contributionCount": c, "weekday": w}
                for d, c, w in days
            ],
        })
    return json.dumps({
        "data": {
            "user": {
                "contributionsCollection": {
                    "contributionCalendar": {
                        "totalContributions": total,
                        "weeks": weeks,
                    }
                }
            }
        }
    })


def test_parse_calendar_one_full_week():
    """One complete week of days parses to date -> contributionCount."""
    resp = _calendar_response([
        ("2025-01-05", [
            ("2025-01-05", 0, 0),
            ("2025-01-06", 1, 1),
            ("2025-01-07", 2, 2),
            ("2025-01-08", 0, 3),
            ("2025-01-09", 0, 4),
            ("2025-01-10", 0, 5),
            ("2025-01-11", 0, 6),
        ]),
    ], total=3)
    counts = vp.parse_calendar_response(resp)
    assert counts[date(2025, 1, 5)] == 0
    assert counts[date(2025, 1, 6)] == 1
    assert counts[date(2025, 1, 7)] == 2
    assert len(counts) == 7


def test_parse_calendar_partial_last_week():
    """A trailing partial week (fewer than 7 days) still parses."""
    resp = _calendar_response([
        ("2025-01-05", [
            ("2025-01-05", 0, 0),
            ("2025-01-06", 0, 1),
            ("2025-01-07", 0, 2),
            ("2025-01-08", 0, 3),
            ("2025-01-09", 0, 4),
            ("2025-01-10", 0, 5),
            ("2025-01-11", 0, 6),
        ]),
        ("2025-01-12", [
            ("2025-01-12", 1, 0),
            ("2025-01-13", 0, 1),
        ]),
    ], total=1)
    counts = vp.parse_calendar_response(resp)
    assert counts[date(2025, 1, 12)] == 1
    assert counts[date(2025, 1, 13)] == 0
    assert len(counts) == 9  # 7 + 2


def test_parse_calendar_empty():
    """Zero weeks -> empty dict."""
    resp = _calendar_response([], total=0)
    assert vp.parse_calendar_response(resp) == {}


# -- render_grid --

def test_render_grid_single_lit_day():
    """A single lit Sunday produces '#' in row 0 only."""
    counts = {date(2025, 1, 5): 1}  # Sunday
    rows = vp.render_grid(counts, date(2025, 1, 5), date(2025, 1, 5))
    assert len(rows) == 7
    assert rows[0] == "#"
    assert all("#" not in r for r in rows[1:])


def test_render_grid_unlit_uses_dot_nbsp():
    """Unlit cells use '.\\xa0' (dot + nbsp) matching preview_plan."""
    rows = vp.render_grid({}, date(2025, 1, 5), date(2025, 1, 5))
    assert rows[0] == ".\xa0"


def test_render_grid_full_week():
    """Sun-Sat with lit Tue and Thu places '#' in rows 2 and 4."""
    counts = {
        date(2025, 1, 7): 2,   # Tuesday  -> row 2
        date(2025, 1, 9): 4,   # Thursday -> row 4
    }
    rows = vp.render_grid(counts, date(2025, 1, 5), date(2025, 1, 11))
    assert "#" in rows[2]
    assert "#" in rows[4]
    assert "#" not in rows[0]
    assert "#" not in rows[1]
    assert "#" not in rows[3]


# -- diff_calendars --

def test_diff_identical_calendars_match():
    """Plan == live -> verdict 'match', totals equal."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 11)
    counts = {date(2025, 1, 6): 3, date(2025, 1, 8): 5}
    diff = vp.diff_calendars(counts, dict(counts), start, end)
    assert diff.verdict == "match"
    assert diff.total_expected == 8
    assert diff.total_observed == 8
    assert all(not w.mismatches for w in diff.weeks)


def test_diff_single_mismatch():
    """One day off by one -> one DayMismatch and verdict 'mismatch'."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 11)
    plan = {date(2025, 1, 6): 3, date(2025, 1, 8): 5}
    live = {date(2025, 1, 6): 3, date(2025, 1, 8): 4}
    diff = vp.diff_calendars(plan, live, start, end)
    assert diff.verdict == "mismatch"
    assert diff.total_expected == 8
    assert diff.total_observed == 7
    mismatches = [dm for w in diff.weeks for dm in w.mismatches]
    assert len(mismatches) == 1
    assert mismatches[0].date == date(2025, 1, 8)
    assert mismatches[0].expected == 5
    assert mismatches[0].observed == 4


def test_diff_left_edge_week():
    """Range starting mid-week excludes days before --start."""
    start = date(2025, 1, 8)   # Wednesday
    end = date(2025, 1, 11)    # Saturday
    plan = {date(2025, 1, 5): 9, date(2025, 1, 8): 3, date(2025, 1, 9): 2}
    live = {date(2025, 1, 5): 9, date(2025, 1, 8): 3, date(2025, 1, 9): 2}
    diff = vp.diff_calendars(plan, live, start, end)
    assert diff.verdict == "match"
    assert diff.total_expected == 5  # only 3 + 2
    all_dates = [dm.date for w in diff.weeks for dm in w.mismatches]
    assert date(2025, 1, 5) not in all_dates


def test_diff_right_edge_week():
    """Range ending mid-week excludes days after --end."""
    start = date(2025, 1, 5)   # Sunday
    end = date(2025, 1, 7)     # Tuesday
    plan = {date(2025, 1, 5): 1, date(2025, 1, 7): 2, date(2025, 1, 9): 9}
    live = {date(2025, 1, 5): 1, date(2025, 1, 7): 2, date(2025, 1, 9): 9}
    diff = vp.diff_calendars(plan, live, start, end)
    assert diff.verdict == "match"
    assert diff.total_expected == 3
    all_dates = [dm.date for w in diff.weeks for dm in w.mismatches]
    assert date(2025, 1, 9) not in all_dates


def test_diff_weeks_grouped_by_sunday():
    """Days in the same Sun-Sat week share one WeekDiff."""
    start = date(2025, 1, 6)   # Monday
    end = date(2025, 1, 9)     # Thursday -- all in week of Jan 5
    plan = {date(2025, 1, 6): 1, date(2025, 1, 9): 1}
    live = {date(2025, 1, 6): 0, date(2025, 1, 9): 2}
    diff = vp.diff_calendars(plan, live, start, end)
    assert len(diff.weeks) == 1
    assert diff.weeks[0].week_start == date(2025, 1, 5)


def test_diff_multiple_weeks():
    """Two full weeks produce two WeekDiff entries."""
    start = date(2025, 1, 5)   # Sunday
    end = date(2025, 1, 18)    # Saturday
    plan = {date(2025, 1, 6): 3, date(2025, 1, 13): 4}
    live = {date(2025, 1, 6): 2, date(2025, 1, 13): 5}
    diff = vp.diff_calendars(plan, live, start, end)
    assert len(diff.weeks) == 2
    assert diff.weeks[0].week_start == date(2025, 1, 5)
    assert diff.weeks[1].week_start == date(2025, 1, 12)


def test_diff_missing_live_day_is_zero():
    """A day in plan but absent in live counts as 0 observed."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    plan = {date(2025, 1, 5): 5}
    live: dict[date, int] = {}
    diff = vp.diff_calendars(plan, live, start, end)
    assert diff.verdict == "mismatch"
    assert diff.total_expected == 5
    assert diff.total_observed == 0


# -- categorize_delta (T-002) --

def test_categorize_shortfall():
    """Plan > live on a day -> shortfall delta."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    plan = {date(2025, 1, 5): 5}
    live = {date(2025, 1, 5): 2}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    assert cat.total_shortfall == 3
    assert cat.total_surplus == 0
    assert cat.net_delta == -3


def test_categorize_surplus():
    """Live > plan on a day -> surplus delta (e.g. foreign contributions)."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    plan = {date(2025, 1, 5): 3}
    live = {date(2025, 1, 5): 10}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    assert cat.total_shortfall == 0
    assert cat.total_surplus == 7
    assert cat.net_delta == 7


def test_categorize_mixed_shortfall_and_surplus():
    """Both sides have independent deltas across different days."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 6)
    plan = {date(2025, 1, 5): 5, date(2025, 1, 6): 2}
    live = {date(2025, 1, 5): 2, date(2025, 1, 6): 8}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    assert cat.total_shortfall == 3   # day 1: plan 5 vs live 2
    assert cat.total_surplus == 6     # day 2: plan 2 vs live 8
    assert cat.net_delta == 3         # 6 - 3


def test_categorize_match_is_zero():
    """Identical calendars produce zero shortfall and surplus."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    counts = {date(2025, 1, 5): 5}
    diff = vp.diff_calendars(counts, dict(counts), start, end)
    cat = vp.categorize_delta(diff)
    assert cat.total_shortfall == 0
    assert cat.total_surplus == 0
    assert cat.net_delta == 0


def test_categorize_counts_only_mismatched_days():
    """Days where plan == live don't contribute to shortfall or surplus."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 7)
    plan = {date(2025, 1, 5): 3, date(2025, 1, 6): 5, date(2025, 1, 7): 4}
    live = {date(2025, 1, 5): 3, date(2025, 1, 6): 2, date(2025, 1, 7): 9}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    assert cat.total_shortfall == 3   # only Jan 6
    assert cat.total_surplus == 5     # only Jan 7


# -- explain_delta (T-002) --

def test_explain_match():
    """Matching calendars produce a 'match' verdict."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    counts = {date(2025, 1, 5): 5}
    diff = vp.diff_calendars(counts, dict(counts), start, end)
    cat = vp.categorize_delta(diff)
    report = vp.explain_delta(diff, cat)
    assert report.verdict == "match"
    assert "agree" in report.summary.lower()


def test_explain_surplus_only_is_explained():
    """All-surplus delta is explained as foreign contributions."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    plan = {date(2025, 1, 5): 3}
    live = {date(2025, 1, 5): 10}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    report = vp.explain_delta(diff, cat)
    assert report.verdict == "explained"
    assert "surplus" in report.summary.lower() or "foreign" in report.summary.lower()
    assert report.surplus == 7
    assert report.shortfall == 0


def test_explain_shortfall_only_is_explained():
    """All-shortfall delta is explained as plan not fully applied."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    plan = {date(2025, 1, 5): 5}
    live = {date(2025, 1, 5): 2}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    report = vp.explain_delta(diff, cat)
    assert report.verdict == "explained"
    assert report.shortfall == 3
    assert report.surplus == 0


def test_explain_mixed_is_explained():
    """Mixed shortfall+surplus is still explained with both numbers."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 6)
    plan = {date(2025, 1, 5): 5, date(2025, 1, 6): 2}
    live = {date(2025, 1, 5): 2, date(2025, 1, 6): 8}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    report = vp.explain_delta(diff, cat)
    assert report.verdict == "explained"
    assert report.shortfall == 3
    assert report.surplus == 6


def test_explain_summary_contains_numbers():
    """The human-readable summary includes the key numeric facts."""
    start = date(2025, 1, 5)
    end = date(2025, 1, 5)
    plan = {date(2025, 1, 5): 5}
    live = {date(2025, 1, 5): 12}
    diff = vp.diff_calendars(plan, live, start, end)
    cat = vp.categorize_delta(diff)
    report = vp.explain_delta(diff, cat)
    assert str(diff.total_expected) in report.summary
    assert str(diff.total_observed) in report.summary
    assert str(cat.total_surplus) in report.summary
