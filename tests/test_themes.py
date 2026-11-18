"""Every preset has to be complete and well-formed, and settings must survive.

A theme is a wall of hex codes typed by hand, several of them ported from
somewhere else, and a single mistyped one is invisible until somebody opens
that theme: Qt silently ignores an unparseable colour in a stylesheet, and
matplotlib raises only when it next draws.

Every manager here is built on its own config dict, so nothing reads or
writes the developer's own settings file.
"""

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
try:
    from PySide6 import QtWidgets  # noqa: F401  needs the Qt GUI libraries
except ImportError as err:          # e.g. no libEGL on a bare Linux runner
    pytest.skip(f"Qt GUI libraries unavailable: {err}", allow_module_level=True)

from luna_gui_wrapper.gui.style import PALETTES, build_qss  # noqa: E402
from luna_gui_wrapper.gui.theme import (  # noqa: E402
    DEFAULT_MARKER_SIZE,
    DEFAULT_PRESET,
    LUNA_THEMES,
    MARKER_SIZE_RANGE,
    N_SERIES,
    PRESETS,
    Theme,
    ThemeManager,
    derive_palette,
    preset_group,
    preset_names,
)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Everything on a theme that is a single colour.
COLOUR_FIELDS = tuple(
    name
    for name in Theme.__dataclass_fields__
    if name not in ("key", "name", "base", "series", "glow", "grid_on")
)


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_every_colour_is_a_six_digit_hex(key):
    theme = PRESETS[key]
    for field in COLOUR_FIELDS:
        value = getattr(theme, field)
        assert HEX.match(value), "{}.{} = {!r}".format(key, field, value)


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_every_theme_carries_a_full_set_of_trace_colours(key):
    theme = PRESETS[key]
    assert len(theme.series) == N_SERIES
    for colour in theme.series:
        assert HEX.match(colour), "{}: {!r}".format(key, colour)


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_the_base_is_dark_or_light(key):
    assert PRESETS[key].base in ("dark", "light")


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_the_marker_is_not_one_of_the_first_two_traces(key):
    """Reference lines must not read as data."""
    theme = PRESETS[key]
    assert theme.marker.lower() not in (
        theme.series[0].lower(),
        theme.series[1].lower(),
    )


def test_the_keys_and_names_are_unique():
    names = [name for _key, name in preset_names()]
    assert len(names) == len(set(names))
    assert len(PRESETS) == len(set(PRESETS))


def test_the_default_is_luna_light_and_the_groups_come_in_menu_order():
    """The theme menu draws a separator where the group changes, so each
    group has to be one block: Luna's, then daplis-rtp's dark, then light."""
    assert DEFAULT_PRESET == "luna_light"
    groups = [preset_group(key) for key, _name in preset_names()]
    order = ("luna", "dark", "light")
    assert groups == sorted(groups, key=order.index)
    assert set(groups) == set(order)


def test_all_ten_daplis_presets_are_there():
    daplis = {"cyberpunk", "midnight", "night_wave", "blueprint", "contrast",
              "daylight", "komorebi", "earth", "solarized", "daplis"}
    assert daplis <= set(PRESETS)
    assert set(PRESETS) - daplis == set(LUNA_THEMES)


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_matplotlib_accepts_every_theme(key):
    """The rcParams a theme produces have to be usable as they stand.

    Checked by actually drawing with them: an unparseable colour in
    'rcParams' raises at draw time and nowhere earlier.
    """
    import matplotlib
    from matplotlib.figure import Figure

    manager = ThemeManager({"theme": key})
    with matplotlib.rc_context(manager.mpl_rc()):
        figure = Figure()
        axes = figure.add_subplot(111)
        axes.plot([0, 1], [0, 1])
        axes.hist([1, 2, 2, 3], histtype="step")
        axes.axvline(0.5, color=PRESETS[key].marker)
        figure.colorbar(axes.imshow([[0, 1], [2, 3]]), ax=axes)
        figure.canvas.draw()


# -- the Luna themes -------------------------------------------------------

@pytest.mark.parametrize("key", sorted(LUNA_THEMES))
def test_a_luna_theme_is_drawn_from_its_own_palette_exactly(key):
    """Nothing overridden: the window looks exactly as it did before themes."""
    assert ThemeManager({"theme": key}).palette() == PALETTES[LUNA_THEMES[key]]


def test_a_change_to_a_luna_theme_replaces_only_what_follows_from_it():
    manager = ThemeManager({"theme": "luna_light"})
    manager.set_override("accent", "#ff0000")
    pal = manager.palette()
    exact = PALETTES["light"]
    assert pal["primary"] == "#ff0000"
    assert pal["heading"] == "#ff0000"
    # Not made from the accent: untouched.
    assert pal["surface"] == exact["surface"]
    assert pal["flag_bg"] == exact["flag_bg"]
    assert pal["text"] == exact["text"]


def test_a_new_window_colour_brings_its_derived_roles_along():
    manager = ThemeManager({"theme": "luna_dark"})
    manager.set_override("window", "#203040")
    pal = manager.palette()
    assert pal["surface"] == "#203040"
    # Buttons and borders are worked out from the window unless set by hand.
    assert pal["surface_container"] != PALETTES["dark"]["surface_container"]
    assert pal["outline_variant"] != PALETTES["dark"]["outline_variant"]


