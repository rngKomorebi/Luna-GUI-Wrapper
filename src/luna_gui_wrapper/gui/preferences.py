"""The Preferences window: pick a theme, or build one.

Ported from daplis-rtp. Deliberately not modal. Every change is applied the
moment it is made, so the way to choose a colour is to put this window beside
the main window and watch it change. Plot settings apply to plots opened
after they are set.

Nothing here computes a look. It reads and writes
:class:`~luna_gui_wrapper.gui.theme.ThemeManager`, which is what everything
else reads too.

"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .theme import (MARKER_SIZE_RANGE, N_SERIES, PLOT_FONT_RANGE,
                    UI_FONT_RANGE, preset_names, readable_on, theme_manager)

MARGIN = 12
SPACING = 8

# The theme fields offered as colour pickers, as (field, caption, tip).
# One row per kind of thing in the window: a colour changed here changes
# that one kind of thing and nothing else.
INTERFACE_COLOURS = (
    (
        "window",
        "Window background",
        "The window and the tab pages.",
    ),
    (
        "panel",
        "Panels",
        "The menu bar, the log, the tables and lists, and the help pages.",
    ),
    (
        "surface",
        "Input fields",
        "Line edits, drop-down boxes and spin boxes, and the group boxes.",
    ),
    (
        "button",
        "Buttons",
        "Push buttons. The hover shade follows it.",
    ),
    (
        "border",
        "Borders",
        "Every thin border: fields, buttons, group boxes and the tab page.",
    ),
    (
        "text",
        "Text",
        "The main text: labels, values in the fields, button captions.",
    ),
    (
        "text_dim",
        "Secondary text",
        "Quieter text: the tabs not in front, group-box titles, table "
        "headers, notes under the controls.",
    ),
    (
        "muted",
        "Muted text",
        "The faintest text: hints, placeholders and disabled controls.",
    ),
    (
        "accent",
        "Accent",
        "Run and the other main buttons, the detector toggle, ticked boxes, "
        "the focus outline, selections, and the help's headings and links.",
    ),
)

# The status colours. Offered separately because changing them is usually
# about telling them apart - for colour blindness, or a projector that
# washes out green.
STATUS_COLOURS = (
    ("ok", "OK", "Luna found, a file converted, the wrapper-options button "
                 "(TDC columns, timewalk) while one is on."),
    (
        "warn",
        "Warning",
        "Asking for attention, and the advanced-flags button as soon as a "
        "flag differs from the plain run.",
    ),
    (
        "error",
        "Error",
        "Luna not found, a file that failed, an error in a panel.",
    ),
)

PLOT_COLOURS = (
    ("figure_bg", "Figure background", "Behind the axes, and the margin."),
    (
        "axes_bg",
        "Plot background",
        "Inside the axes. Setting it apart from the figure background "
        "frames the data; setting it the same keeps the plot flat.",
    ),
    (
        "axes_fg",
        "Ticks and labels",
        "Everything on the axes that is read as text.",
    ),
    (
        "axes_edge",
        "Axes frame",
        "The box around the data. Set it to the same colour as the "
        "ticks and labels for a plot with one axis colour; a dimmer "
        "frame under brighter text puts the emphasis on the numbers.",
    ),
    ("grid", "Grid", "The grid lines, when the grid is switched on."),
    (
        "marker",
        "Markers",
        "Reference lines over the data: the median and the noisy-pixel "
        "cut on the per-pixel DCR histogram.",
    ),
)

# Width of the colour buttons, and of the spin boxes beside them. One
# number, so that the left edge of every field in the window lines up
# with the one above it.
FIELD_WIDTH = 100

# What each series colour is actually used for, so that picking one is
# not guesswork.
SERIES_USE = (
    "Histograms, the timewalk delay, DCR vs time",
    "The timewalk jitter",
    "Spare",
    "Spare",
    "Spare",
)


class ColourButton(QtWidgets.QPushButton):
    """A button that is the colour it stands for, and opens a picker."""

    picked = QtCore.Signal(str)

    def __init__(self, colour, parent=None, title="Choose a colour"):
        super().__init__(parent)
        self._title = title
        self._colour = colour
        self.setFixedWidth(FIELD_WIDTH)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.set_colour(colour)
        self.clicked.connect(self._choose)

    def set_colour(self, colour):
        self._colour = colour
        self.setText(colour)
        # An instance stylesheet beats the application one for this
        # widget, which is what keeps the style from painting over it.
        self.setStyleSheet(
            "QPushButton {{"
            " background-color: {}; color: {};"
            " border: 1px solid #7a7a7a; padding: 3px;"
            "}}".format(colour, readable_on(colour))
        )

    def colour(self):
        return self._colour

    def _choose(self):
        chosen = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._colour), self, self._title
        )
        if chosen.isValid():
            self.set_colour(chosen.name())
            self.picked.emit(chosen.name())


class PreferencesDialog(QtWidgets.QDialog):
    """Theme, colours, font and marker sizes, applied as chosen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        # A window of its own rather than a sheet over the main window, so
        # it can be put beside what it is being used to colour.
        self.setWindowFlags(QtCore.Qt.WindowType.Window)
        self.setModal(False)

        self._manager = theme_manager()
        self._colour_buttons = {}
        self._series_buttons = []
        # Set while the widgets are being written to from the theme, so
        # that doing so does not read back as the user changing them.
        self._loading = False

        self._build_ui()
        self.reload()
        self._manager.changed.connect(self.reload)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        outer.setSpacing(SPACING)

        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(QtWidgets.QLabel("Theme", self))
        self.comboBox_preset = QtWidgets.QComboBox(self)
        for key, name in preset_names():
            self.comboBox_preset.addItem(name, key)
        self.comboBox_preset.setToolTip(
            "The colours. A starting point: any colour below can be changed "
            "afterwards; picking a theme again clears those changes."
        )
        self.comboBox_preset.activated.connect(self._preset_chosen)
        preset_row.addWidget(self.comboBox_preset, 1)
        outer.addLayout(preset_row)

        # Two columns: the window on the left, the plots on the right. One
        # long list of colours ran off a laptop screen.
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(SPACING)
        left = QtWidgets.QVBoxLayout()
        interface, status = self._interface_box(), self._status_box()
        left.addWidget(interface)
        left.addWidget(status)
        left.addStretch(1)
        right = QtWidgets.QVBoxLayout()
        plots, series = self._plot_box(), self._series_box()
        right.addWidget(plots)
        right.addWidget(series)
        right.addStretch(1)
        columns.addLayout(left)
        columns.addLayout(right, 1)
        outer.addLayout(columns, 1)
        # Each column's forms share one label width, so their fields
        # start at the same x rather than each form's own.
        self._aligned_forms = (
            (interface.layout(), status.layout()),
            (plots.layout(), series.layout()),
        )

        buttons = QtWidgets.QHBoxLayout()
        self.pushButton_reset = QtWidgets.QPushButton(
            "Reset to defaults", self
        )
        self.pushButton_reset.setToolTip(
            "Back to the Luna light theme, with the shipped font and marker "
            "sizes, throwing away every change made here."
        )
        self.pushButton_reset.clicked.connect(self._reset)
        buttons.addWidget(self.pushButton_reset)
        buttons.addStretch(1)
        close = QtWidgets.QPushButton("Close", self)
        close.clicked.connect(self.hide)
        buttons.addWidget(close)
        outer.addLayout(buttons)

    def _interface_box(self):
        box = QtWidgets.QGroupBox("Interface", self)
        form = QtWidgets.QFormLayout(box)
        form.setSpacing(SPACING)

        for field, caption, tip in INTERFACE_COLOURS:
            form.addRow(caption, self._colour_row(field, caption, tip, box))

        self.spinBox_uiFont = QtWidgets.QSpinBox(box)
        self.spinBox_uiFont.setRange(*UI_FONT_RANGE)
        self.spinBox_uiFont.setSuffix(" pt")
        # Held to the width of the colour buttons above it. A form layout
        # gives its field the whole row otherwise.
        self.spinBox_uiFont.setFixedWidth(FIELD_WIDTH)
        self.spinBox_uiFont.setToolTip(
            "Size of the text in the window. Small notes are a point "
            "below it, headings a point above."
        )
        self.spinBox_uiFont.valueChanged.connect(self._ui_font_changed)
        form.addRow("Font size", self.spinBox_uiFont)
        return box

    def _status_box(self):
        box = QtWidgets.QGroupBox("Status", self)
        form = QtWidgets.QFormLayout(box)
        form.setSpacing(SPACING)
        for field, caption, tip in STATUS_COLOURS:
            form.addRow(caption, self._colour_row(field, caption, tip, box))
        return box

    def _plot_box(self):
        box = QtWidgets.QGroupBox("Plots", self)
        form = QtWidgets.QFormLayout(box)
        form.setSpacing(SPACING)

        for field, caption, tip in PLOT_COLOURS:
            form.addRow(caption, self._colour_row(field, caption, tip, box))

        self.spinBox_plotFont = QtWidgets.QSpinBox(box)
        self.spinBox_plotFont.setRange(*PLOT_FONT_RANGE)
        self.spinBox_plotFont.setSuffix(" pt")
        self.spinBox_plotFont.setFixedWidth(FIELD_WIDTH)
        self.spinBox_plotFont.setToolTip(
            "Size of the tick labels and axis labels on the plots. Titles "
            "are drawn a step larger."
        )
        self.spinBox_plotFont.valueChanged.connect(self._plot_font_changed)
        form.addRow("Font size", self.spinBox_plotFont)

        self.spinBox_markerSize = QtWidgets.QSpinBox(box)
        self.spinBox_markerSize.setRange(*MARKER_SIZE_RANGE)
        self.spinBox_markerSize.setSuffix(" pt")
        self.spinBox_markerSize.setFixedWidth(FIELD_WIDTH)
        self.spinBox_markerSize.setToolTip(
            "Size of the dots on the traces: the timewalk curve and DCR vs "
            "time. At 0 the trace is drawn as a line alone."
        )
        self.spinBox_markerSize.valueChanged.connect(
            self._marker_size_changed
        )
        form.addRow("Marker size", self.spinBox_markerSize)

        switches = QtWidgets.QHBoxLayout()
        self.checkBox_glow = QtWidgets.QCheckBox("Glow", box)
        self.checkBox_glow.setToolTip(
            "A glow under the traces, from mplcyberpunk when it is "
            "installed (python -m pip install mplcyberpunk)."
        )
        self.checkBox_glow.toggled.connect(
            lambda on: self._override("glow", on)
        )
        switches.addWidget(self.checkBox_glow)

        self.checkBox_grid = QtWidgets.QCheckBox("Grid", box)
        self.checkBox_grid.setToolTip(
            "Grid lines behind the data, in the grid colour above. Never "
            "drawn over a hitmap."
        )
        self.checkBox_grid.toggled.connect(
            lambda on: self._override("grid_on", on)
        )
        switches.addWidget(self.checkBox_grid)
        switches.addStretch(1)
        form.addRow("", switches)
        return box

    def _series_box(self):
        box = QtWidgets.QGroupBox("Trace colours", self)
        form = QtWidgets.QFormLayout(box)
        form.setSpacing(SPACING)
        for index in range(N_SERIES):
            button = ColourButton(
                "#000000", box, "Trace {} colour".format(index + 1)
            )
            button.setToolTip(SERIES_USE[index])
            button.picked.connect(
                lambda colour, i=index: self._series_picked(i, colour)
            )
            self._series_buttons.append(button)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(button)
            caption = QtWidgets.QLabel(SERIES_USE[index], box)
            caption.setProperty("faint", True)
            caption.setObjectName("tabHint")
            row.addWidget(caption, 1)
            holder = QtWidgets.QWidget(box)
            holder.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            form.addRow("Trace {}".format(index + 1), holder)
        return box

    def _align_labels(self):
        """One label width per column, across the forms stacked in it.

        Redone on every theme change: the width follows the font size.

        """
        for forms in self._aligned_forms:
            labels = []
            for form in forms:
                for row in range(form.rowCount()):
                    item = form.itemAt(
                        row, QtWidgets.QFormLayout.ItemRole.LabelRole)
                    if item is not None and item.widget() is not None:
                        labels.append(item.widget())
            if not labels:
                continue
            for label in labels:
                # The stylesheet's font, not the default one
                label.ensurePolished()
                label.setMinimumWidth(0)
            width = max(label.sizeHint().width() for label in labels)
            for label in labels:
                label.setMinimumWidth(width)

    def _colour_row(self, field, caption, tip, parent):
        button = ColourButton(
            "#000000", parent, "{} colour".format(caption)
        )
        button.setToolTip(tip)
        button.picked.connect(
            lambda colour, name=field: self._override(name, colour)
        )
        self._colour_buttons[field] = button
        return button

    # ------------------------------------------------------------------
    # Reading the theme back into the widgets
    # ------------------------------------------------------------------

    def reload(self):
        """Show what the theme currently says.

        Connected to the theme as well as called at build time, so that
        a reset - or a theme chosen from the menu while this window is
        open - moves the controls rather than leaving them showing the
        old values.

        """
        self._loading = True
        try:
            theme = self._manager.theme
            index = self.comboBox_preset.findData(self._manager.preset_key)
            if index >= 0:
                self.comboBox_preset.setCurrentIndex(index)
            for field, button in self._colour_buttons.items():
                button.set_colour(getattr(theme, field))
            for index, button in enumerate(self._series_buttons):
                button.set_colour(theme.colour(index))
            self.spinBox_uiFont.setValue(self._manager.ui_font_size)
            self.spinBox_plotFont.setValue(self._manager.plot_font_size)
            self.spinBox_markerSize.setValue(self._manager.marker_size)
            self.checkBox_glow.setChecked(theme.glow)
            self.checkBox_grid.setChecked(theme.grid_on)
            self._align_labels()
        finally:
            self._loading = False

    # ------------------------------------------------------------------
    # Writing the widgets back into the theme
    # ------------------------------------------------------------------

    def _preset_chosen(self, index):
        if self._loading:
            return
        self._manager.set_preset(self.comboBox_preset.itemData(index))

    def _override(self, field, value):
        if self._loading:
            return
        self._manager.set_override(field, value)

    def _series_picked(self, index, colour):
        if self._loading:
            return
        self._manager.set_series_colour(index, colour)

    def _ui_font_changed(self, value):
        if self._loading:
            return
        self._manager.set_ui_font_size(value)

    def _plot_font_changed(self, value):
        if self._loading:
            return
        self._manager.set_plot_font_size(value)

    def _marker_size_changed(self, value):
        if self._loading:
            return
        self._manager.set_marker_size(value)

    def _reset(self):
        self._manager.reset()

    def open_beside(self):
        self.show()
        self.raise_()
        self.activateWindow()
