#!/usr/bin/env python3
"""Generate backdated commits to draw patterns on the GitHub contribution graph.

Three modes:
  gradient  Linear ramp from N_min to N_max commits per day across the date range.
            Default mode. Reproduces the current 365-day gradient.
  text      Render a string in the 5x7 bitmap font across the graph.
            Example: --text "KLEIN"
  draw      Load a PNG and place it on the graph (Pillow required).
            Example: --image path/to/drawing.png

Modes produce a Plan (date -> commit_count). The plan is capped to
--max-per-day commits (default 12) and materialized into backdated git
commits with --apply. Without --apply the script runs in dry-run mode and
prints what *would* happen.

Safety: the script does NOT create an initial repo commit. The repo is
expected to already be a git repo with a README. To create a fresh repo,
run `git init && git commit --allow-empty -m init` first.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commits import EMAIL, Plan, cap_counts, materialize
from font_5x7 import HEIGHT, render_text
from font_5x7 import SUPPORTED as FONT_SUPPORTED

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ────────────────────────────── mode builders ──────────────────────────────


def plan_gradient(args: argparse.Namespace) -> Plan:
    """Linear ramp from N_min to N_max across the date range.

    Single-day range (--end == --start) is allowed and treated as the
    endpoint of the ramp: t = 1.0 -> max_commits. This makes
    `--start 2024-06-15 --end 2024-06-15` produce one day with max commits.
    """
    counts: dict[date, int] = {}
    span = (args.end - args.start).days
    if span < 0:
        raise SystemExit("gradient: --end must be on or after --start")
    for i in range(span + 1):
        t = 1.0 if span == 0 else i / span  # 0..1, or 1.0 for single-day
        n = round(args.min_commits + (args.max_commits - args.min_commits) * t)
        counts[args.start + timedelta(days=i)] = n
    return Plan(counts=counts, start=args.start, end=args.end)


def plan_text(args: argparse.Namespace) -> Plan:
    """Render `text` in the 5x7 font, place it on the graph right-aligned.

    The text's right edge ends on the Saturday of the week containing
    --end. Each "lit" pixel becomes one commit on its day; each "unlit"
    pixel becomes zero. The total commits per day are the count of lit
    pixels in that day's column.
    """
    if not args.text:
        raise SystemExit("text mode: --text is required")
    bad = sorted({c for c in args.text if c not in FONT_SUPPORTED})
    if bad:
        raise SystemExit(
            f"text mode: unsupported characters (use A-Z, 0-9, space): {bad!r}"
        )

    rows = render_text(args.text)  # list of 7 strings
    text_cols = len(rows[0])
    if text_cols == 0:
        raise SystemExit("text mode: empty text")

    # Find the Saturday that ends the week containing --end.
    # weekday(): Mon=0..Sun=6. We want rows indexed 0..6 = Sun..Sat.
    # Map: weekday()=6 (Sun) -> row 0, weekday()=5 (Sat) -> row 6.
    end_weekday = args.end.weekday()  # 0=Mon..6=Sun
    sat_row = 5  # row 6 is Saturday (rows are 0-6, Sun..Sat)
    sat_date = args.end + timedelta(days=(sat_row - end_weekday) % 7)

    # Place the rightmost column of the text on sat_date.
    start_col = sat_date - timedelta(days=text_cols - 1)
    if start_col < args.start:
        # The text would overflow the requested start. Slide so the
        # leftmost column lands on --start, and let the right side extend
        # past --end if needed (caller can shorten --end).
        start_col = args.start

    counts: dict[date, int] = defaultdict(int)
    for col_idx in range(text_cols):
        col_date = start_col + timedelta(days=col_idx)
        # Each column maps to one day on the contribution graph; that day's
        # commit count is the number of lit pixels in the column (rows
        # 0..6 = Sun..Sat). Per-day cap is applied later by cap_counts().
        lit = sum(1 for r in range(HEIGHT) if rows[r][col_idx] == "1")
        if lit:
            counts[col_date] = lit

    plan_start = min(counts) if counts else args.start
    plan_end = max(counts) if counts else args.end
    return Plan(counts=dict(counts), start=plan_start, end=plan_end)


def plan_draw(args: argparse.Namespace) -> Plan:
    """Load a PNG/JPG and treat each non-transparent/bright pixel as lit."""
    if not args.image:
        raise SystemExit("draw mode: --image is required")
    try:
        from PIL import Image
    except ImportError as e:
        raise SystemExit(
            "draw mode requires Pillow. Install with: pip install Pillow"
        ) from e

    img = Image.open(args.image).convert("RGBA")
    # GitHub graph is 7 rows tall. Width = weeks; we leave width = image
    # width as given. Caller can resize the image to fit the desired span.
    w, h = img.size
    if h != 7:
        raise SystemExit(
            f"draw mode: image must be exactly 7 pixels tall (got {h}). "
            "Resize the image so height == 7 before passing."
        )

    # Place the rightmost column on the Saturday of the week containing --end.
    end_weekday = args.end.weekday()
    sat_row = 5
    sat_date = args.end + timedelta(days=(sat_row - end_weekday) % 7)

    start_col = sat_date - timedelta(days=w - 1)
    if start_col < args.start:
        start_col = args.start

    counts: dict[date, int] = defaultdict(int)
    for x in range(w):
        col_date = start_col + timedelta(days=x)
        for y in range(7):  # rows are Sun..Sat
            r, g, b, a = img.getpixel((x, y))
            # Treat pixels with alpha > 128 and brightness < 128 as lit.
            if a > 128 and (r + g + b) / 3 < 128:
                counts[col_date] += 1

    # All-white / transparent image -> no lit pixels. Return an empty
    # plan anchored on the requested window instead of crashing on
    # min(counts).
    if not counts:
        return Plan(counts={}, start=args.start, end=args.end)
    return Plan(counts=dict(counts), start=min(counts), end=max(counts))


# ────────────────────────────── preview ──────────────────────────────


def preview_plan(plan: Plan) -> None:
    """Print a 7-row ASCII rendering of the plan so the user can eyeball it.

    Rows are Sun..Sat (matching GitHub's contribution-graph layout).
    Lit pixels show '#', unlit show '.'.
    """
    if not plan.counts:
        print("  (plan is empty)")
        return
    span = (plan.end - plan.start).days + 1
    # Build a 7xspan grid
    grid: list[list[str]] = [[".\u00a0" for _ in range(span)] for _ in range(7)]
    for i in range(span):
        d = plan.start + timedelta(days=i)
        n = plan.counts.get(d, 0)
        if n:
            row = (d.weekday() + 1) % 7  # Sun=0..Sat=6
            grid[row][i] = "#"
    print(f"  contribution-graph preview (Sun..Sat, {span} days):")
    for row in grid:
        print("  " + "".join(row))


# ────────────────────────────── CLI ──────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate backdated commits to draw on the GitHub contribution graph.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--mode", choices=("gradient", "text", "draw"), default="gradient",
        help="What kind of pattern to draw.",
    )
    p.add_argument(
        "--start", type=_parse_date, default=None,
        help="Range start (YYYY-MM-DD). Required for gradient; default for text/draw: 365 days before --end.",
    )
    p.add_argument(
        "--end", type=_parse_date, default=None,
        help="Range end (YYYY-MM-DD). Defaults to today for gradient; to Saturday of this week for text/draw.",
    )
    p.add_argument(
        "--max-per-day", type=int, default=12,
        help="Cap commits per day (GitHub visually saturates at ~10-12).",
    )
    p.add_argument(
        "--min-commits", type=int, default=1,
        help="Gradient mode: commits on the first day of the range.",
    )
    p.add_argument(
        "--max-commits", type=int, default=12,
        help="Gradient mode: commits on the last day of the range.",
    )
    p.add_argument("--text", type=str, help="text mode: letters to render.")
    p.add_argument("--image", type=str, help="draw mode: path to PNG (must be 7 px tall).")
    p.add_argument(
        "--apply", action="store_true",
        help="Actually create commits. Without this, the script runs in dry-run mode.",
    )
    p.add_argument(
        "--labels", action="store_true",
        help="Print Mon/YY/Sun/YY boundary labels above the preview (for text/draw debugging).",
    )
    return p.parse_args(argv)


def _parse_date(s: str) -> date:
    if not s:
        raise argparse.ArgumentTypeError("date string required")
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid date {s!r}: {e}") from e


def apply_defaults(args: argparse.Namespace) -> None:
    """Fill in --start/--end defaults based on the mode."""
    if args.end is None:
        if args.mode == "gradient":
            args.end = date.today()
        else:
            # text/draw: end on the Saturday of this week.
            today = date.today()
            sat_row = 5
            args.end = today + timedelta(days=(sat_row - today.weekday()) % 7)
    if args.start is None:
        if args.mode == "gradient":
            args.start = args.end - timedelta(days=364)
        else:
            args.start = args.end - timedelta(days=364)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    apply_defaults(args)

    if args.end < args.start:
        raise SystemExit(f"--end ({args.end}) is before --start ({args.start})")
    if args.max_per_day < 1:
        raise SystemExit("--max-per-day must be >= 1")

    if args.mode == "gradient":
        plan = plan_gradient(args)
    elif args.mode == "text":
        plan = plan_text(args)
    else:
        plan = plan_draw(args)

    # Cap per-day after the plan is built so the cap is a single source of truth.
    capped = cap_counts(plan.counts, max_per_day=args.max_per_day)
    plan = Plan(counts=capped, start=plan.start, end=plan.end)

    print(f"Mode: {args.mode}")
    print(f"Range: {plan.start} .. {plan.end}  ({plan.days} days)")
    print(f"Total commits: {plan.total}")
    print(f"Per-day cap: {args.max_per_day}")
    print()
    preview_plan(plan)
    print()

    if not args.apply:
        print("DRY-RUN. Re-run with --apply to create commits.")
        print("  (Commits use author email:", EMAIL, ")")
        return 0

    materialize(plan, repo=REPO, apply=True, prefix=args.mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
