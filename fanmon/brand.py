"""Agentic Builders Collective (ABC) branding.

`fm` is built for the members of ABC — https://www.agenticbuilders.sg/ — and
wears the collective's identity: the sliced, slanted ABC wordmark and its
peach → coral gradient. The gradient doubles as the tool's heat scale, so the
brand and the gauges are one visual system: peach = warm, coral = hot.
"""
from __future__ import annotations

from rich.text import Text

COMMUNITY_NAME = "Agentic Builders Collective"
COMMUNITY_URL = "https://www.agenticbuilders.sg/"
TAGLINE = "agentic builders collective"

# --- palette (sampled from the ABC logo) -----------------------------------
INK = "#0B0A12"        # background: near-black navy
SURFACE = "#12111B"
PANEL = "#1A1824"
PEACH = "#F5A86B"      # top slab of the wordmark
SALMON = "#EF8E64"     # middle slab
CORAL = "#E86F5E"      # bottom slab
RUST = "#6B3226"       # outline / dotted rule
MIST = "#E8DED6"       # body text (warm off-white)
MUTED = "#8E8489"      # captions
SAGE = "#8FBF8F"       # the one non-brand colour: "healthy"

# Wordmark slab gradient, top → bottom (5 rows, one per slab).
SLABS = ["#F6AD70", "#F39E6A", "#EF8E64", "#EB7E60", "#E86F5E"]

# Severity → colour. The brand gradient *is* the heat scale.
SEVERITY = {"ok": SAGE, "watch": PEACH, "high": CORAL}

# --- wordmark ----------------------------------------------------------------
# Each letter is five horizontal slabs (like the logo); `▀` leaves the lower
# half of the cell empty so consecutive rows read as separate slices. Rows are
# shifted right toward the top to give the logo's italic lean.
_LETTERS = {
    "A": ["▀▀▀▀▀", "▀▀ ▀▀", "▀▀▀▀▀", "▀▀ ▀▀", "▀▀ ▀▀"],
    "B": ["▀▀▀▀▀", "▀▀ ▀▀", "▀▀▀▀ ", "▀▀ ▀▀", "▀▀▀▀▀"],
    "C": ["▀▀▀▀▀", "▀▀   ", "▀▀   ", "▀▀   ", "▀▀▀▀▀"],
}
_GAP = "  "

WORDMARK_ROWS = [
    " " * (4 - i) + _GAP.join(_LETTERS[ch][i] for ch in "ABC")
    for i in range(5)
]
WORDMARK_WIDTH = max(len(r) for r in WORDMARK_ROWS)   # 23
BRAND_WIDTH = len(TAGLINE)                            # 27


def _lerp(a: str, b: str, t: float) -> str:
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return "#{:02X}{:02X}{:02X}".format(
        round(ar + (br - ar) * t), round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t))


def wordmark() -> Text:
    """The sliced ABC wordmark, one gradient stop per slab row."""
    t = Text(no_wrap=True)
    for i, row in enumerate(WORDMARK_ROWS):
        t.append(row, style=f"bold {SLABS[i]}")
        if i < len(WORDMARK_ROWS) - 1:
            t.append("\n")
    return t


def rule(width: int = BRAND_WIDTH) -> Text:
    return Text("┈" * width, style=RUST, no_wrap=True)


def tagline(width: int = BRAND_WIDTH) -> Text:
    """Lowercase tagline with a per-character peach → coral sweep."""
    t = Text(no_wrap=True)
    n = max(1, len(TAGLINE) - 1)
    for i, ch in enumerate(TAGLINE):
        t.append(ch, style=_lerp(PEACH, CORAL, i / n))
    return t


def brand_block() -> Text:
    """Wordmark + rule + tagline as a single 7-row renderable (for --once)."""
    t = wordmark()
    t.append("\n")
    t.append_text(rule())
    t.append("\n")
    t.append_text(tagline())
    return t


# --- animation ---------------------------------------------------------------
# On launch, slabs start as the logo's rust outline and fill top to bottom in
# the gradient, then the rule and tagline appear.
REVEAL_STEPS = 8      # 5 slabs + flash tail + rule + tagline
REVEAL_PERIOD = 0.16  # seconds per frame


def _lighten(color: str, t: float) -> str:
    return _lerp(color, "#FFF3E8", t)


def _rows(row_styles: list[str], rule_style: str | None,
          tagline_visible: bool) -> Text:
    t = Text(no_wrap=True)
    for i, row in enumerate(WORDMARK_ROWS):
        t.append(row, style=f"bold {row_styles[i]}")
        t.append("\n")
    t.append_text(rule() if rule_style is None else
                  Text("┈" * BRAND_WIDTH, style=rule_style, no_wrap=True))
    t.append("\n")
    if tagline_visible:
        t.append_text(tagline())
    else:
        t.append(" " * BRAND_WIDTH)
    return t


def brand_frame(mode: str, step: int) -> Text:
    """One animation frame. Unknown mode / out-of-range step → static block."""
    n = len(WORDMARK_ROWS)
    if mode == "reveal":
        if step >= REVEAL_STEPS:
            return brand_block()
        styles = []
        for i in range(n):
            if i < step - 1:
                styles.append(SLABS[i])                  # settled
            elif i == step - 1:
                styles.append(_lighten(SLABS[i], 0.45))  # just lit: flash
            else:
                styles.append(RUST)                      # still outline
        rule_style = None if step >= n + 1 else INK
        return _rows(styles, rule_style, tagline_visible=step >= n + 2)
    return brand_block()


def heat_color(frac: float) -> str:
    """0..1 → sage / peach / coral. Same steps everywhere in the app."""
    return SAGE if frac < 0.4 else (PEACH if frac < 0.75 else CORAL)


def bar(frac: float, width: int = 20, color: str | None = None) -> Text:
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    t = Text(no_wrap=True)
    t.append("█" * filled, style=color or heat_color(frac))
    t.append("░" * (width - filled), style=RUST)
    return t


def textual_theme():
    """The ABC theme for the Textual TUI (imported lazily; rich-only callers
    such as `fm --once` never need Textual)."""
    from textual.theme import Theme
    return Theme(
        name="abc",
        primary=PEACH,
        secondary=SALMON,
        accent=CORAL,
        warning=PEACH,
        error=CORAL,
        success=SAGE,
        foreground=MIST,
        background=INK,
        surface=SURFACE,
        panel=PANEL,
        boost="#F5A86B10",
        dark=True,
        variables={
            "footer-key-foreground": PEACH,
            "footer-description-foreground": MUTED,
            "footer-background": INK,
            "block-cursor-background": SALMON,
            "block-cursor-foreground": INK,
            "block-cursor-text-style": "bold",
            "datatable--header-cursor": PEACH,
            "scrollbar": RUST,
            "scrollbar-hover": SALMON,
            "scrollbar-active": PEACH,
            "border": RUST,
            "border-blurred": RUST,
        },
    )
