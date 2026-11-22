"""Where every colour, font size and plot style in the application comes from.

Ported from daplis-rtp's ``gui/theme.py``: one object holds the lot - the
window palette, the accent, the colours the traces are drawn in, the two font
sizes - and one signal says it has changed.

The two Luna themes are the app's own light and dark palettes, exactly as
they were; the other ten are daplis-rtp's presets, unchanged. Every theme is
drawn with Luna's own stylesheet (style.py), from a palette worked out of the
theme's colours (derive_palette).

The settings live in the app's JSON config with everything else
(functions/config.py), written on exit; daplis-rtp keeps them in QSettings.

"""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

from PySide6 import QtCore, QtWidgets

from ..functions.config import load_config
from .style import (_FONT_MONO_CANDIDATES, _FONT_SANS_CANDIDATES, PALETTES,
                    build_palette, build_qss, pick_font)

# The two font sizes the user can move. The interface one is applied to the
# whole application; the plot one to every plot opened after it is set.
UI_FONT_RANGE = (7, 16)
PLOT_FONT_RANGE = (6, 32)

DEFAULT_UI_FONT_SIZE = 10
# The komorebi styles' 30 pt, scaled to the on-screen figure (see
# functions/plotting.py), which is what the Luna themes' plots have always had.
DEFAULT_PLOT_FONT_SIZE = 12

# The dots on the traces, in points. Zero is allowed: it draws the line alone.
MARKER_SIZE_RANGE = (0, 12)
DEFAULT_MARKER_SIZE = 4

# How many series colours a theme carries.
N_SERIES = 5


# ----------------------------------------------------------------------
# Colour arithmetic
# ----------------------------------------------------------------------

_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        *(max(0, min(255, int(round(c)))) for c in rgb)
    )


def _mix(start, end, t):
    """The colour a fraction ``t`` of the way from ``start`` to ``end``."""
    a, b = _rgb(start), _rgb(end)
    return _hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


def readable_on(colour):
    """Black or white, whichever can be read on ``colour``.

    Rec. 601 luma: the eye weights green far above blue, so a plain mean of
    the channels calls yellow dark and blue light.
    """
    try:
        r, g, b = _rgb(colour)
    except (ValueError, AttributeError):
        return "#000000"
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luma > 140 else "#ffffff"


@dataclass(frozen=True)
class Theme:
    """A complete look: window, controls and plots together.

    Frozen because a theme is a value, not a thing that is edited. The
    user's changes are kept separately, as overrides, and applied with
    ``dataclasses.replace`` when the effective theme is built - so
    "reset to preset" is throwing the overrides away rather than
    reconstructing anything.

    """

    key: str
    name: str
    # 'dark' or 'light': which block of the theme menu it sits in, and
    # which way a few derived shades lean (see _DERIVED, derive_palette).
    base: str

    # --- interface -------------------------------------------------
    window: str
    surface: str
    text: str
    muted: str
    accent: str
    ok: str
    warn: str
    error: str

    # --- plots -----------------------------------------------------
    figure_bg: str
    axes_bg: str
    # Ticks and the axis labels - everything that is read as text.
    axes_fg: str
    # The box around the data. Separate from the text because several
    # of the ported styles depend on the difference: Blueprint draws a
    # dim blue frame under bright white labels, and Solarized a grey
    # one under slate text.
    axes_edge: str
    grid: str
    series: Tuple[str, ...]
    # Reference lines drawn over the data rather than as data: the median
    # and noisy-cut lines on the per-pixel DCR histogram.
    marker: str

    # --- effects ---------------------------------------------------
    # The glow under the traces, from 'mplcyberpunk' when it is installed.
    glow: bool
    grid_on: bool

    # --- interface, in finer steps ---------------------------------
    # A preset may leave these empty; they are then worked out from the
    # colours above when the preset is registered (see '_DERIVED'), and
    # follow those colours when the user changes them.
    #
    # The menu bar, the log, the tables and lists, the help pages.
    panel: str = ""
    # Push buttons.
    button: str = ""
    # Every thin border: fields, buttons, group boxes, the tab page.
    border: str = ""
    # Secondary text: one step quieter than 'text'.
    text_dim: str = ""

    def colour(self, index):
        """Series colour ``index``, wrapping round rather than raising."""
        return self.series[index % len(self.series)]


