"""Verify the dry-run plan against kleinpanic's LIVE GitHub contribution graph.

Fetches the live contribution calendar via the GitHub GraphQL API
(``user(login:) -> contributionsCollection -> contributionCalendar``),
generates a dry-run plan using the same gradient/text/draw engine as
``generate_gradient.py``, renders both in a Sun..Sat grid, and diffs
live-vs-plan for a given ``--start``/``--end`` range, printing
per-week mismatches.

GraphQL shape (resolved via context7 library id
/websites/github_en_graphql, High reputation):

    user(login: "...") {
      contributionsCollection {
        contributionCalendar {
          totalContributions
          weeks {                 # no args; returns full ~53-week year
            firstDay
            contributionDays {
              date               # "YYYY-MM-DD"
              contributionCount  # int
              color             # "#ebedf0" etc.
              weekday           # 0=Sun .. 6=Sat
            }
          }
        }
      }
    }

The ``weekday`` field (0=Sun..6=Sat) matches the repo's existing
``(d.weekday() + 1) % 7`` row mapping used in ``preview_plan``.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_gradient as gg
from _commits import Plan, cap_counts

LOGIN_DEFAULT = "kleinpanic"

_SATURDAY_WEEKDAY = 5


def _days_to_sunday(d: date) -> int:
    """Days from *d* back to the Sunday at the start of its week (0..6)."""
    return (d.weekday() + 1) % 7


# ────────────────────────────── data models ──────────────────────────────


@dataclass(frozen=True)
class DayMismatch:
    """A single day where plan and live disagree."""

    date: date
    expected: int
    observed: int


@dataclass(frozen=True)
class WeekDiff:
    """Diff for one Sun-Sat week."""

    week_start: date
    mismatches: list[DayMismatch] = field(default_factory=list)


@dataclass(frozen=True)
class DiffResult:
    """Full diff between plan and live over [start, end]."""

    verdict: str  # "match" | "mismatch"
    total_expected: int
    total_observed: int
    weeks: list[WeekDiff]


# ────────────────────────────── parsing ──────────────────────────────


def parse_calendar_response(raw: str) -> dict[date, int]:
    """Parse the GraphQL JSON response into ``{date: contributionCount}``.

    Handles full and partial (trailing) weeks transparently — every
    ``contributionDay`` in every week is flattened into the dict.
    """
    data: dict[str, Any] = json.loads(raw)
    calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    counts: dict[date, int] = {}
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            counts[date.fromisoformat(day["date"])] = day["contributionCount"]
    return counts


# ────────────────────────────── rendering ──────────────────────────────


def render_grid(
    counts: dict[date, int],
    start: date,
    end: date,
) -> list[str]:
    """Render a 7-row Sun..Sat ASCII grid identical in style to ``preview_plan``.

    Returns a list of 7 strings (one per weekday row, Sun=0..Sat=6).
    Lit cells show ``'#'``; unlit cells show ``'.\\xa0'`` (dot + nbsp).
    """
    span = (end - start).days + 1
    grid: list[list[str]] = [[".\xa0" for _ in range(span)] for _ in range(7)]
    for i in range(span):
        d = start + timedelta(days=i)
        n = counts.get(d, 0)
        if n:
            row = (d.weekday() + 1) % 7  # Sun=0..Sat=6
            grid[row][i] = "#"
    return ["".join(row) for row in grid]


# ────────────────────────────── diff ──────────────────────────────


def _week_start_of(d: date) -> date:
    """Return the Sunday at the start of *d*'s week."""
    return d - timedelta(days=_days_to_sunday(d))


def diff_calendars(
    plan: dict[date, int],
    live: dict[date, int],
    start: date,
    end: date,
) -> DiffResult:
    """Diff *plan* vs *live* over the inclusive range [start, end].

    Days outside [start, end] are ignored. Days present in one dict but
    not the other are treated as 0 in the missing dict. Results are
    grouped into WeekDiff objects by their containing Sun-Sat week.
    """
    weeks_map: dict[date, list[DayMismatch]] = defaultdict(list)
    total_expected = 0
    total_observed = 0
    has_mismatch = False

    for i in range((end - start).days + 1):
        d = start + timedelta(days=i)
        exp = plan.get(d, 0)
        obs = live.get(d, 0)
        total_expected += exp
        total_observed += obs
        if exp != obs:
            has_mismatch = True
            weeks_map[_week_start_of(d)].append(
                DayMismatch(date=d, expected=exp, observed=obs)
            )

    # Build a sorted list of WeekDiff, including weeks with no mismatches
    # so the caller can iterate a complete calendar if needed. Only weeks
    # that contain at least one day in [start, end] appear.
    first_week = _week_start_of(start)
    last_week = _week_start_of(end)
    weeks: list[WeekDiff] = []
    w = first_week
    while w <= last_week:
        weeks.append(WeekDiff(week_start=w, mismatches=weeks_map.get(w, [])))
        w += timedelta(days=7)

    return DiffResult(
        verdict="mismatch" if has_mismatch else "match",
        total_expected=total_expected,
        total_observed=total_observed,
        weeks=weeks,
    )


