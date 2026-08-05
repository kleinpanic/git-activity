"""Tests for text mode and the 5x7 font."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from font_5x7 import HEIGHT, SUPPORTED, glyph_rows, render_text

import generate_gradient as gg


def _ns(text: str, start: str, end: str, **kw) -> object:
    class NS:
        pass

    ns = NS()
    ns.text = text
    ns.start = date.fromisoformat(start)
    ns.end = date.fromisoformat(end)
    ns.max_per_day = kw.get("max_per_day", 12)
    return ns


# ── font-shape tests ──────────────────────────────────────────────


def test_font_every_glyph_is_5x7():
    for ch, glyph in SUPPORTED.items():
        assert len(glyph) == 7, f"{ch}: expected 7 rows, got {len(glyph)}"
        for row in glyph:
            assert len(row) == 5, f"{ch}: row width {len(row)} != 5"
            assert all(c in "01" for c in row), f"{ch}: non-binary row {row!r}"


def test_font_space_is_blank():
    glyph = glyph_rows(" ")
    assert glyph == ("00000",) * 7


def test_font_letter_has_lit_pixels():
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        glyph = glyph_rows(ch)
        assert any("1" in row for row in glyph), f"{ch}: no lit pixels"


def test_render_text_A_is_5_cols():
    rows = render_text("A")
    assert len(rows) == HEIGHT
    for r in rows:
        assert len(r) == 5


def test_render_text_KLEIN_is_30_cols():
    rows = render_text("KLEIN")
    # 5 letters x 5 cols + 4 gaps x 1 col = 29 cols
    assert len(rows[0]) == 29


def test_render_text_empty_returns_blank_rows():
    rows = render_text("")
    assert rows == [""] * HEIGHT


def test_render_text_adds_gap_between_letters():
    a = render_text("A")
    ab = render_text("AB")
    b = render_text("B")
    # Each row of "AB" should be A's row + 1-col gap ("0") + B's row.
    for r in range(HEIGHT):
        assert ab[r] == a[r] + "0" + b[r], f"row {r}: {ab[r]!r} != {a[r] + '0' + b[r]!r}"


def test_render_text_unsupported_char_raises():
    try:
        render_text("klein")  # lowercase 'k','l','e','i','n' — not supported
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError on lowercase")


# ── plan_text tests ──────────────────────────────────────────────


def test_plan_text_lands_on_saturday():
    # --start must be early enough that the 29-column "KLEIN" string fits
    # without overflowing: start_col = sat_date - (text_cols - 1) = 2026-07-11.
    # Passing --start 2026-07-11 keeps the rightmost column on 2026-08-08.
    plan = gg.plan_text(_ns("KLEIN", "2026-07-11", "2026-08-04"))
    # Rightmost column should fall on the Saturday of the week containing --end.
    # The Saturday of the week containing 2026-08-04 (Tue) is 2026-08-08.
    assert plan.end == date(2026, 8, 8)


def test_plan_text_width_in_commit_days():
    plan = gg.plan_text(_ns("KLEIN", "2026-08-01", "2026-12-31"))
    # 5 letters x 5 cols + 4 gaps = 29 day-columns. Six of those columns
    # have zero lit pixels (4 gap cols + the I glyph's all-zero cols 0 and
    # 4), so 23 columns actually receive commits.
    days_with_commits = sum(1 for d in plan.counts if plan.counts[d] > 0)
    assert days_with_commits == 23


def test_plan_text_unsupported_rejected():
    try:
        gg.plan_text(_ns("klein", "2026-01-01", "2026-12-31"))
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit on unsupported chars")