PRESETS: Dict[str, Theme] = {}


# Roles worked out from others, as (field, sources, rule). The steps are
# daplis-rtp's (after dapkel-rtp's), so the presets the apps share agree.
_DERIVED = (
    (
        "panel",
        ("window", "text"),
        lambda t: (
            _mix(t.window, "#000000", 0.30)
            if t.base == "dark"
            else _mix(t.window, t.text, 0.05)
        ),
    ),
    ("button", ("window", "text"), lambda t: _mix(t.window, t.text, 0.10)),
    ("border", ("window", "muted"), lambda t: _mix(t.window, t.muted, 0.35)),
    ("text_dim", ("muted", "text"), lambda t: _mix(t.muted, t.text, 0.50)),
)


def _complete(theme):
    """Fill the derived roles a theme leaves empty."""
    filled = {
        field: rule(theme)
        for field, _sources, rule in _DERIVED
        if not getattr(theme, field)
    }
    return replace(theme, **filled) if filled else theme


def _preset(theme):
    theme = _complete(theme)
    PRESETS[theme.key] = theme
    return theme


# The Luna themes first, then daplis-rtp's: dark, then light, because that is
# the order they are offered in - the menu puts a separator where the group
# changes (see preset_group).

# Luna's own light and dark palettes (style.PALETTES), as themes. With
# nothing overridden, the window is drawn from those palettes exactly; the
# fields here are what Preferences shows and what a change starts from. The
# plot fields are the komorebi_mpl styles the Inspect
# tab has always used - 'sci_pure' and 'night_wave' - which are drawn with
# komorebi_mpl itself when it is installed.
LUNA_THEMES = {"luna_light": "light", "luna_dark": "dark"}

_preset(
    Theme(
        key="luna_light",
        name="Luna light",
        base="light",
        window="#ffffff",
        surface="#f9fafb",
        text="#111827",
        muted="#6b7280",
        accent="#007aff",
        ok="#1a7f37",
        warn="#8a6d00",
        error="#d32f2f",
        figure_bg="#ffffff",
        axes_bg="#ffffff",
        axes_fg="#000000",
        axes_edge="#000000",
        grid="#1a1a1a",
        series=("#e63946", "#ff7f00", "#2ecc71", "#1f77b4", "#8e44ad"),
        marker="#808080",
        glow=False,
        # Off deliberately: dense hitmaps and long-tailed histograms, where
        # a grid competes with the data rather than helping read it.
        grid_on=False,
        panel="#ffffff",
        button="#f3f4f6",
        border="#d1d5db",
        text_dim="#4b5563",
    )
)

_preset(
    Theme(
        key="luna_dark",
        name="Luna dark",
        base="dark",
        window="#131315",
        surface="#1b1b1d",
        text="#e5e5e5",
        muted="#8e8e93",
        accent="#007aff",
        ok="#32d74b",
        warn="#ffd60a",
        error="#ff453a",
        figure_bg="#221d2f",
        axes_bg="#221d2f",
        axes_fg="#f2f2f2",
        axes_edge="#bfbfbf",
        grid="#aac7df",
        series=("#eb67f5", "#88f7e2", "#44d492", "#f5eb67", "#ffa15c"),
        marker="#808080",
        glow=False,
        grid_on=False,
        panel="#131315",
        button="#202022",
        border="#48484a",
        text_dim="#9ca3af",
    )
)

# ---- daplis-rtp's presets, unchanged ------------------------------------
#
# The six after the first two are ports of the matplotlib styles in
# 'komorebi_mpl' (github.com/rngKomorebi/komorebi_mpl). The figure, axes,
# grid and trace colours are that package's; the window chrome - and the
# three status colours - are daplis-rtp's.