# ────────────────────────────── live fetch ──────────────────────────────


_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            date
            contributionCount
            color
            weekday
          }
        }
      }
    }
  }
}
"""


def fetch_live_calendar(login: str) -> dict[date, int]:
    """Call ``gh api graphql`` to fetch the live contribution calendar.

    Uses the already-authenticated ``gh`` CLI on this box.
    """
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={_QUERY}", "-F", f"login={login}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_calendar_response(result.stdout)


# ────────────────────────────── CLI ──────────────────────────────


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def build_plan(args: argparse.Namespace) -> Plan:
    """Generate a dry-run Plan using the same engine as generate_gradient.py."""
    # Reuse generate_gradient's argparse + defaults so the plan matches
    gg_args = gg.parse_args([
        "--mode", args.mode,
        "--start", args.start.isoformat(),
        "--end", args.end.isoformat(),
        "--min-commits", str(args.min_commits),
        "--max-commits", str(args.max_commits),
        "--max-per-day", str(args.max_per_day),
        "--curve", str(args.curve),
    ])
    if args.mode == "gradient":
        gg_args.align_weeks = args.align_weeks
        plan = gg.plan_gradient(gg_args)
    elif args.mode == "text":
        gg_args.text = args.text
        plan = gg.plan_text(gg_args)
    else:
        gg_args.image = args.image
        plan = gg.plan_draw(gg_args)
    capped = cap_counts(plan.counts, max_per_day=args.max_per_day)
    return Plan(counts=capped, start=plan.start, end=plan.end)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Verify the dry-run plan against the LIVE GitHub contribution graph.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--login", default=LOGIN_DEFAULT, help="GitHub user whose calendar to fetch.")
    p.add_argument("--start", type=_parse_date, required=True, help="Range start (YYYY-MM-DD).")
    p.add_argument("--end", type=_parse_date, required=True, help="Range end (YYYY-MM-DD).")
    p.add_argument("--mode", choices=("gradient", "text", "draw"), default="gradient")
    p.add_argument("--min-commits", type=int, default=0)
    p.add_argument("--max-commits", type=int, default=20)
    p.add_argument("--max-per-day", type=int, default=12)
    p.add_argument("--curve", type=float, default=1.0)
    p.add_argument("--align-weeks", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--text", type=str, help="text mode: letters to render.")
    p.add_argument("--image", type=str, help="draw mode: path to PNG (must be 7 px tall).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.end < args.start:
        raise SystemExit(f"--end ({args.end}) is before --start ({args.start})")

    # 1. Build the dry-run plan
    plan = build_plan(args)
    print(f"Plan: {plan.start} .. {plan.end}  ({plan.days} days, {plan.total} commits)")
    print()
    print("Plan preview:")
    plan_rows = render_grid(plan.counts, plan.start, plan.end)
    for row in plan_rows:
        print("  " + row)
    print()

    # 2. Fetch live calendar
    print(f"Fetching live calendar for {args.login} ...")
    live = fetch_live_calendar(args.login)
    print(f"Live: {len(live)} days fetched")
    print()
    print("Live preview:")
    live_rows = render_grid(live, plan.start, plan.end)
    for row in live_rows:
        print("  " + row)
    print()

    # 3. Diff over the plan's full range
    diff = diff_calendars(plan.counts, live, plan.start, plan.end)

    # 4. Report per-week mismatches
    if diff.verdict == "match":
        print("No mismatches — plan and live agree across all weeks.")
    else:
        print("Per-week mismatches:")
        for w in diff.weeks:
            if not w.mismatches:
                continue
            print(f"  Week of {w.week_start}:")
            for dm in w.mismatches:
                print(f"    {dm.date}  expected {dm.expected} / observed {dm.observed}")
    print()

    # 5. One-line verdict
    print(f"expected {diff.total_expected} / observed {diff.total_observed} / {diff.verdict}")
    return 0 if diff.verdict == "match" else 1


if __name__ == "__main__":
    sys.exit(main())
