"""Tests for draw mode (requires Pillow)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_gradient as gg

PIL_OK = True
try:
    from PIL import Image
except ImportError:
    PIL_OK = False


def _ns(image: str, start: str, end: str, **kw) -> object:
    class NS:
        pass

    ns = NS()
    ns.image = image
    ns.start = date.fromisoformat(start)
    ns.end = date.fromisoformat(end)
    ns.max_per_day = kw.get("max_per_day", 12)
    return ns


def test_plan_draw_requires_seven_pixel_height(tmp_path):
    if not PIL_OK:
        import pytest
        pytest.skip("Pillow not installed")
    img_path = tmp_path / "bad.png"
    Image.new("RGBA", (10, 5), (0, 0, 0, 255)).save(img_path)
    try:
        gg.plan_draw(_ns(str(img_path), "2026-01-01", "2026-12-31"))
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit on wrong height")


def test_plan_draw_lands_on_saturday(tmp_path):
    if not PIL_OK:
        import pytest
        pytest.skip("Pillow not installed")
    # 7x10 image, all black -> every cell is one commit.
    img_path = tmp_path / "solid.png"
    Image.new("RGBA", (10, 7), (0, 0, 0, 255)).save(img_path)
    # --end 2026-08-04 is a Tuesday; Saturday of that week is 2026-08-08.
    plan = gg.plan_draw(_ns(str(img_path), "2026-01-01", "2026-08-04"))
    assert plan.end == date(2026, 8, 8)


def test_plan_draw_counts_lit_pixels(tmp_path):
    if not PIL_OK:
        import pytest
        pytest.skip("Pillow not installed")
    # 7x3 image where column 0 is fully lit (7 commits), col 1 half-lit,
    # col 2 fully dark (0 commits).
    img = Image.new("RGBA", (3, 7), (255, 255, 255, 255))  # white = unlit
    for y in range(7):
        img.putpixel((0, y), (0, 0, 0, 255))    # lit
        img.putpixel((1, y), (0, 0, 0, 255)) if y < 4 else None  # half lit
    img_path = tmp_path / "draw.png"
    img.save(img_path)
    plan = gg.plan_draw(_ns(str(img_path), "2026-01-01", "2026-12-31"))
    # Three day-columns with 7, 4, 0 commits respectively.
    sorted_counts = sorted(plan.counts.values(), reverse=True)
    assert sorted_counts[0] == 7
    assert sorted_counts[1] == 4
    # col 2 should be absent from counts entirely
    assert min(plan.counts.values()) >= 4


def test_plan_draw_image_path_required():
    try:
        gg.plan_draw(_ns(None, "2026-01-01", "2026-12-31"))
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit when --image is missing")


def test_plan_draw_all_white_image_returns_empty_plan(tmp_path):
    """An all-white (no lit pixels) 7px-tall image must not crash on
    min(counts)/max(counts). It should return a Plan with empty counts
    anchored on the requested --start/--end window.
    """
    if not PIL_OK:
        import pytest
        pytest.skip("Pillow not installed")
    img_path = tmp_path / "blank.png"
    Image.new("RGBA", (10, 7), (255, 255, 255, 255)).save(img_path)
    plan = gg.plan_draw(_ns(str(img_path), "2026-01-01", "2026-12-31"))
    assert plan.counts == {}
    assert plan.start == date(2026, 1, 1)
    assert plan.end == date(2026, 12, 31)
    assert plan.total == 0