# daplis-rtp's default: a near-black figure, coral traces and the
# 'mplcyberpunk' glow under them.
_preset(
    Theme(
        key="cyberpunk",
        name="Cyberpunk",
        base="dark",
        window="#14181f",
        surface="#1b212b",
        text="#e3e9f2",
        muted="#8c97a8",
        accent="#08f7fe",
        ok="#00e676",
        warn="#ffc400",
        error="#ff5370",
        figure_bg="#0d0f14",
        axes_bg="#0d0f14",
        axes_fg="#c7d0dd",
        axes_edge="#c7d0dd",
        grid="#2a3140",
        series=("#f48383", "#08f7fe", "#fe53bb", "#f5d300", "#00ff9f"),
        marker="#00b8b8",
        glow=True,
        grid_on=False,
    )
)

# The same dark window without the glow.
_preset(
    Theme(
        key="midnight",
        name="Midnight",
        base="dark",
        window="#19232d",
        surface="#222b35",
        text="#dfe4ec",
        muted="#8a94a3",
        accent="#4d9de0",
        ok="#7fd18b",
        warn="#e7c26b",
        error="#e06c75",
        figure_bg="#19232d",
        axes_bg="#19232d",
        axes_fg="#d8dee9",
        axes_edge="#d8dee9",
        grid="#36404e",
        series=("#e06c75", "#61afef", "#98c379", "#e5c07b", "#c678dd"),
        marker="#56b6c2",
        glow=False,
        grid_on=True,
    )
)

# komorebi_mpl's 'night_wave': synthwave neon on a violet ground.
_preset(
    Theme(
        key="night_wave",
        name="Night wave",
        base="dark",
        window="#221d2f",
        surface="#382c47",
        text="#ffffff",
        muted="#9a8fb0",
        accent="#eb67f5",
        ok="#44d492",
        warn="#f5eb67",
        error="#fa233e",
        figure_bg="#221d2f",
        axes_bg="#221d2f",
        axes_fg="#f2f2f2",
        axes_edge="#bfbfbf",
        grid="#aac7df",
        series=("#eb67f5", "#88f7e2", "#44d492", "#f5eb67", "#ffa15c"),
        marker="#aac7df",
        glow=True,
        grid_on=True,
    )
)

# komorebi_mpl's 'blueprint': white and ice-blue lines on deep navy, with
# the frame a dimmer blue than the labels.
_preset(
    Theme(
        key="blueprint",
        name="Blueprint",
        base="dark",
        window="#0d1f3c",
        surface="#142848",
        text="#e8f1fa",
        muted="#b8d4ea",
        accent="#7ec8e3",
        ok="#7ec8e3",
        warn="#f0a030",
        error="#ff6b6b",
        figure_bg="#0d1f3c",
        axes_bg="#0d1f3c",
        axes_fg="#e8f1fa",
        axes_edge="#3a6186",
        grid="#3a6186",
        series=("#f0f4f8", "#7ec8e3", "#a3d9ff", "#4fa3c5", "#c8e6f5"),
        marker="#60b0d4",
        glow=False,
        grid_on=True,
    )
)

# Pure black, white axes, and series colours chosen to stay apart both for
# normal vision and for the common forms of colour blindness.
_preset(
    Theme(
        key="contrast",
        name="High contrast",
        base="dark",
        window="#000000",
        surface="#121212",
        text="#ffffff",
        muted="#b0b0b0",
        accent="#ffd400",
        ok="#00e676",
        warn="#ffd400",
        error="#ff5252",
        figure_bg="#000000",
        axes_bg="#000000",
        axes_fg="#ffffff",
        axes_edge="#ffffff",
        grid="#555555",
        series=("#ffffff", "#ffd400", "#00e5ff", "#ff6ec7", "#7cff00"),
        marker="#00e5ff",
        glow=False,
        grid_on=True,
    )
)

# For a bright room, and for a plot that is going to be printed.
_preset(
    Theme(
        key="daylight",
        name="Daylight",
        base="light",
        window="#f0f2f5",
        surface="#ffffff",
        text="#1c2430",
        muted="#5b6675",
        accent="#1565c0",
        ok="#2e7d32",
        warn="#ef6c00",
        error="#c62828",
        figure_bg="#ffffff",
        axes_bg="#ffffff",
        axes_fg="#1c2430",
        axes_edge="#1c2430",
        grid="#d4d9e0",
        series=("#c0392b", "#1565c0", "#2e7d32", "#d35400", "#6a1b9a"),
        marker="#00838f",
        glow=False,
        grid_on=True,
    )
)

