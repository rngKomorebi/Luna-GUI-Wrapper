"""Small widget helpers and the queue's check-box header."""

from __future__ import annotations

from PySide6.QtCore import QDir, QEvent, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QStyle,
                               QStyledItemDelegate, QStyleOptionViewItem,
                               QTableView, QWidget)

# ---------------------------------------------------------------------------
# small widget helpers
# ---------------------------------------------------------------------------

def vline():
    f = QFrame()
    f.setProperty("vline", True)
    f.setFixedWidth(1)
    return f


def row(*widgets, spacing=6, margins=(0, 0, 0, 0)):
    """A QWidget holding a horizontal row; None means 'stretch here'."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for item in widgets:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, str):
            lay.addWidget(QLabel(item))
        else:
            lay.addWidget(item)
    return w


class PathEdit(QLineEdit):
    """A line edit for a path that takes what Explorer hands it.

    Explorer's "Copy as path" puts quotes around the path; they are dropped
    as soon as it is pasted. A file or folder dragged in from Explorer lands
    as its path, not as a file:/// URL, and announces itself through
    path_dropped so the owner can act on it straight away.
    """

    path_dropped = Signal(str)

    def __init__(self, text=""):
        super().__init__(text)
        self.textChanged.connect(self._unquote)

    def _unquote(self, text):
        s = text.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            self.setText(s[1:-1])

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()
        else:
            super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()
        else:
            super().dragMoveEvent(ev)

    def dropEvent(self, ev):
        urls = [u for u in ev.mimeData().urls() if u.isLocalFile()]
        if not urls:
            super().dropEvent(ev)
            return
        self.setText(QDir.toNativeSeparators(urls[0].toLocalFile()))
        ev.acceptProposedAction()
        self.path_dropped.emit(self.text())


class PathsEdit(QPlainTextEdit):
    """A box of paths, one per line; files or folders dragged in from
    Explorer are added as their paths, each on its own line."""

    def canInsertFromMimeData(self, source):
        return source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        urls = [u for u in source.urls() if u.isLocalFile()] if source.hasUrls() else []
        if not urls:
            super().insertFromMimeData(source)
            return
        text = self.toPlainText()
        if text and not text.endswith("\n"):
            self.moveCursor(self.textCursor().MoveOperation.End)
            self.insertPlainText("\n")
        self.insertPlainText("\n".join(QDir.toNativeSeparators(u.toLocalFile())
                                       for u in urls) + "\n")


def button(text, slot=None, accent=False, toggle=False, danger=False, tip="",
           quiet=False):
    """A themed push button. `quiet` draws it as an outline that fills on
    hover: for rows of many equal buttons (plots), so the few filled ones --
    the actions -- stand out."""
    b = QPushButton(text)
    if accent:
        b.setProperty("accent", True)
    if quiet:
        b.setProperty("quiet", True)
    if danger:
        b.setProperty("danger", True)
    if toggle:
        b.setProperty("toggle", True)
        b.setCheckable(True)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


# ---------------------------------------------------------------------------
# themed check box, drawn by hand
# ---------------------------------------------------------------------------

def paint_check_box(painter, box, state, pal):
    """The QCheckBox::indicator look, painted into box (a QRectF).

    Shared by the queue header and the queue rows, so the master box and the
    per-file boxes are one shape in one set of colours. Leaves the painter's
    pen and brush changed: callers wrap it in save()/restore().
    """
    checked = state == Qt.CheckState.Checked
    partial = state == Qt.CheckState.PartiallyChecked
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    fill = pal["primary"] if checked or partial else pal["surface_container_low"]
    edge = pal["primary_border"] if checked or partial else pal["outline"]
    painter.setPen(QPen(QColor(edge), 1))
    painter.setBrush(QColor(fill))
    painter.drawRoundedRect(box, 4, 4)

    mark = QPen(QColor(pal["on_primary"]), 2,
                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin)
    if checked:
        path = QPainterPath()
        path.moveTo(box.x() + box.width() * 0.24, box.y() + box.height() * 0.52)
        path.lineTo(box.x() + box.width() * 0.44, box.y() + box.height() * 0.72)
        path.lineTo(box.x() + box.width() * 0.78, box.y() + box.height() * 0.28)
        painter.setPen(mark)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    elif partial:
        painter.setPen(mark)
        painter.drawLine(int(box.x() + box.width() * 0.25),
                         int(box.center().y()),
                         int(box.x() + box.width() * 0.75),
                         int(box.center().y()))


class CheckHeader(QHeaderView):
    """Horizontal header that draws a master checkbox in one section.

    The box is painted by hand rather than through PE_IndicatorCheckBox: under
    a stylesheet the QCheckBox::indicator rules only reach real QCheckBoxes, so
    a style-drawn indicator here would ignore the theme. Same shape, same
    colours, drawn from the same palette.

    Clicking anywhere on the section emits box_clicked; the owner decides what
    "tick everything" means and pushes the result back through set_state(), so
    the header never second-guesses the model.
    """

    box_clicked = Signal()
    BOX = 15                            # matches QCheckBox::indicator in the QSS

    def __init__(self, column, palette, label="", parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.box_col = column
        self.pal = palette
        self.label = label
        self.box_state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)

    # Toggled on the press itself, not through sectionClicked. A quick second
    # click arrives as a double-click event, and with sectionClicked the pair
    # could cancel out -- the box looked stuck. Here each click is one toggle,
    # however fast they come.
    def _box_press(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.logicalIndexAt(event.position().toPoint()) == self.box_col):
            self.box_clicked.emit()
            event.accept()
            return True
        return False

    def mousePressEvent(self, event):
        if not self._box_press(event):
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self._box_press(event):
            super().mouseDoubleClickEvent(event)

    def set_palette(self, palette):
        self.pal = palette
        self.updateSection(self.box_col)

    def set_state(self, state):
        if state != self.box_state:
            self.box_state = state
            self.updateSection(self.box_col)

    def paintSection(self, painter, rect, index):
        # The model reports an empty title for this section, so the base class
        # paints the themed background and nothing else; the box and the label
        # go on top of it here.
        #
        # save()/restore() around the base call is not optional: it leaves the
        # painter with an empty clip region, and anything drawn afterwards is
        # silently clipped away.
        painter.save()
        super().paintSection(painter, rect, index)
        painter.restore()
        if index != self.box_col:
            return
        box = QRectF(rect.x() + 8.5,
                     rect.y() + (rect.height() - self.BOX) / 2.0 + 0.5,
                     self.BOX - 1, self.BOX - 1)
        painter.save()
        paint_check_box(painter, box, self.box_state, self.pal)

        if self.label:
            painter.setPen(QColor(self.pal["text_muted"]))
            text = QRect(int(box.right()) + 7, rect.y(),
                         rect.right() - int(box.right()) - 11, rect.height())
            painter.drawText(text, int(Qt.AlignmentFlag.AlignLeft |
                                       Qt.AlignmentFlag.AlignVCenter),
                             painter.fontMetrics().elidedText(
                                 self.label, Qt.TextElideMode.ElideRight,
                                 text.width()))
        painter.restore()


class CheckDelegate(QStyledItemDelegate):
    """Per-row check box for one table column, in the CheckHeader look.

    The style-drawn indicator ignored the theme: ticked it was a bare mark in
    the row's status colour (green on a done file), unticked a dark square that
    vanished into the row, and only a hit on that small square counted. Here
    the box is drawn like the header's, and a click anywhere in the cell
    toggles it -- through the model's setData, as before.
    """

    BOX = CheckHeader.BOX

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.pal = palette

    def set_palette(self, palette):
        self.pal = palette

    def paint(self, painter, option, index):
        # Background and selection as for any other cell, then the box.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter,
                          opt.widget)
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        if state is None:
            return                      # nothing to overwrite: no box at all
        r = option.rect
        box = QRectF(r.x() + 8.5, r.y() + (r.height() - self.BOX) / 2.0 + 0.5,
                     self.BOX - 1, self.BOX - 1)
        painter.save()
        paint_check_box(painter, box, Qt.CheckState(state), self.pal)
        painter.restore()

    @staticmethod
    def _toggle(model, index):
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        ticked = state is not None and Qt.CheckState(state) == Qt.CheckState.Checked
        new = Qt.CheckState.Unchecked if ticked else Qt.CheckState.Checked
        return model.setData(index, new.value, Qt.ItemDataRole.CheckStateRole)

    def editorEvent(self, event, model, option, index):
        if not (index.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return False
        t = event.type()
        # On the press, and on a double-click's second press too, so two quick
        # clicks are two toggles rather than one that the other undoes.
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            return self._toggle(model, index)
        if t == QEvent.Type.MouseButtonRelease:
            return True                 # already handled on the press
        if (t == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)):
            return self._toggle(model, index)
        return False


def table(model, stretch_cols=(), widths=()):
    v = QTableView()
    v.setModel(model)
    v.setAlternatingRowColors(True)
    v.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    v.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    v.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    v.verticalHeader().setVisible(False)
    v.verticalHeader().setDefaultSectionSize(24)
    v.setShowGrid(False)
    hdr = v.horizontalHeader()
    hdr.setHighlightSections(False)
    hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for i, w in enumerate(widths):
        v.setColumnWidth(i, w)
    for i in range(model.columnCount()):
        hdr.setSectionResizeMode(
            i, QHeaderView.ResizeMode.Stretch if i in stretch_cols
            else QHeaderView.ResizeMode.Interactive)
    return v
