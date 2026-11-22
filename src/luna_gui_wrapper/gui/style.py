"""The app's stylesheet, built from a palette.

The colours come from the current theme (theme.py): the two Luna themes hand
in PALETTES below exactly as they are, every other theme a palette worked out
from its colours (theme.derive_palette).

custom_qss() is the part of the sheet that gives Luna's own widgets their
meaning -- the yellow advanced-flags button, the green wrapper button, the
accent and toggle buttons, the code line, the status colours.

One font size for the whole window: every tab, every field and every text box
is drawn at the interface size; only the notes under the controls are a point
smaller and the headings a point larger.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtGui import QColor, QFontDatabase, QPalette

# ---------------------------------------------------------------------------
# the Luna themes' palettes, light and dark
# ---------------------------------------------------------------------------

PALETTES = {
    "light": dict(
        surface="#ffffff",
        surface_container_low="#f9fafb",
        surface_container="#f3f4f6",
        surface_container_high="#e5e7eb",
        surface_container_highest="#e5e7eb",
        primary="#007aff", primary_hover="#0062cc", primary_border="#005bb5",
        on_primary="#ffffff",
        outline="#9ca3af", outline_variant="#d1d5db",
        text="#111827", text_muted="#4b5563", text_faint="#6b7280",
        success="#1a7f37", warning="#8a6d00", error="#d32f2f", info="#0b5cad",
        alert_bg="#fef2f2", alert_border="#fecaca",
        tab_active_bg="#f9fafb", tab_active_fg="#111827",
        selection="#cfe4ff", grid="#e5e7eb",
        flag_bg="#fde047", flag_border="#eab308", flag_fg="#422006",
        wrap_bg="#bbf7d0", wrap_border="#4ade80", wrap_fg="#14532d",
        # The Advanced tab's flags and wrapper boxes: a faint wash of the
        # two buttons' colours over the group-box background.
        flag_tint="#faf6e2", wrap_tint="#f0faf5",
        heading="#0b5cad",
        # The menu bar, and the views: the log, tables, lists, help pages.
        panel="#ffffff", view="#f9fafb",
    ),
    "dark": dict(
        surface="#131315",
        surface_container_low="#1b1b1d",
        surface_container="#202022",
        surface_container_high="#2a2a2c",
        surface_container_highest="#353537",
        primary="#007aff", primary_hover="#0a84ff", primary_border="#005bb5",
        on_primary="#ffffff",
        outline="#8e8e93", outline_variant="#48484a",
        text="#e5e5e5", text_muted="#9ca3af", text_faint="#8e8e93",
        success="#32d74b", warning="#ffd60a", error="#ff453a", info="#409cff",
        alert_bg="#202022", alert_border="#48484a",
        tab_active_bg="#353537", tab_active_fg="#ffffff",
        selection="#0a3a66", grid="#2a2a2c",
        flag_bg="#ffd60a", flag_border="#e6c000", flag_fg="#1c1c1e",
        wrap_bg="#86efac", wrap_border="#4ade80", wrap_fg="#052e16",
        flag_tint="#2d2a1b", wrap_tint="#242c28",
        heading="#5ac8fa",
        panel="#131315", view="#1b1b1d",
    ),
}

# The interface font size the sheets were drawn at; the others are steps off it.
BASE_FONT_SIZE = 10

_FONT_SANS_CANDIDATES = ("Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue",
                         "Noto Sans", "Helvetica", "Arial")
_FONT_MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo",
                         "DejaVu Sans Mono", "Courier New", "Courier")


def pick_font(candidates, fallback=""):
    try:
        available = set(QFontDatabase.families())
    except Exception:
        return fallback
    for name in candidates:
        if name in available:
            return name
    return fallback


_ARROW_DIR = Path(tempfile.gettempdir()) / "luna_gui_wrapper_arrows"
_ARROW_SVG = {
    "up": '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5" '
          'viewBox="0 0 8 5"><path d="M0 5 L4 0 L8 5 Z" fill="{c}"/></svg>',
    "down": '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5" '
            'viewBox="0 0 8 5"><path d="M0 0 L4 5 L8 0 Z" fill="{c}"/></svg>',
}


def arrow_icon(direction: str, colour: str) -> str:
    """Path of a small spin-box arrow in `colour`, written on first use.

    A stylesheet that gives the spin-box buttons any look of their own makes
    Qt drop the style's arrows, and it can only put an image in their place
    -- so the arrow is an image, one per colour, kept in the temp folder.
    Returned with forward slashes, as a stylesheet url() wants it. If the
    file cannot be written the path is still returned; the arrow is then
    simply missing, which is no reason to stop the window drawing.
    """
    path = _ARROW_DIR / f"{direction}_{colour.lstrip('#').lower()}.svg"
    if not path.is_file():
        try:
            _ARROW_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(_ARROW_SVG[direction].replace("{c}", colour),
                            encoding="utf-8")
        except OSError:
            pass
    return path.as_posix()


def build_palette(pal: dict) -> QPalette:
    """A real QPalette to back the stylesheet.

    The stylesheet cannot reach everything -- non-native file dialogs, combo
    popups, tooltips, disabled text -- and whatever it misses would otherwise
    fall back to Fusion's built-in light colours, which looks broken in dark
    mode. Setting both keeps them consistent.
    """
    c = QColor
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, c(pal["surface"]))
    p.setColor(QPalette.ColorRole.WindowText, c(pal["text"]))
    p.setColor(QPalette.ColorRole.Base, c(pal["surface_container_low"]))
    p.setColor(QPalette.ColorRole.AlternateBase, c(pal["surface_container"]))
    p.setColor(QPalette.ColorRole.Text, c(pal["text"]))
    p.setColor(QPalette.ColorRole.Button, c(pal["surface_container"]))
    p.setColor(QPalette.ColorRole.ButtonText, c(pal["text"]))
    p.setColor(QPalette.ColorRole.Highlight, c(pal["primary"]))
    p.setColor(QPalette.ColorRole.HighlightedText, c(pal["on_primary"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, c(pal["surface_container_highest"]))
    p.setColor(QPalette.ColorRole.ToolTipText, c(pal["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, c(pal["text_faint"]))
    p.setColor(QPalette.ColorRole.Link, c(pal["primary"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(pal["text_faint"]))
    return p


def build_qss(pal: dict, sans: str, mono: str, size: int = BASE_FONT_SIZE) -> str:
    """One stylesheet for the whole app, from a palette.

    `size` is the interface font size in points; the small text is a point
    below it and the headings a point above, as they were at 10 pt.
    """
    return f"""
    * {{
        font-family: "{sans}";
        font-size: {size}pt;
    }}
    /* Only real containers paint a background. A blanket QWidget rule would
       make every QLabel and QCheckBox paint the window colour on top of the
       group box it sits in, which shows as pale bands behind the text. */
    QMainWindow, QDialog {{ background: {pal['surface']}; }}
    QLabel, QCheckBox, QRadioButton, QFrame {{
        background: transparent;
        color: {pal['text']};
    }}

    /* ---- tabs ---------------------------------------------------------- */
    QTabWidget::pane {{
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        top: -1px;
        background: {pal['surface']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {pal['text_muted']};
        padding: 8px 18px;
        margin-right: 2px;
        border: 1px solid transparent;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTabBar::tab:hover {{ color: {pal['text']}; }}
    QTabBar::tab:selected {{
        background: {pal['tab_active_bg']};
        color: {pal['tab_active_fg']};
        border-color: {pal['outline_variant']};
        border-bottom-color: {pal['tab_active_bg']};
        font-weight: 600;
    }}

    /* ---- buttons ------------------------------------------------------- */
    QPushButton {{
        background: {pal['surface_container']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 7px;
        padding: 6px 14px;
        min-height: 18px;
    }}
    QPushButton:hover  {{ background: {pal['surface_container_high']}; }}
    QPushButton:pressed {{ background: {pal['surface_container_highest']}; }}
    QPushButton:disabled {{
        color: {pal['text_faint']};
        border-color: {pal['outline_variant']};
        background: {pal['surface_container_low']};
    }}

    /* ---- inputs -------------------------------------------------------- */
    /* Spin boxes too: left to Fusion they were the one kind of field drawn
       flat and square, in a different shade from the fields beside them. */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {pal['surface_container_low']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 7px;
        padding: 5px 9px;
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {pal['primary']};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        background: {pal['surface_container']};
        color: {pal['text_faint']};
    }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        width: 20px;
        border: none;
        border-left: 1px solid {pal['outline_variant']};
        background: transparent;
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: 7px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: 7px;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {pal['surface_container_high']};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{arrow_icon('up', pal['text_muted'])}");
        width: 8px; height: 5px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{arrow_icon('down', pal['text_muted'])}");
        width: 8px; height: 5px;
    }}
    QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{
        image: url("{arrow_icon('up', pal['text_faint'])}");
    }}
    QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
        image: url("{arrow_icon('down', pal['text_faint'])}");
    }}
    QComboBox QAbstractItemView {{
        background: {pal['surface_container_low']};
        border: 1px solid {pal['outline_variant']};
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
        outline: none;
    }}
    QCheckBox, QRadioButton {{ spacing: 7px; padding: 2px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
    QCheckBox::indicator {{
        border: 1px solid {pal['outline']};
        border-radius: 4px;
        background: {pal['surface_container_low']};
    }}
    QRadioButton::indicator {{
        border: 1px solid {pal['outline']};
        border-radius: 8px;
        background: {pal['surface_container_low']};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {pal['primary']};
        border-color: {pal['primary_border']};
    }}

    /* ---- group boxes --------------------------------------------------- */
    QGroupBox {{
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        margin-top: 14px;
        padding: 12px 10px 10px 10px;
        background: {pal['surface_container_low']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 6px;
        color: {pal['text_muted']};
        font-weight: 600;
    }}
    /* The Advanced tab's boxes, tinted by what they do: Luna flags in the
       Advanced-flags button's yellow, the GUI's own post-processing in the
       Wrapper-options button's green. The stripe on the left carries most
       of it, so the wash can stay faint enough not to drown the grey notes. */
    QGroupBox[tone="flag"] {{
        background: {pal['flag_tint']};
        border-left: 4px solid {pal['flag_border']};
    }}
    QGroupBox[tone="wrap"] {{
        background: {pal['wrap_tint']};
        border-left: 4px solid {pal['wrap_border']};
    }}

    /* ---- tables -------------------------------------------------------- */
    QTableView {{
        background: {pal['view']};
        alternate-background-color: {pal['surface_container']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        gridline-color: {pal['grid']};
        selection-background-color: {pal['selection']};
        selection-color: {pal['text']};
        outline: none;
    }}
    QTableView::item {{ padding: 3px 6px; border: none; }}
    QHeaderView::section {{
        background: {pal['surface_container_high']};
        color: {pal['text_muted']};
        border: none;
        border-right: 1px solid {pal['outline_variant']};
        border-bottom: 1px solid {pal['outline_variant']};
        padding: 6px 8px;
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background: {pal['surface_container_high']};
        border: none;
    }}

    /* ---- log ----------------------------------------------------------- */
    QPlainTextEdit {{
        background: {pal['view']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
    }}

    /* ---- misc ---------------------------------------------------------- */
    QProgressBar {{
        border: 1px solid {pal['outline_variant']};
        border-radius: 7px;
        background: {pal['surface_container_low']};
        text-align: center;
        height: 18px;
    }}
    QProgressBar::chunk {{ background: {pal['primary']}; border-radius: 6px; }}
    QSplitter::handle {{ background: transparent; width: 6px; }}
    QSplitter::handle:vertical {{ height: 6px; }}
    QScrollBar:vertical {{
        background: transparent; width: 11px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {pal['outline_variant']};
        border-radius: 5px; min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {pal['outline']}; }}
    QScrollBar:horizontal {{
        background: transparent; height: 11px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {pal['outline_variant']};
        border-radius: 5px; min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {pal['outline']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QListWidget {{
        background: {pal['view']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        outline: none;
    }}
    QListWidget::item:selected {{
        background: {pal['selection']};
        color: {pal['text']};
    }}

    /* ---- menu bar ------------------------------------------------------ */
    QMenuBar {{
        background: {pal['panel']};
        color: {pal['text']};
        padding: 2px 6px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 4px 10px;
        border-radius: 6px;
    }}
    QMenuBar::item:selected, QMenuBar::item:pressed {{
        background: {pal['surface_container_high']};
    }}
    QMenu {{
        background: {pal['surface_container_low']};
        color: {pal['text']};
        border: 1px solid {pal['outline_variant']};
        padding: 4px;
    }}
    QMenu::item {{ padding: 5px 28px 5px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {pal['selection']}; color: {pal['text']}; }}
    QMenu::item:disabled {{ color: {pal['text_faint']}; }}
    QMenu::separator {{
        height: 1px;
        background: {pal['outline_variant']};
        margin: 4px 8px;
    }}

    /* ---- help ---------------------------------------------------------- */
    QListWidget[nav="true"]::item:hover {{
        background: {pal['surface_container_high']};
    }}
    QTextBrowser {{
        padding: 6px 10px;
        background: {pal['view']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
    }}
    QToolTip {{
        background: {pal['surface_container_highest']};
        color: {pal['text']};
        border: 1px solid {pal['outline_variant']};
        padding: 4px 7px;
    }}
    """ + custom_qss(pal, sans, mono, size)


def custom_qss(pal: dict, sans: str, mono: str, size: int = BASE_FONT_SIZE) -> str:
    """The rules that give Luna's own widgets their meaning.

    Selected by property or by widget class, never by look: the yellow
    advanced-flags button, the green wrapper button, the accent and toggle
    buttons, the code line, the status colours, the monospaced text boxes.
    """
    small, large = max(1, size - 1), size + 1
    return f"""
    QLabel[muted="true"]  {{ color: {pal['text_muted']}; }}
    QLabel[faint="true"]  {{ color: {pal['text_faint']}; font-size: {small}pt; }}
    QLabel[role="ok"]     {{ color: {pal['success']}; }}
    QLabel[role="warn"]   {{ color: {pal['warning']}; }}
    QLabel[role="error"]  {{ color: {pal['error']}; }}
    QLabel[heading="true"] {{ font-size: {large}pt; font-weight: 600; }}
    QLabel[intro="true"]  {{ font-size: {large}pt; color: {pal['text']}; }}
    QLabel[code="true"] {{
        font-family: "{mono}";
        font-size: {large}pt;
        color: {pal['text']};
        background: {pal['surface_container_high']};
        border: 1px solid {pal['outline_variant']};
        border-left: 3px solid {pal['primary']};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton[accent="true"] {{
        background: {pal['primary']};
        border-color: {pal['primary_border']};
        color: {pal['on_primary']};
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover   {{ background: {pal['primary_hover']}; }}
    QPushButton[accent="true"]:disabled {{
        background: {pal['surface_container']};
        border-color: {pal['outline_variant']};
        color: {pal['text_faint']};
    }}
    QPushButton[toggle="true"] {{
        border-radius: 6px;
        padding: 4px 14px;
    }}
    /* Plot buttons: an outline until hovered, so a row of eight reads as
       one light strip and the filled buttons beside it as the actions. */
    QPushButton[quiet="true"] {{
        background: transparent;
        border-color: {pal['outline_variant']};
    }}
    QPushButton[quiet="true"]:hover {{
        background: {pal['surface_container_high']};
    }}
    QPushButton[quiet="true"]:pressed {{
        background: {pal['surface_container_highest']};
    }}
    QPushButton[toggle="true"]:checked {{
        background: {pal['primary']};
        border-color: {pal['primary_border']};
        color: {pal['on_primary']};
        font-weight: 600;
    }}
    /* A 1px-wide frame has no room to paint a border, so fill it instead. */
    QFrame[vline="true"] {{
        border: none;
        background: {pal['outline_variant']};
        margin: 5px 0;
    }}
    /* Advanced flags on the Process tab: grey while the run is plain,
       yellow as soon as anything deviates from it. */
    QPushButton[adv="off"] {{ color: {pal['text_faint']}; }}
    QPushButton[adv="on"] {{
        background: {pal['flag_bg']};
        border-color: {pal['flag_border']};
        color: {pal['flag_fg']};
        font-weight: 600;
    }}
    QPushButton[adv="on"]:hover {{ border-color: {pal['flag_fg']}; }}
    /* Its light-green sibling: the wrapper's own post-processing options
       (TDC columns, timewalk), visible only while one is on. */
    QPushButton[wrap="on"] {{
        background: {pal['wrap_bg']};
        border-color: {pal['wrap_border']};
        color: {pal['wrap_fg']};
        font-weight: 600;
    }}
    QPushButton[wrap="on"]:hover {{ border-color: {pal['wrap_fg']}; }}
    QPushButton[danger="true"]:hover {{
        background: {pal['surface_container_high']};
        border-color: {pal['error']};
        color: {pal['error']};
    }}
    /* The log, the file summary and the DCR report: monospaced, since their
       columns are lined up with spaces, but at the size of everything else
       rather than a point below it. */
    QPlainTextEdit {{
        font-family: "{mono}";
        font-size: {size}pt;
    }}
    QListWidget {{
        font-family: "{mono}";
        font-size: {small}pt;
    }}
    /* The help's section list reads as navigation, not as a list of paths. */
    QListWidget[nav="true"] {{
        font-family: "{sans}";
        font-size: {large}pt;
        padding: 4px 0;
    }}
    QListWidget[nav="true"]::item {{
        padding: 6px 12px;
        border-left: 3px solid transparent;
    }}
    QListWidget[nav="true"]::item:selected {{
        background: {pal['selection']};
        color: {pal['text']};
        border-left: 3px solid {pal['heading']};
    }}
    QTextBrowser {{
        font-family: "{sans}";
        font-size: {large}pt;
    }}
    """