# komorebi_mpl's own: deep gold, forest green and sky blue on parchment.
_preset(
    Theme(
        key="komorebi",
        name="Komorebi",
        base="light",
        window="#f0ede2",
        surface="#faf8f0",
        text="#2c2416",
        muted="#6b6252",
        accent="#c8860a",
        ok="#2d6a4f",
        warn="#c8860a",
        error="#9b2335",
        figure_bg="#faf8f0",
        axes_bg="#faf8f0",
        axes_fg="#2c2416",
        axes_edge="#5a5040",
        grid="#c8b898",
        series=("#c8860a", "#2d6a4f", "#4a86b8", "#a0522d", "#6baa25"),
        marker="#8b7bc8",
        glow=False,
        grid_on=True,
    )
)

# komorebi_mpl's 'earth': terracotta, rust, olive and sage on aged paper.
_preset(
    Theme(
        key="earth",
        name="Earth",
        base="light",
        window="#ede4ce",
        surface="#f5ecd7",
        text="#2c1810",
        muted="#6b5540",
        accent="#9b2335",
        ok="#5e7a28",
        warn="#d4622a",
        error="#9b2335",
        figure_bg="#f5ecd7",
        axes_bg="#ede0c8",
        axes_fg="#2c1810",
        axes_edge="#a08060",
        grid="#c8b898",
        series=("#9b2335", "#d4622a", "#5e7a28", "#8b5e3c", "#c9984a"),
        marker="#4a7462",
        glow=False,
        grid_on=True,
    )
)

# Ethan Schoonover's Solarized, by way of komorebi_mpl.
_preset(
    Theme(
        key="solarized",
        name="Solarized",
        base="light",
        window="#eee8d5",
        surface="#fdf6e3",
        text="#586e75",
        muted="#93a1a1",
        accent="#268bd2",
        ok="#859900",
        warn="#b58900",
        error="#dc322f",
        figure_bg="#fdf6e3",
        axes_bg="#eee8d5",
        axes_fg="#657b83",
        axes_edge="#93a1a1",
        grid="#d3ccb8",
        series=("#268bd2", "#dc322f", "#859900", "#d33682", "#2aa198"),
        marker="#b58900",
        glow=False,
        grid_on=True,
    )
)

# komorebi_mpl's 'daplis': rebeccapurple and darkorange, chosen to stay
# legible for the common forms of colour blindness. The one to export in.
_preset(
    Theme(
        key="daplis",
        name="Daplis (publication)",
        base="light",
        window="#f2f2f2",
        surface="#ffffff",
        text="#1a1a1a",
        muted="#5a5a5a",
        accent="#663399",
        ok="#008080",
        warn="#ff8c00",
        error="#8b0000",
        figure_bg="#ffffff",
        axes_bg="#ffffff",
        axes_fg="#000000",
        axes_edge="#000000",
        grid="#bfbfbf",
        series=("#663399", "#ff8c00", "#008080", "#fa8072", "#483d8b"),
        marker="#cd5c5c",
        glow=False,
        grid_on=True,
    )
)

# The look the application shipped with, so an existing user opens the new
# version to the application they know.
DEFAULT_PRESET = "luna_light"

# Theme names stored by earlier versions, which had only light and dark.
_LEGACY_PRESETS = {"light": "luna_light", "dark": "luna_dark"}

# Overrides are stored by field name, but three of the fields are not
# colours the user can pick - they identify the preset itself.
UNOVERRIDABLE = ("key", "name", "base")

# The fields that change only the plots.
PLOT_FIELDS = ("figure_bg", "axes_bg", "axes_fg", "axes_edge", "grid",
               "series", "marker", "glow", "grid_on")


def preset_names():
    """``(key, display name)`` for every preset, in the order defined."""
    return [(key, theme.name) for key, theme in PRESETS.items()]


def preset_group(key):
    """Which block of the theme menu a preset sits in: 'luna', 'dark', 'light'."""
    return "luna" if key in LUNA_THEMES else PRESETS[key].base