@pytest.mark.parametrize("key", sorted(PRESETS))
def test_every_theme_gives_the_stylesheet_a_complete_palette(key):
    pal = derive_palette(PRESETS[key])
    assert set(pal) == set(PALETTES["light"])
    for name, value in pal.items():
        assert HEX.match(value), "{}: {} = {!r}".format(key, name, value)


@pytest.mark.parametrize("key", sorted(PRESETS))
@pytest.mark.parametrize("size", (7, 10, 16))
def test_the_luna_stylesheet_is_built_for_every_theme_and_size(key, size):
    manager = ThemeManager({"theme": key, "ui_font_size": size})
    qss = build_qss(manager.palette(), "Sans", "Mono", size)
    assert "{" in qss and "}" in qss
    assert f"font-size: {size}pt" in qss
    # Every colour substituted: no palette key left in the text.
    assert "pal[" not in qss


def test_every_kind_of_field_and_text_box_is_styled_alike():
    """No tab may look different from the others because one kind of widget
    on it fell outside the sheet: spin boxes sit in the same rule as line
    edits and drop-downs, and the text boxes - the log, the file summary,
    the DCR report - are drawn at the interface size, not a point below."""
    qss = build_qss(PALETTES["dark"], "Sans", "Mono", 10)
    assert "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {" in qss
    # Every rule that gives a text box a font gives it the interface size.
    rules = re.findall(r"QPlainTextEdit\s*\{([^}]*)\}", qss)
    sized = [r for r in rules if "font-size" in r]
    assert sized
    for rule in sized:
        assert "font-size: 10pt" in rule, rule


# -- settings -----------------------------------------------------------------

@pytest.mark.parametrize("old, new", (("light", "luna_light"),
                                      ("dark", "luna_dark")))
def test_a_config_from_before_themes_opens_on_the_same_look(old, new):
    assert ThemeManager({"theme": old}).preset_key == new


def test_an_unreadable_config_opens_on_the_defaults():
    manager = ThemeManager({
        "theme": "no-such-theme", "ui_font_size": "big",
        "marker_size": None,
        "theme_overrides": {"accent": "red", "key": "x", "series": ["#000000"],
                            "nonsense": "#123456", "window": "#123456"},
    })
    assert manager.preset_key == DEFAULT_PRESET
    # Only the one well-formed override survives.
    assert manager.overrides() == {"window": "#123456"}


def test_everything_survives_a_restart():
    """Set in Preferences, stored on exit, read back as on next start."""
    cfg = {}
    manager = ThemeManager(cfg)
    manager.set_preset("earth")
    manager.set_override("accent", "#00ff00")
    manager.set_override("grid_on", False)
    manager.set_series_colour(1, "#abcdef")
    manager.set_ui_font_size(12)
    manager.set_plot_font_size(20)
    manager.set_marker_size(7)
    manager.store(cfg)

    again = ThemeManager(cfg)
    assert again.preset_key == "earth"
    assert again.theme.accent == "#00ff00"
    assert again.theme.grid_on is False
    assert again.theme.series[1] == "#abcdef"
    assert again.ui_font_size == 12
    assert again.plot_font_size == 20
    assert again.marker_size == 7
    assert again.mpl_rc()["lines.markersize"] == 7


def test_a_style_left_by_the_previous_version_is_dropped():
    cfg = {"theme": "earth", "style": "daplis"}
    ThemeManager(cfg).store(cfg)
    assert "style" not in cfg
    assert cfg["theme"] == "earth"


def test_out_of_range_sizes_are_held_at_the_limit():
    manager = ThemeManager({})
    manager.set_marker_size(MARKER_SIZE_RANGE[1] + 50)
    assert manager.marker_size == MARKER_SIZE_RANGE[1]


def test_picking_a_preset_clears_the_changes_and_reset_clears_everything():
    manager = ThemeManager({})
    manager.set_override("accent", "#00ff00")
    manager.set_preset("midnight")
    assert manager.overrides() == {}
    manager.set_marker_size(9)
    manager.reset()
    assert manager.preset_key == DEFAULT_PRESET
    assert manager.marker_size == DEFAULT_MARKER_SIZE


def test_a_change_is_announced():
    manager = ThemeManager({})
    seen = []
    manager.changed.connect(lambda: seen.append(1))
    manager.set_preset("cyberpunk")
    manager.set_override("accent", "#123456")
    assert len(seen) == 2


# -- plots ----------------------------------------------------------------------

def test_only_the_user_s_plot_changes_are_laid_over_the_komorebi_style():
    manager = ThemeManager({"theme": "luna_light"})
    assert manager.mpl_rc_changes() == {}
    manager.set_override("axes_bg", "#eeeeee")
    manager.set_marker_size(DEFAULT_MARKER_SIZE + 2)
    changes = manager.mpl_rc_changes()
    assert changes["axes.facecolor"] == "#eeeeee"
    assert changes["lines.markersize"] == DEFAULT_MARKER_SIZE + 2
    assert "figure.facecolor" not in changes


@pytest.mark.parametrize("key", ("luna_light", "luna_dark", "cyberpunk",
                                 "daylight"))
def test_the_plot_takes_the_theme_s_figure_colour(key):
    pytest.importorskip("matplotlib")
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure

    from luna_gui_wrapper.functions.plotting import plot_style_context

    manager = ThemeManager({"theme": key})
    manager.set_override("figure_bg", "#123456")
    with plot_style_context(manager.preset_key, manager.mpl_rc(),
                            manager.mpl_rc_changes()):
        figure = Figure()
    assert to_hex(figure.get_facecolor()) == "#123456"
