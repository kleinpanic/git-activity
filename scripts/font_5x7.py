"""5x7 bitmap font for ASCII letters (A-Z), digits (0-9), and space.

Each character is a 7-row x 5-column grid encoded as a list of 7 strings of
'0' and '1' (1 = lit pixel). The grid matches the GitHub contribution
graph's 7-row layout (Sun-Sat), so text drops in vertically without scaling.

Glyphs are a hand-rolled classic 5x7 font. Limited to uppercase + digits
+ space — lowercase letters are intentionally unsupported (most 'lowercase'
5x7 fonts render as 5x5 with descenders that don't fit cleanly).
"""
from __future__ import annotations

# 37 glyphs: 26 letters + 10 digits + space
_FONT: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "10001", "11001", "10101", "10011", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "10001", "01010", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}

GLYPHS = {**_FONT, **{c.lower(): _FONT[c] for c in "abcdefghijklmnopqrstuvwxyz" if c in _FONT}}
# SUPPORTED is exposed as the same dict as GLYPHS so callers can iterate
# `.items()` and inspect each glyph, and `c in SUPPORTED` still works for
# the membership check the CLI uses.
SUPPORTED = GLYPHS
WIDTH = 5
HEIGHT = 7


def glyph_rows(ch: str) -> tuple[str, ...]:
    """Return the 7 row strings for `ch`. Raises KeyError on unsupported."""
    return GLYPHS[ch]


def render_text(text: str) -> list[str]:
    """Render `text` into a list of `HEIGHT` rows of '0'/'1'.

    Letters are concatenated with a 1-column blank space between them.
    Letters that aren't supported raise KeyError.
    """
    if not text:
        return [""] * HEIGHT
    rows = [""] * HEIGHT
    for i, ch in enumerate(text):
        glyph = GLYPHS[ch]  # KeyError surfaces the missing char
        for r in range(HEIGHT):
            rows[r] += glyph[r]
            if i < len(text) - 1:
                rows[r] += "0"  # 1-col gap between letters
    return rows