# ----------------------------------------------------------------------
# The stylesheet's palette, from a theme
# ----------------------------------------------------------------------
#
# style.build_qss() reads a palette of some thirty named colours. The two Luna
# themes have theirs written out (style.PALETTES); every other theme gets one
# worked out from its own colours here, as {palette key: (theme fields it is
# made from, rule)}. The sources are also what decides, on a Luna theme, which
# written-out colours a user's change replaces.

def _tint_amount(theme):
    """How far a box's tint moves from the box colour towards its hue."""
    return 0.08 if theme.base == "dark" else 0.14


_PALETTE_RULES = {
    "surface": (("window",), lambda t: t.window),
    "surface_container_low": (("surface",), lambda t: t.surface),
    "surface_container": (("button",), lambda t: t.button),
    "surface_container_high": (("button", "text"),
                               lambda t: _mix(t.button, t.text, 0.08)),
    "surface_container_highest": (("button", "text"),
                                  lambda t: _mix(t.button, t.text, 0.16)),
    "primary": (("accent",), lambda t: t.accent),
    "primary_hover": (("accent",), lambda t: _mix(
        t.accent, "#ffffff" if t.base == "dark" else "#000000", 0.15)),
    "primary_border": (("accent",), lambda t: _mix(t.accent, "#000000", 0.25)),
    "on_primary": (("accent",), lambda t: readable_on(t.accent)),
    "outline": (("border", "muted"), lambda t: _mix(t.border, t.muted, 0.6)),
    "outline_variant": (("border",), lambda t: t.border),
    "text": (("text",), lambda t: t.text),
    "text_muted": (("text_dim",), lambda t: t.text_dim),
    "text_faint": (("muted",), lambda t: t.muted),
    "success": (("ok",), lambda t: t.ok),
    "warning": (("warn",), lambda t: t.warn),
    "error": (("error",), lambda t: t.error),
    "info": (("accent",), lambda t: t.accent),
    "alert_bg": (("window", "error"), lambda t: _mix(t.window, t.error, 0.08)),
    "alert_border": (("window", "error"), lambda t: _mix(t.window, t.error, 0.35)),
    "tab_active_bg": (("surface",), lambda t: t.surface),
    "tab_active_fg": (("text",), lambda t: t.text),
    "selection": (("window", "accent"), lambda t: _mix(t.window, t.accent, 0.25)),
    "grid": (("window", "text"), lambda t: _mix(t.window, t.text, 0.10)),
    # The advanced-flags button: the warning colour, since it flags a run that
    # is not the plain one. The wrapper-options button: the OK colour.
    "flag_bg": (("warn",), lambda t: t.warn),
    "flag_border": (("warn",), lambda t: _mix(t.warn, "#000000", 0.2)),
    "flag_fg": (("warn",), lambda t: readable_on(t.warn)),
    "wrap_bg": (("ok",), lambda t: t.ok),
    "wrap_border": (("ok",), lambda t: _mix(t.ok, "#000000", 0.2)),
    "wrap_fg": (("ok",), lambda t: readable_on(t.ok)),
    # Their faint washes, behind the Advanced tab's flags and wrapper boxes.
    # A dark window shows a tint at about half the strength a light one needs.
    "flag_tint": (("surface", "warn"),
                  lambda t: _mix(t.surface, t.warn, _tint_amount(t))),
    "wrap_tint": (("surface", "ok"),
                  lambda t: _mix(t.surface, t.ok, _tint_amount(t))),
    "heading": (("accent",), lambda t: t.accent),
    "panel": (("panel",), lambda t: t.panel),
    "view": (("panel",), lambda t: t.panel),
}


def derive_palette(theme):
    """The stylesheet's palette for any theme, from the theme's colours."""
    return {key: rule(theme) for key, (_sources, rule) in _PALETTE_RULES.items()}


class ThemeManager(QtCore.QObject):
    """The live theme, the user's changes to it, and who to tell.

    One of these exists per process - see :func:`theme_manager`. Everything
    that draws connects to :attr:`changed`, which is what makes a colour
    picked in Preferences show up in the window while it is still open.

    """

    changed = QtCore.Signal()

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self._preset_key = DEFAULT_PRESET
        # Only what the user has actually changed, keyed by field name.
        # Keeping it separate from the theme is what lets a preset be
        # swapped underneath a custom accent colour, and what makes
        # 'reset' a one-liner.
        self._overrides: Dict[str, object] = {}
        self._ui_font_size = DEFAULT_UI_FONT_SIZE
        self._plot_font_size = DEFAULT_PLOT_FONT_SIZE
        self._marker_size = DEFAULT_MARKER_SIZE
        self._fonts = None
        self.load(load_config() if cfg is None else cfg)

    # -- the effective theme ------------------------------------------

    @property
    def preset_key(self):
        return self._preset_key

    @property
    def theme(self):
        """The preset with the user's overrides laid over it."""
        base = PRESETS.get(self._preset_key, PRESETS[DEFAULT_PRESET])
        if not self._overrides:
            return base
        theme = replace(base, **self._overrides)
        # A derived role follows a source the user changed - a new window
        # background brings its panels and buttons along - unless the
        # user set that role too.
        moved = self._moved_roles()
        if moved:
            theme = _complete(replace(theme, **{field: "" for field in moved}))
        return theme

    def _moved_roles(self):
        return {
            field
            for field, sources, _rule in _DERIVED
            if field not in self._overrides
            and any(source in self._overrides for source in sources)
        }

    def changed_fields(self):
        """Every theme field that differs from the preset because of the user."""
        return set(self._overrides) | self._moved_roles()

    @property
    def ui_font_size(self):
        return self._ui_font_size

    @property
    def plot_font_size(self):
        return self._plot_font_size

    @property
    def marker_size(self):
        return self._marker_size

    def overrides(self):
        """A copy, so a caller editing it cannot change the theme."""
        return copy.deepcopy(self._overrides)

    def is_overridden(self, name):
        return name in self._overrides

    # -- changing it ---------------------------------------------------

    def set_preset(self, key, keep_overrides=False):
        """Switch preset.

        The overrides are dropped by default, and that is deliberate:
        picking a new preset and getting the last one's accent back is
        the surprising behaviour, not the helpful one.

        """
        if key not in PRESETS:
            return
        self._preset_key = key
        if not keep_overrides:
            self._overrides.clear()
        self._emit()

    def set_override(self, name, value):
        """Override one field of the preset, or clear it with ``None``."""
        if name in UNOVERRIDABLE or name not in Theme.__dataclass_fields__:
            return
        if value is None:
            self._overrides.pop(name, None)
        else:
            self._overrides[name] = value
        self._emit()

    def set_series_colour(self, index, colour):
        """Override one trace colour, leaving the others alone."""
        series: List[str] = list(self.theme.series)
        if not 0 <= index < len(series):
            return
        series[index] = colour
        self._overrides["series"] = tuple(series)
        self._emit()

    def set_ui_font_size(self, points):
        self._ui_font_size = _clamp(points, UI_FONT_RANGE)
        self._emit()

    def set_plot_font_size(self, points):
        self._plot_font_size = _clamp(points, PLOT_FONT_RANGE)
        self._emit()

    def set_marker_size(self, points):
        self._marker_size = _clamp(points, MARKER_SIZE_RANGE)
        self._emit()

    def reset(self):
        """Back to the shipped defaults, overrides and fonts included."""
        self._preset_key = DEFAULT_PRESET
        self._overrides.clear()
        self._ui_font_size = DEFAULT_UI_FONT_SIZE
        self._plot_font_size = DEFAULT_PLOT_FONT_SIZE
        self._marker_size = DEFAULT_MARKER_SIZE
        self._emit()

    def _emit(self):
        self.changed.emit()

    # -- persistence ---------------------------------------------------

    def load(self, cfg):
        """Read the stored settings, ignoring anything unrecognised.

        A stored value that no longer names a field - a preset that was
        renamed, a colour written by a newer version - is skipped rather
        than raising. A settings file is not something the user can
        easily repair, so it must never be able to stop the application
        opening.

        """
        cfg = cfg if isinstance(cfg, dict) else {}
        key = cfg.get("theme")
        key = _LEGACY_PRESETS.get(key, key)
        self._preset_key = key if key in PRESETS else DEFAULT_PRESET
        self._ui_font_size = _clamp(
            cfg.get("ui_font_size", DEFAULT_UI_FONT_SIZE), UI_FONT_RANGE)
        self._plot_font_size = _clamp(
            cfg.get("plot_font_size", DEFAULT_PLOT_FONT_SIZE), PLOT_FONT_RANGE)
        self._marker_size = _clamp(
            cfg.get("marker_size", DEFAULT_MARKER_SIZE), MARKER_SIZE_RANGE)

        self._overrides.clear()
        stored = cfg.get("theme_overrides")
        if not isinstance(stored, dict):
            return
        fields = set(Theme.__dataclass_fields__)
        for name, value in stored.items():
            if name not in fields or name in UNOVERRIDABLE:
                continue
            if name in ("glow", "grid_on"):
                self._overrides[name] = bool(value)
            elif name == "series":
                if isinstance(value, (list, tuple)):
                    colours = tuple(c for c in value
                                    if isinstance(c, str) and _HEX.fullmatch(c))
                    if len(colours) == N_SERIES:
                        self._overrides[name] = colours
            elif isinstance(value, str) and _HEX.fullmatch(value):
                self._overrides[name] = value

    def store(self, cfg):
        """Write the settings into ``cfg``, the app's config dict."""
        cfg["theme"] = self._preset_key
        # Written by the version that also had a choice of style.
        cfg.pop("style", None)
        cfg["ui_font_size"] = self._ui_font_size
        cfg["plot_font_size"] = self._plot_font_size
        cfg["marker_size"] = self._marker_size
        cfg["theme_overrides"] = {
            name: list(value) if name == "series" else value
            for name, value in self._overrides.items()
        }

    # -- applying it ---------------------------------------------------

    def palette(self):
        """The stylesheet's palette for the current theme.

        A Luna theme gives its own written-out palette, with only the
        colours that follow a field the user changed worked out afresh;
        every other theme a palette worked out from its colours.

        """
        theme = self.theme
        derived = derive_palette(theme)
        exact = PALETTES.get(LUNA_THEMES.get(self._preset_key))
        if exact is None:
            return derived
        changed = self.changed_fields()
        pal = dict(exact)
        for key, (sources, _rule) in _PALETTE_RULES.items():
            if changed.intersection(sources):
                pal[key] = derived[key]
        return pal

    def fonts(self):
        """``(sans, mono)``: the interface and the monospaced font families.

        Looked up once, and only once a QApplication exists - the font
        database needs one.

        """
        if self._fonts is None:
            if QtWidgets.QApplication.instance() is None:
                return ("Segoe UI" if os.name == "nt" else "Sans",
                        "Consolas" if os.name == "nt" else "Monospace")
            self._fonts = (
                pick_font(_FONT_SANS_CANDIDATES,
                          "Segoe UI" if os.name == "nt" else "Sans"),
                pick_font(_FONT_MONO_CANDIDATES,
                          "Consolas" if os.name == "nt" else "Monospace"),
            )
        return self._fonts

    def apply_to_app(self, app=None):
        """Put the current theme on the application.

        The font goes on the ``QApplication`` rather than on the widgets,
        so that every widget built before or after this call picks it up.

        """
        app = app or QtWidgets.QApplication.instance()
        if app is None:
            return
        sans, _mono = self.fonts()
        font = app.font()
        font.setFamily(sans)
        font.setPointSize(self._ui_font_size)
        app.setFont(font)
        # A real QPalette behind the sheet: it is what file dialogs, combo
        # pop-ups and disabled text fall back to.
        app.setPalette(build_palette(self.palette()))
        app.setStyleSheet(self.stylesheet())

    def stylesheet(self):
        """The whole application's stylesheet, in the current theme."""
        sans, mono = self.fonts()
        return build_qss(self.palette(), sans, mono, self._ui_font_size)

    # -- matplotlib ----------------------------------------------------

    def mpl_rc(self, fontsize=None):
        """The theme as matplotlib rcParams.

        Handed to ``rc_context`` around a draw rather than pushed into the
        global ``rcParams``. daplis-rtp's, plus the trace colours as the
        colour cycle and the tick convention its canvases draw by hand -
        inward ticks on all four sides with a minor set between - since the
        Inspect tab's plots are plain figures.

        """
        from cycler import cycler

        theme = self.theme
        size = self._plot_font_size if fontsize is None else fontsize
        return {
            "figure.facecolor": theme.figure_bg,
            "figure.edgecolor": theme.figure_bg,
            "figure.frameon": True,
            "savefig.facecolor": theme.figure_bg,
            "savefig.edgecolor": theme.figure_bg,
            "axes.facecolor": theme.axes_bg,
            "axes.edgecolor": theme.axes_edge,
            "axes.labelcolor": theme.axes_fg,
            "axes.titlecolor": theme.axes_fg,
            "axes.grid": theme.grid_on,
            "axes.axisbelow": True,
            "axes.linewidth": 1.6,
            "axes.prop_cycle": cycler(color=list(theme.series)),
            "grid.color": theme.grid,
            "grid.alpha": 0.45,
            "grid.linestyle": "--",
            "grid.linewidth": 0.8,
            "text.color": theme.axes_fg,
            "xtick.color": theme.axes_fg,
            "ytick.color": theme.axes_fg,
            "xtick.labelcolor": theme.axes_fg,
            "ytick.labelcolor": theme.axes_fg,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "xtick.minor.visible": True,
            "ytick.minor.visible": True,
            "xtick.major.size": 7,
            "ytick.major.size": 7,
            "xtick.minor.size": 4,
            "ytick.minor.size": 4,
            "xtick.major.width": 1.6,
            "ytick.major.width": 1.6,
            "xtick.minor.width": 1.6,
            "ytick.minor.width": 1.6,
            "font.size": size,
            "axes.labelsize": size,
            "axes.titlesize": "large",
            "figure.titlesize": "large",
            "xtick.labelsize": size,
            "ytick.labelsize": size,
            "legend.fontsize": size,
            "legend.facecolor": theme.axes_bg,
            "legend.edgecolor": theme.axes_fg,
            "lines.linewidth": 1.6,
            "lines.markersize": self._marker_size,
        }

    def mpl_rc_changes(self):
        """The part of :meth:`mpl_rc` that the user's plot settings changed.

        Laid over the komorebi_mpl style a Luna theme is drawn with, so a
        trace colour or a font size picked in Preferences still shows.

        """
        rc = self.mpl_rc()
        keys = []
        for field in self.changed_fields():
            keys.extend(_RC_FOR_FIELD.get(field, ()))
        if self._plot_font_size != DEFAULT_PLOT_FONT_SIZE:
            keys.extend(_RC_FONT)
        if self._marker_size != DEFAULT_MARKER_SIZE:
            keys.append("lines.markersize")
        return {key: rc[key] for key in keys}


# Which rcParams each plot field sets, for mpl_rc_changes.
_RC_FOR_FIELD = {
    "figure_bg": ("figure.facecolor", "figure.edgecolor",
                  "savefig.facecolor", "savefig.edgecolor"),
    "axes_bg": ("axes.facecolor", "legend.facecolor"),
    "axes_fg": ("axes.labelcolor", "axes.titlecolor", "text.color",
                "xtick.color", "ytick.color", "xtick.labelcolor",
                "ytick.labelcolor", "legend.edgecolor"),
    "axes_edge": ("axes.edgecolor",),
    "grid": ("grid.color",),
    "grid_on": ("axes.grid",),
    "series": ("axes.prop_cycle",),
}
_RC_FONT = ("font.size", "axes.labelsize", "axes.titlesize", "figure.titlesize",
            "xtick.labelsize", "ytick.labelsize", "legend.fontsize")


def _clamp(value, bounds):
    low, high = bounds
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = low
    return max(low, min(high, value))


_MANAGER = None


def theme_manager():
    """The process-wide theme, read from the app's config on first use."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ThemeManager()
    return _MANAGER


def current_theme():
    """Shorthand for ``theme_manager().theme``."""
    return theme_manager().theme
