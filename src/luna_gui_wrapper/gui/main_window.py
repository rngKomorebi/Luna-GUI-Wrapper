"""The main window: Process, Advanced and Inspect HDF5 tabs."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
import traceback
from collections import deque
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QActionGroup, QFontDatabase, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox,
    QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QRadioButton, QScrollArea,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget)

from .. import __version__
from ..functions.backend import (Backend, detect_backend, drive_letter,
                                 win_to_wsl, wsl_missing_paths,
                                 wsl_mount_drive, wsl_unmounted_drives)
from ..functions.common import (_NO_WINDOW, APP_NAME, ICON_PATH, IS_WINDOWS,
                                human_size)
from ..functions.config import load_config, save_config
from ..functions.dcr import (DCR_DEFAULT_NOISY_K, DCR_DEFAULT_TIME_SOURCE,
                             TIME_SOURCES, dcr_maps, dcr_report,
                             find_measurement_metadata, fmt_rate,
                             measure_dcr, pick_time, write_dcr_csv)
from ..functions.detectors import DETECTORS, TPX3, TPX4, detect_from_file
from ..functions.failures import diagnose, still_fails
from ..functions.flags import (FLAG_GROUPS, FLAGS, flag_args, flag_bits,
                               flag_problems)
from ..functions.naming import (DEFAULT_TEMPLATE, PRESET_TEMPLATES,
                                TEMPLATE_HELP, Job, measurement_context,
                                migrate_template, render_name)
from ..functions.plotting import (CSIZE_BINS, CSIZE_MAX, HITMAP_CLIP_FACTOR,
                                  HITMAP_CLIP_PERCENTILE, PLOT_FIGSIZE,
                                  PLOT_TITLES, STOT_TARGET_BINS, TOT_MAX_BINS,
                                  plot_style_context, tot_bin_edges)
from ..functions.tdc import (TDC_DATASET, TDC_REFERENCES,
                             TDC_SECONDS_PER_TICK, TDC_SOURCES, TDC_STAMP,
                             TOF_TDC_REFERENCES, add_tdc_columns,
                             describe_tdc_types, read_tdc_events, read_tdcs,
                             read_with_tdc, tag_times_with_tdc,
                             tdc_reference_edges)
from ..functions.timewalk import (TW_CURVE, TW_DEFAULT_CTOT_CUT_NS,
                                  TW_FIELD_ATTR, TW_FIELDS, TW_STAMP,
                                  add_timewalk_columns, measure_timewalk)
from .dataset_view import DatasetViewer
from .help_window import SECTIONS, HelpWindow
from .models import FolderModel, JobModel
from .preferences import PreferencesDialog
from .theme import preset_group, preset_names, theme_manager
from .widgets import (CheckHeader, PathEdit, PathsEdit, button, row, table,
                      vline)

# ---------------------------------------------------------------------------
# optional scientific stack (Inspect tab only)
# ---------------------------------------------------------------------------

# Converter lines worth keeping for diagnosing a failure. Only tested on the
# first line of each kind, so the cost stays off the per-line path.
_ALARM = re.compile(r"panicked at|^error|error:|no space left|permission denied|"
                    r"skipping file", re.IGNORECASE)
# Luna's "[crates/.../file.rs:137] [thread: Name]" location prefix.
_LOG_PREFIX = re.compile(r"^\[[^\]]*\]\s*\[thread:[^\]]*\]\s*")
# Blanks the digits out of a log line, so lines of one kind compare equal.
# A translate table rather than a regex: it runs once per line of converter
# output, which can be hundreds of thousands of lines per file.
_DIGITS = str.maketrans("0123456789", "##########")


def require_h5py(parent=None):
    try:
        import h5py
        import numpy
        return h5py, numpy
    except Exception:
        QMessageBox.critical(
            parent, APP_NAME,
            "This panel needs h5py and numpy.\n\n"
            "Install them into the interpreter running this GUI:\n"
            "    python -m pip install h5py numpy")
        return None, None


def require_pandas(parent=None):
    try:
        import pandas
        return pandas
    except Exception:
        QMessageBox.critical(
            parent, APP_NAME,
            "This panel needs pandas.\n\n"
            "Install it into the interpreter running this GUI:\n"
            "    python -m pip install pandas")
        return None

# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        migrate_template(self.cfg)    # one-time move onto the current default name
        self.jobs = []
        self.folders = []
        self.backend = Backend()
        self.proc = None
        self.todo = []
        self.stopping = False
        self.total = self.done = self.ok = self.failed = 0
        self.t_all = self.t_job = 0.0
        self.cur = -1
        # Which Luna converter, raw files and units: Timepix3 or Timepix4.
        self.det = DETECTORS.get(self.cfg.get("detector"), TPX3)
        # The converter's output, buffered on its way into the log.
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_output)
        self._reset_output()

        # The theme: one process-wide manager (theme.py), which also serves
        # Preferences. self.pal is the stylesheet's palette for the current
        # theme, read by the models, the queue header and Help.
        self._manager = theme_manager()
        self.pal = self._manager.palette()
        self.sans, self.mono = self._manager.fonts()
        self._preferences = None      # built on first use, then kept

        self.setWindowTitle(APP_NAME)
        # The layout's own minimum is 841x746 and its preferred hint 841x780,
        # but 841 wide cramps the six-column Files found table, so open a bit
        # wider than strictly needed and let the user shrink from there.
        # Whatever is asked for must never exceed the desktop it opens on: a
        # 1080p panel at 125% scaling leaves only 1536x832 of usable logical
        # space. _fit_to_screen() does the exact correction below, once the
        # frame size is knowable.
        avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.resize(min(1080, avail.width()), min(760, avail.height()))
        self.setMinimumSize(min(840, avail.width()), min(620, avail.height()))
        self._fitted = False
        if ICON_PATH:
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self.job_model = JobModel(self)
        self.folder_model = FolderModel(self)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        # header: title (the theme lives in the View menu)
        title = QLabel(APP_NAME)
        title.setProperty("heading", True)
        outer.addWidget(title)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.tab_process = QWidget()
        self.tab_advanced = QWidget()
        self.tab_inspect = QWidget()
        self.tabs.addTab(self.tab_process, "Process")
        self.tabs.addTab(self.tab_advanced, "Advanced")
        self.tabs.addTab(self.tab_inspect, "Inspect HDF5")

        # Advanced first: it owns every option widget the others read.
        self._build_advanced(self.tab_advanced)
        self._build_process(self.tab_process)
        self._build_inspect(self.tab_inspect)
        self._connect_option_signals()
        self.help = None              # built on first use, then kept
        self._build_menu()

        self._manager.changed.connect(self._theme_changed)
        self._theme_changed()
        self.apply_detector()

        # Restore last session's batch; deferred so the window paints first
        # even when the folders live on a slow or absent disk.
        self._load_folders()
        if self.folders:
            QTimer.singleShot(300, self.scan_folders)

    # -- detector ---------------------------------------------------------

    def _det_key(self, base, det=None):
        """Settings key for state kept per detector. Timepix3 keeps the
        historical key, so an existing install loses nothing."""
        det = det or self.det
        return base if det is TPX3 else base + "_" + det.key

    def _load_folders(self):
        saved = self.cfg.get(self._det_key("folders")) or []
        self.folders = [{"path": f.get("path", ""),
                         "recursive": bool(f.get("recursive", True)),
                         "count": None}
                        for f in saved if isinstance(f, dict) and f.get("path")]
        self.folder_model.reset()

    def _store_detector_state(self):
        """The current detector's Luna folder and batch, into the settings."""
        self.cfg[self._det_key("luna_dir")] = self.e_luna.text()
        self.cfg[self._det_key("folders")] = [
            {"path": f["path"], "recursive": f["recursive"]} for f in self.folders]

    def switch_detector(self, key):
        """Change between Timepix3 and Timepix4.

        Each keeps its own Luna folder and batch folders, so switching swaps
        the whole setup rather than scanning Timepix3 folders for .tpx4
        files. The flag values are shared; only the current converter's are
        shown and passed.
        """
        new = DETECTORS[key]
        if new is self.det:
            self.apply_detector()           # re-check the toggle it unchecked
            return
        if self.proc is not None:
            QMessageBox.information(self, APP_NAME,
                                    "Wait for the run to finish, or stop it, "
                                    "before switching detector.")
            self.apply_detector()
            return
        self._store_detector_state()
        self.det = new
        self.cfg["detector"] = new.key
        self.e_luna.setText(self.cfg.get(self._det_key("luna_dir"), ""))
        self.jobs = []
        self._load_folders()
        self.apply_detector()
        self.log(f"Switched to {new.name}: {new.exe}, {new.suffix} files.")
        if self.folders:
            self.scan_folders()
        else:
            self.recompute_outputs()

    def apply_detector(self):
        """Bring every detector-dependent label and control in line."""
        d = self.det
        self.b_tpx3.setChecked(d is TPX3)
        self.b_tpx4.setChecked(d is TPX4)
        self.e_luna.setPlaceholderText(f"the folder containing bin/{d.exe}")
        self.lbl_intro_cmd.setText(f"{d.exe} process -i NAME{d.suffix} -o NAME.hdf5")
        self.lbl_intro_tail.setText(
            f"for every queued file, writing the .hdf5 beside its {d.suffix}.")
        self.g_opt.setTitle(f"{d.exe} flags  (blank = {d.exe}'s own default)")
        for f in FLAGS:
            for w in self.flag_rows[f.key]:
                w.setVisible(d.key in f.detectors)
        for cap, group in self.flag_caps:
            cap.setVisible(any(d.key in f.detectors for f in group))
        # tpx4dump records no TDC edges, so there is nothing to tag from. The
        # timewalk row stays: it needs only hits and clusters.
        self.w_tdc_row.setVisible(d is TPX3)
        self.b_add_folders.setToolTip(
            f"Queue every {d.suffix} found under one or more folders")
        self.refresh_backend()
        self.update_adv_summary()

    # -- theme ------------------------------------------------------------

    def _theme_changed(self):
        """Restyle everything after the theme or a size changed.

        Connected to the theme manager, so a choice from the View menu and a
        colour picked in Preferences take the same path.
        """
        m = self._manager
        self.pal = m.palette()
        m.apply_to_app(QApplication.instance())
        self._sync_theme_menu()
        self.b_rerun.ensurePolished()
        self.cap_l.setMinimumHeight(self.b_rerun.sizeHint().height())
        # Repaint model-driven colours (status text) under the new palette,
        # including the hand-drawn checkbox in the queue header.
        if getattr(self, "jhead", None):
            self.jhead.set_palette(self.pal)
        if getattr(self, "help", None):
            self.help.set_palette(self.pal, m.ui_font_size)
        self.job_model.reset()
        self.sync_overwrite_header()
        self.folder_model.reset()
        self.refresh_backend()
        self.update_adv_summary()

    # -- process tab ------------------------------------------------------

    def _build_process(self, tab):
        """The main window: pick input, press Run. Nothing else.

        On its own this tab is exactly
            tpx3dump process -i NAME.tpx3 -o NAME.hdf5
        for every queued file. Anything that changes that lives on Advanced.
        """
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)

        self.lbl_status = QLabel("")
        self.b_setup = button("Set up Luna...", self.goto_advanced)
        # Non-default settings are invisible from here otherwise, and silently
        # renamed or relocated output is the surprise worth never having: the
        # button turns yellow the moment anything deviates from the plain run,
        # and lists it all on a click.
        self.b_adv = button("Advanced flags", self.show_adv_flags)
        # Its green sibling: what this GUI does after Luna (TDC columns,
        # timewalk), shown only while one of those is switched on.
        self.b_wrap = button("Wrapper options", self.show_wrapper_options)
        self.b_wrap.setProperty("wrap", "on")
        self.b_wrap.setVisible(False)
        # Which detector the batch is for: picks the Luna converter, the raw
        # files a folder scan queues, and the flags on offer.
        self.b_tpx3 = button("Timepix3", lambda: self.switch_detector("tpx3"),
                             toggle=True, tip="Process .tpx3 files with tpx3dump")
        self.b_tpx4 = button("Timepix4", lambda: self.switch_detector("tpx4"),
                             toggle=True, tip="Process .tpx4 files with tpx4dump")
        cap_det = QLabel("Detector")
        cap_det.setProperty("muted", True)
        lay.addWidget(row(cap_det, self.b_tpx3, self.b_tpx4, vline(),
                          self.lbl_status, None, self.b_wrap, self.b_adv,
                          self.b_setup,
                          spacing=6))

        # Additive actions on the left, the destructive one pushed to the far
        # right so "Clear" can never be hit while reaching for "Add".
        self.b_add_folders = button("Add folders...", self.add_folders_dialog)
        cap_in = QLabel("Input")
        cap_in.setProperty("muted", True)
        lay.addWidget(row(
            cap_in,
            self.b_add_folders,
            vline(),
            button("Rescan", self.scan_folders,
                   tip="Re-read the batch folders and queue anything new"),
            None,
            button("Clear", self.clear_queue, danger=True,
                   tip="Empty the queue and the folder list"),
        ))

        self.b_run = button("Run queue", self.run_queue, accent=True)
        self.b_stop = button("Stop", self.stop_run)
        self.b_stop.setEnabled(False)
        self.lbl_prog = QLabel("")
        self.pb = QProgressBar()
        self.pb.setFixedWidth(240)
        self.pb.setValue(0)
        self.pb.setTextVisible(False)      # only meaningful during a run
        self.pb.setVisible(False)          # and an empty bar is just noise
        # Run controls only. "Clear log" used to sit here despite having
        # nothing to do with running; it now lives on the log's own header.
        lay.addWidget(row(self.b_run, self.b_stop, None, self.lbl_prog, self.pb))

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(4)
        cap_l = QLabel("Folders to process")
        cap_l.setProperty("muted", True)
        llay.addWidget(cap_l)
        self.ftable = table(self.folder_model, stretch_cols=(0,), widths=(230, 56, 72))
        llay.addWidget(self.ftable, 1)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(4)
        cap_r = QLabel("Files found")
        cap_r.setProperty("muted", True)
        # Pushed to the right edge, so it sits above the Overwrite column it
        # works through. Live only once something has failed.
        self.b_rerun = button("Rerun failed", self.rerun_failed,
                              tip="No file has failed")
        self.b_rerun.setEnabled(False)
        self.b_rerun.setProperty("adv", "off")
        rlay.addWidget(row(cap_r, None, self.b_rerun))
        # Same height for the left caption, so the two tables start level.
        # Measured again on every theme change (_theme_changed): the font
        # size and the style both change the button's height.
        self.cap_l = cap_l
        cap_l.setMinimumHeight(self.b_rerun.sizeHint().height())
        self.jtable = table(self.job_model, stretch_cols=(3,),
                            widths=(110, 175, 70, 320, 108))
        self.jhead = CheckHeader(JobModel.OVER, self.pal,
                                 JobModel.HEADERS[JobModel.OVER], self.jtable)
        self.jtable.setHorizontalHeader(self.jhead)
        self.jhead.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft
                                       | Qt.AlignmentFlag.AlignVCenter)
        self.jhead.setHighlightSections(False)
        for i in range(self.job_model.columnCount()):
            self.jhead.setSectionResizeMode(
                i, QHeaderView.ResizeMode.Stretch if i == 3
                else QHeaderView.ResizeMode.Interactive)
        for i, w in enumerate((110, 175, 70, 320, 108)):
            self.jtable.setColumnWidth(i, w)
        self.jhead.setSectionsClickable(True)   # setHorizontalHeader can reset it
        self.jhead.box_clicked.connect(self.toggle_all_overwrite)
        self.jtable.doubleClicked.connect(self._job_double_clicked)
        rlay.addWidget(self.jtable, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 3)

        cap_log = QLabel("Log")
        cap_log.setProperty("muted", True)
        lay.addWidget(row(cap_log, None,
                          button("Save log...", self.save_log,
                                 tip="Write the whole log to a text file"),
                          button("Clear log", lambda: self.log_view.clear())))

        # No line cap: a long batch's log is kept whole. The repeat collapsing
        # in _take_line keeps it to a few dozen lines per file, which a
        # QPlainTextEdit takes in its stride even for thousands of files.
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.log_view, 2)

    # -- advanced tab -----------------------------------------------------

    def _build_advanced(self, tab):
        """Everything that is not "-i FILE.tpx3 -o FILE.hdf5"."""
        # Scrolls rather than squeezes. Four groups of options are taller than
        # a laptop screen at 125% scaling leaves room for, and the window's
        # explicit minimum size lets it go shorter than this layout's own
        # minimum -- without a scroll area Qt then crushes the line edits and
        # combos below their height and they paint over one another.
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)   # the tab pane shows
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)

        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        # The one thing worth knowing before touching anything below, so it
        # reads first: larger text, and the command as a code block.
        intro = QVBoxLayout()
        intro.setSpacing(6)
        head = QLabel("All optional. Left alone, the Process tab runs exactly")
        head.setProperty("intro", True)
        # Both texts follow the detector; apply_detector() fills them in.
        cmd = self.lbl_intro_cmd = QLabel("")
        cmd.setProperty("code", True)
        cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tail = self.lbl_intro_tail = QLabel("")
        tail.setProperty("intro", True)
        intro.addWidget(head)
        intro.addWidget(row(cmd, None, margins=(14, 0, 0, 0)))
        intro.addWidget(tail)
        lay.addLayout(intro)

        # Luna install ----------------------------------------------------
        g_luna = QGroupBox("Luna installation")
        gl = QGridLayout(g_luna)
        gl.setHorizontalSpacing(8)
        gl.setVerticalSpacing(8)
        gl.setColumnStretch(1, 1)
        gl.addWidget(QLabel("Folder:"), 0, 0)
        self.e_luna = PathEdit(self.cfg.get(self._det_key("luna_dir"), ""))
        self.e_luna.setPlaceholderText("the folder containing bin/tpx3dump")
        self.e_luna.editingFinished.connect(self.refresh_backend)
        self.e_luna.path_dropped.connect(lambda _p: self.refresh_backend())
        gl.addWidget(self.e_luna, 0, 1)
        gl.addWidget(button("Browse...", self.pick_luna), 0, 2)
        gl.addWidget(button("Check install", self.check_install), 0, 3)
        self.lbl_backend = QLabel("")
        self.lbl_backend.setWordWrap(True)
        gl.addWidget(self.lbl_backend, 1, 0, 1, 4)
        lay.addWidget(g_luna)

        # Output ----------------------------------------------------------
        g_out = QGroupBox("Output")
        go = QGridLayout(g_out)
        go.setHorizontalSpacing(8)
        go.setVerticalSpacing(8)
        go.setColumnStretch(1, 1)
        self.rb_beside = QRadioButton("Next to the input file")
        self.rb_flat = QRadioButton("Output folder (flat)")
        self.rb_mirror = QRadioButton("Output folder (mirror tree)")
        mode = self.cfg.get("out_mode", "beside")
        {"beside": self.rb_beside, "flat": self.rb_flat,
         "mirror": self.rb_mirror}.get(mode, self.rb_beside).setChecked(True)
        for rb in (self.rb_beside, self.rb_flat, self.rb_mirror):
            rb.toggled.connect(lambda _c: self.recompute_outputs())
        go.addWidget(row(self.rb_beside, self.rb_flat, self.rb_mirror, None,
                         spacing=18), 0, 0, 1, 3)

        go.addWidget(QLabel("Output folder:"), 1, 0)
        self.e_outdir = PathEdit(self.cfg.get("out_dir", ""))
        self.e_outdir.setPlaceholderText("used by the two 'Output folder' modes")
        self.e_outdir.textChanged.connect(lambda _t: self.recompute_outputs())
        go.addWidget(self.e_outdir, 1, 1)
        self.b_outdir = button("Browse...", self.pick_outdir)
        go.addWidget(self.b_outdir, 1, 2)

        go.addWidget(QLabel("Name template:"), 2, 0)
        self.e_template = QLineEdit(self.cfg.get("template", DEFAULT_TEMPLATE))
        self.e_template.textChanged.connect(lambda _t: self.recompute_outputs())
        go.addWidget(self.e_template, 2, 1)
        go.addWidget(button("Presets...", self.template_presets), 2, 2)

        # One unwrapped line: a word-wrapped QLabel is height-for-width, which
        # a grid inside a group box sizes unreliably.
        ph = QLabel("placeholders:  " + TEMPLATE_HELP)
        ph.setProperty("faint", True)
        ph.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        go.addWidget(ph, 3, 1, 1, 2)

        self.cb_skip = QCheckBox("Skip files whose output already exists")
        self.cb_skip.setChecked(bool(self.cfg.get("skip_existing", True)))
        skip_hint = QLabel("untick to overwrite them all -- or tick "
                           "'Overwrite' on single rows of the queue")
        skip_hint.setProperty("faint", True)
        go.addWidget(row(self.cb_skip, skip_hint, None, spacing=10),
                     4, 0, 1, 3)
        lay.addWidget(g_out)

        # Flags -------------------------------------------------------------
        # One flag per row -- name, control, a one-line note -- built from
        # FLAG_GROUPS, so the notes line up in a column and a new flag needs
        # no layout work. The full story is in each row's tooltip.
        # Every flag is built; apply_detector() shows the ones the current
        # converter accepts and titles the group after it.
        g_opt = self.g_opt = QGroupBox("")
        gf = QGridLayout(g_opt)
        gf.setHorizontalSpacing(10)
        gf.setVerticalSpacing(6)
        gf.setColumnStretch(2, 1)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self.flag_w = {}
        self.flag_rows = {}            # key -> the row's widgets, to show/hide
        self.flag_caps = []            # (caption, its flags)
        r = 0
        for title, group in FLAG_GROUPS:
            cap = QLabel(title)
            cap.setProperty("muted", True)
            # Air above every group but the first, as the caption's own margin
            # so a group hidden for this detector takes its gap with it.
            if r:
                cap.setContentsMargins(0, 10, 0, 0)
            gf.addWidget(cap, r, 0, 1, 3)
            self.flag_caps.append((cap, group))
            r += 1
            for f in group:
                label = QLabel(f.flag)
                note = QLabel(f.note)
                note.setProperty("faint", True)
                ctl = self._flag_control(f)
                tip = f.note + (".\n\n" + f.tip if f.tip else ".")
                if f.default:
                    tip += "\n\nDefault: " + f.default
                tip += "\nFor: " + " and ".join(DETECTORS[k].name for k in f.detectors)
                for w in (label, ctl, note):
                    w.setToolTip(tip)
                self.flag_rows[f.key] = (label, ctl, note)
                gf.addWidget(label, r, 0, right)
                if f.kind == "path":
                    # A path needs the width; its note goes underneath.
                    gf.addWidget(ctl, r, 1, 1, 2)
                    r += 1
                    gf.addWidget(note, r, 1, 1, 2)
                else:
                    gf.addWidget(ctl, r, 1)
                    gf.addWidget(note, r, 2)
                r += 1

        gf.setRowMinimumHeight(r, 10)
        gf.addWidget(QLabel("extra arguments"), r + 1, 0, right)
        self.e_extra = QLineEdit(self.cfg.get("extra", ""))
        gf.addWidget(self.e_extra, r + 1, 1, 1, 2)
        hint = QLabel("Passed verbatim, after the flags above -- "
                      "'Check install' prints the authoritative flag list.")
        hint.setProperty("faint", True)
        gf.addWidget(hint, r + 2, 1, 1, 2)
        gf.addWidget(row(None, button("All flags explained...",
                                      lambda: self.show_help("flags"))),
                     r + 3, 0, 1, 3)
        lay.addWidget(g_opt)

        # Wrapper options ----------------------------------------------------
        # Not Luna flags: after Luna finishes, the GUI reopens each .hdf5 and
        # writes these columns into it itself. Kept in a box of their own so
        # they are never mistaken for flags passed to tpx3dump / tpx4dump.
        g_post = self.g_post = QGroupBox(
            "Wrapper options  (run by this GUI after Luna, not Luna flags)")
        gpv = QVBoxLayout(g_post)
        gpv.setSpacing(6)
        # Its own widget, so Timepix4 can hide the TDC row and keep the rest.
        self.w_tdc_row = QWidget()
        gp = QHBoxLayout(self.w_tdc_row)
        gp.setContentsMargins(0, 0, 0, 0)
        gp.setSpacing(8)
        gpv.addWidget(self.w_tdc_row)
        self.cb_tdc = QCheckBox("Add TDC columns to each output .hdf5")
        self.cb_tdc.setChecked(bool(self.cfg.get("tdc_columns", False)))
        self.cb_tdc.setToolTip(
            "Tag every pixel hit and cluster with the TDC edge it follows, and "
            "write the result into the output file as /PixelHitsTDC and "
            "/ClustersTDC. The datasets tpx3dump wrote are left untouched.")
        gp.addWidget(self.cb_tdc)
        gp.addSpacing(10)
        gp.addWidget(QLabel("reference:"))
        self.c_tdcref = QComboBox()
        self.c_tdcref.addItems(TDC_REFERENCES)
        self.c_tdcref.setCurrentText(self.cfg.get("tdc_reference",
                                                  TDC_REFERENCES[0]))
        self.c_tdcref.setMinimumWidth(130)
        self.c_tdcref.setEnabled(self.cb_tdc.isChecked())
        self.cb_tdc.toggled.connect(self.c_tdcref.setEnabled)
        gp.addWidget(self.c_tdcref)
        gp.addStretch(1)

        # Timewalk: measured from the file's own clusters, no TDC needed.
        self.cb_tw = QCheckBox("Timewalk-correct each output .hdf5")
        self.cb_tw.setChecked(bool(self.cfg.get("timewalk_columns", False)))
        self.cb_tw.setToolTip(
            "Measure the timewalk curve from the file's own clusters (each "
            "hit's ToA relative to the largest-ToT pixel of its cluster) and "
            "add the timewalk-corrected cluster time as a last column of "
            "Clusters (ctoa_tw), plus the curve as /TimewalkCurve. Needs pixel "
            "hits and clusters; no TDC. Adding a column rewrites the file once, "
            "which needs free space for one more copy of it.")
        self.sp_tw_cut = self._ctot_cut_spin(
            self.cfg.get("timewalk_ctot_cut", TW_DEFAULT_CTOT_CUT_NS))
        self.cb_tw_hits = QCheckBox("also every pixel hit (slower)")
        self.cb_tw_hits.setChecked(bool(self.cfg.get("timewalk_hits", False)))
        self.cb_tw_hits.setToolTip(
            "Also add the corrected time of every pixel hit as a last column "
            "of PixelHits (toa_tw): 8 more bytes per hit. Without it, "
            "read_with_timewalk() still computes toa_tw on the fly from the "
            "stored curve.")
        for w in (self.sp_tw_cut, self.cb_tw_hits):
            w.setEnabled(self.cb_tw.isChecked())
            self.cb_tw.toggled.connect(w.setEnabled)
        gt = QHBoxLayout()
        gt.setSpacing(8)
        gt.addWidget(self.cb_tw)
        gt.addSpacing(10)
        gt.addWidget(QLabel("ctot cut:"))
        gt.addWidget(self.sp_tw_cut)
        gt.addSpacing(10)
        gt.addWidget(self.cb_tw_hits)
        gt.addStretch(1)
        gpv.addLayout(gt)
        lay.addWidget(g_post)
        lay.addStretch(1)

        # Outside the scroll area, so the actions stay in reach however far
        # the options above have been scrolled.
        outer.addWidget(row(
            button("Preview commands", self.preview),
            button("Export .sh", self.export_sh),
            button("Reset to defaults", self.reset_advanced),
            None,
            button("Back to Process", lambda: self.tabs.setCurrentWidget(self.tab_process)),
            margins=(12, 6, 12, 10)))

    def _flag_control(self, f):
        """The input widget for one tpx3dump flag, filled from the settings."""
        saved = self.cfg.get(f.key, "")
        if f.kind == "switch":
            cb = QCheckBox()
            cb.setChecked(bool(saved))
            self.flag_w[f.key] = cb
            return cb
        if f.kind in ("choice", "switch_choice"):
            # Item data is what gets passed; a plain choice leads with an
            # entry naming tpx3dump's default, whose data "" passes nothing.
            c = QComboBox()
            if f.kind == "choice":
                c.addItem(f"default ({f.default})", "")
            for ch in f.choices:
                if ch:
                    c.addItem(ch, ch)
            c.setCurrentIndex(max(c.findData(str(saved)), 0))
            c.setFixedWidth(170)
            self.flag_w[f.key] = c
            if f.kind == "choice":
                return c
            # The flag takes a value, so the checkbox -- not a blank combo
            # entry -- decides whether it is passed at all. That way an
            # unchecked flag still remembers which value was last picked.
            cb = QCheckBox()
            cb.setChecked(bool(self.cfg.get(f.key + "_on", False)))
            c.setEnabled(cb.isChecked())
            cb.toggled.connect(c.setEnabled)
            self.flag_w[f.key + "_on"] = cb
            return row(cb, c, None, spacing=4)
        e = PathEdit(str(saved)) if f.kind == "path" else QLineEdit(str(saved))
        e.setPlaceholderText(f.default or "")
        self.flag_w[f.key] = e
        if f.kind == "path":
            return row(e, button("Browse...", lambda: self._pick_flag_file(e)))
        e.setFixedWidth(170)
        return e

    @staticmethod
    def _ctot_cut_spin(value):
        """The timewalk ctot cut, in ns. Same box on the Advanced and Inspect
        tabs, kept in step by _connect_option_signals."""
        sp = QSpinBox()
        sp.setRange(0, 25000)
        sp.setSingleStep(25)
        sp.setSuffix(" ns")
        sp.setValue(int(float(value)))
        sp.setToolTip(
            "Only clusters whose largest pixel ToT is at least this build the "
            "timewalk curve, so the reference pixel walks little itself. "
            "1000 ns keeps that below ~5 ns on a Timepix3Cam. Lower it if a "
            "file has few bright clusters. Not Luna's --ctot-cut, which only "
            "applies to Luna's own timewalk statistics.")
        return sp

    def _pick_flag_file(self, edit):
        p, _ = QFileDialog.getOpenFileName(
            self, "Select an earlier tpx3dump output", edit.text(),
            "HDF5 (*.hdf5 *.h5);;All files (*)", "", self.DLG)
        if p:
            edit.setText(p)

    def flag_values(self):
        """Every flag control's state, keyed as FLAGS and the settings are."""
        vals = {}
        for key, w in self.flag_w.items():
            if isinstance(w, QCheckBox):
                vals[key] = w.isChecked()
            elif isinstance(w, QComboBox):
                vals[key] = w.currentData()
            else:
                vals[key] = w.text()
        return vals

    def flags_ok(self):
        problems = flag_problems(self.flag_values(), self.det.key)
        if problems:
            QMessageBox.critical(self, APP_NAME,
                                 "Fix these on the Advanced tab first:\n\n"
                                 + "\n".join(problems))
        return not problems

    def _connect_option_signals(self):
        for w in (self.e_template, self.e_extra):
            w.textChanged.connect(self.update_adv_summary)
        for w in self.flag_w.values():
            if isinstance(w, QCheckBox):
                w.toggled.connect(self.update_adv_summary)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self.update_adv_summary)
            else:
                w.textChanged.connect(self.update_adv_summary)
        self.c_tdcref.currentTextChanged.connect(self.update_adv_summary)
        self.sp_tw_cut.valueChanged.connect(self.update_adv_summary)
        for w in (self.cb_skip, self.cb_tdc, self.cb_tw, self.cb_tw_hits,
                  self.rb_beside, self.rb_flat, self.rb_mirror):
            w.toggled.connect(self.update_adv_summary)
        # The ctot cut and the per-hit choice also live on the Inspect tab;
        # setValue / setChecked emit nothing when unchanged, so pairs settle.
        self.sp_tw_cut.valueChanged.connect(self.sp_tw_cut_i.setValue)
        self.sp_tw_cut_i.valueChanged.connect(self.sp_tw_cut.setValue)
        self.cb_tw_hits.toggled.connect(self.cb_tw_hits_i.setChecked)
        self.cb_tw_hits_i.toggled.connect(self.cb_tw_hits.setChecked)
        # One TDC reference, two places to set it. setCurrentText is a no-op
        # when the text already matches, so Qt emits nothing back and the pair
        # settles instead of ping-ponging.
        self.c_tdcref.currentTextChanged.connect(self.c_tdcref_i.setCurrentText)
        self.c_tdcref_i.currentTextChanged.connect(self.c_tdcref.setCurrentText)

    # -- option accessors --------------------------------------------------

    def out_mode(self):
        if self.rb_flat.isChecked():
            return "flat"
        if self.rb_mirror.isChecked():
            return "mirror"
        return "beside"

    def goto_advanced(self):
        self.tabs.setCurrentWidget(self.tab_advanced)

    def _build_menu(self):
        # View: the theme, and Preferences to change any part of it.
        v = self.menuBar().addMenu("&View")
        theme_menu = v.addMenu("&Theme")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions = {}
        group = None
        for key, name in preset_names():
            # A separator where the group changes: the Luna themes, then
            # daplis-rtp's dark ones, then its light ones.
            if group is not None and preset_group(key) != group:
                theme_menu.addSeparator()
            group = preset_group(key)
            a = theme_menu.addAction(name)
            a.setCheckable(True)
            a.setData(key)
            self._theme_group.addAction(a)
            self._theme_actions[key] = a
        self._theme_group.triggered.connect(
            lambda a: self._manager.set_preset(a.data()))

        v.addSeparator()
        a = v.addAction("&Preferences...", self.open_preferences)
        a.setShortcut(QKeySequence("Ctrl+,"))
        a.setStatusTip("Theme, every colour, font and marker sizes")

        m = self.menuBar().addMenu("&Help")
        a = m.addAction("Help contents", lambda: self.show_help("start"))
        a.setShortcut(QKeySequence.StandardKey.HelpContents)
        m.addSeparator()
        for anchor, title in SECTIONS:
            if anchor not in ("start", "about"):
                m.addAction(title, lambda a=anchor: self.show_help(a))
        m.addSeparator()
        m.addAction("About " + APP_NAME, self.show_about)

    def _sync_theme_menu(self):
        """Tick the current theme without re-triggering it."""
        a = self._theme_actions.get(self._manager.preset_key)
        if a is not None and not a.isChecked():
            blocked = self._theme_group.blockSignals(True)
            a.setChecked(True)
            self._theme_group.blockSignals(blocked)

    def open_preferences(self):
        """Preferences, built on first use and kept: it is not modal, so it
        can sit beside the window while colours are picked."""
        if self._preferences is None:
            self._preferences = PreferencesDialog(self)
        self._preferences.open_beside()

    def show_help(self, anchor):
        if self.help is None:
            self.help = HelpWindow(self.pal, self.mono, self,
                                   size=self._manager.ui_font_size)
        self.help.show()
        self.help.raise_()
        self.help.activateWindow()
        self.help.show_section(anchor)

    def show_about(self):
        QMessageBox.about(
            self, "About " + APP_NAME,
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "A batch front end for Luna's <code>tpx3dump</code> (Timepix3) and "
            "<code>tpx4dump</code> (Timepix4), with an HDF5 "
            "inspector and TDC tagging.<br><br>"
            "It runs your own, unmodified Luna installation and contains no "
            "part of it.<br><br>Press F1 for help.")

    def plain_command(self):
        """The command every file gets when nothing is set."""
        d = self.det
        return f"{d.exe} process -i NAME{d.suffix} -o NAME.hdf5"

    def tdc_after_run(self):
        """Whether each finished file gets its TDC columns written. Never for
        Timepix4: tpx4dump records no TDC edges to tag from."""
        return self.cb_tdc.isChecked() and self.det is TPX3

    def timewalk_after_run(self):
        """Whether each finished file gets timewalk-corrected times written."""
        return self.cb_tw.isChecked()

    def advanced_bits(self):
        """Everything that deviates from the plain run, one item per setting."""
        bits = []
        mode = self.out_mode()
        outdir = self.e_outdir.text().strip() or "(no folder chosen)"
        if mode == "flat":
            bits.append("output into one folder: " + outdir)
        elif mode == "mirror":
            bits.append("output into a mirrored tree under " + outdir)
        tmpl = self.e_template.text().strip()
        if tmpl and tmpl != DEFAULT_TEMPLATE:
            bits.append("renaming to " + tmpl)
        if not self.cb_skip.isChecked():
            bits.append("OVERWRITING existing output")
        bits += [" ".join(b) for b in flag_bits(self.flag_values(),
                                                 detector=self.det.key)]
        if self.e_extra.text().strip():
            bits.append("extra arguments: " + self.e_extra.text().strip())
        return bits

    def wrapper_bits(self):
        """What this GUI does to each output after Luna, one item each.
        Kept apart from advanced_bits: none of it changes the Luna command."""
        bits = []
        if self.tdc_after_run():
            bits.append("TDC columns after processing (" +
                        self.c_tdcref.currentText() + ")")
        if self.timewalk_after_run():
            bits.append(f"timewalk correction after processing (ctot cut "
                        f"{self.sp_tw_cut.value()} ns, clusters"
                        + (" and every pixel hit)" if self.cb_tw_hits.isChecked()
                           else ")"))
        return bits

    def update_adv_summary(self, *_a):
        bits = self.advanced_bits()
        self.b_adv.setText(f"Advanced flags ({len(bits)})" if bits
                           else "Advanced flags")
        self.b_adv.setProperty("adv", "on" if bits else "off")
        self.b_adv.setToolTip("\n".join(bits) if bits else
                              "Nothing set: every file runs as plain\n"
                              + self.plain_command())
        self.b_adv.style().unpolish(self.b_adv)
        self.b_adv.style().polish(self.b_adv)
        # Green, and only there while something is on: the GUI's own steps
        # after Luna, so they are never mistaken for Luna flags.
        wbits = self.wrapper_bits()
        self.b_wrap.setVisible(bool(wbits))
        self.b_wrap.setText(f"Wrapper options ({len(wbits)})")
        self.b_wrap.setToolTip("Run by this GUI after Luna, not Luna flags:\n"
                               + "\n".join(wbits))

    def show_wrapper_options(self):
        self.show_adv_flags(wrapper=True)

    def show_adv_flags(self, wrapper=False):
        """List every setting in effect, one per row: the Luna-side ones, or
        with `wrapper` the GUI's own post-processing."""
        bits = self.wrapper_bits() if wrapper else self.advanced_bits()
        dlg = QDialog(self)
        dlg.setWindowTitle("Wrapper options in effect" if wrapper
                           else "Advanced flags in effect")
        dlg.resize(620, 380)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(8)
        if bits:
            head = QLabel(
                f"After Luna finishes each file, this GUI runs {len(bits)} "
                "step(s) on its output. They do not change the Luna command:"
                if wrapper else
                f"{len(bits)} setting(s) differ from the plain run and apply "
                "to every queued file:")
            head.setWordWrap(True)
            head.setProperty("muted", True)
            lay.addWidget(head)
            lst = QListWidget()
            lst.setSpacing(3)
            lst.addItems(bits)
            lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            lay.addWidget(lst, 1)
        else:
            head = QLabel("Nothing set. Every queued file runs as")
            head.setProperty("intro", True)
            cmd = QLabel(self.plain_command())
            cmd.setProperty("code", True)
            lay.addWidget(head)
            lay.addWidget(cmd)
            lay.addStretch(1)

        def edit():
            dlg.accept()
            self.goto_advanced()

        lay.addWidget(row(button("Change on the Advanced tab", edit), None,
                          button("Close", dlg.reject)))
        dlg.exec()

    def reset_advanced(self):
        if QMessageBox.question(
                self, APP_NAME,
                "Reset every advanced setting to its default?\n\n"
                "Output goes next to the input file, named after it, and no extra "
                f"flags are passed to {self.det.exe}.\n\n"
                "The Luna folder and the queue are left alone."
        ) != QMessageBox.StandardButton.Yes:
            return
        self.rb_beside.setChecked(True)
        self.e_outdir.clear()
        self.e_template.setText(DEFAULT_TEMPLATE)
        self.cb_skip.setChecked(True)
        self.e_extra.clear()
        for w in self.flag_w.values():
            if isinstance(w, QCheckBox):
                w.setChecked(False)
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(0)    # the default, or the first TDC reference
            else:
                w.clear()
        self.cb_tdc.setChecked(False)
        self.c_tdcref.setCurrentText(TDC_REFERENCES[0])
        self.cb_tw.setChecked(False)
        self.sp_tw_cut.setValue(int(TW_DEFAULT_CTOT_CUT_NS))
        self.cb_tw_hits.setChecked(False)
        self.recompute_outputs()
        self.log("Advanced settings reset to defaults.")

    # -- logging ----------------------------------------------------------

    def log(self, text=""):
        self.log_view.appendPlainText(text)
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def save_log(self):
        start = self.common_root() or Path.home()
        name = time.strftime(f"{self.det.exe}_log_%Y-%m-%d_%H-%M.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the log", str(Path(start) / name),
            "Text files (*.txt);;All files (*)", options=self.DLG)
        if not path:
            return
        try:
            Path(path).write_text(self.log_view.toPlainText() + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save the log:\n{exc}")
            return
        self.log(f"Log saved to {path}")

    # -- Luna install -----------------------------------------------------

    # On Windows the file dialogs are Explorer's own, so everything learnt
    # there works unchanged: Alt+D for the address bar, pasting a path into
    # it, Ctrl+A, Quick Access, recent folders. The price is that they follow
    # Windows' light/dark setting rather than this app's. Elsewhere Qt's own
    # dialog keeps the app theme.
    DLG = (QFileDialog.Option(0) if IS_WINDOWS
           else QFileDialog.Option.DontUseNativeDialog)

    def pick_luna(self):
        d = QFileDialog.getExistingDirectory(
            self, f"Select the {self.det.name} Luna folder (containing bin/{self.det.exe})",
            self.e_luna.text() or str(Path.home()), self.DLG)
        if d:
            self.e_luna.setText(d)
            self.refresh_backend()

    def refresh_backend(self):
        try:
            self.backend = detect_backend(self.e_luna.text(), self.det.exe)
        except Exception as exc:
            self.backend = Backend(detail=str(exc))
        ok = self.backend.usable
        self.lbl_backend.setText(("OK  " if ok else "!   ") + self.backend.detail)
        self.lbl_backend.setProperty("role", "ok" if ok else "error")
        # The main tab gets one short line; the detail stays on Advanced.
        if ok:
            self.lbl_status.setText(
                f"Ready - {self.det.exe} runs " +
                ("through WSL." if self.backend.kind == "wsl" else "natively."))
            self.lbl_status.setProperty("role", "ok")
            self.b_setup.setVisible(False)
        else:
            self.lbl_status.setText(self.backend.detail)
            self.lbl_status.setProperty("role", "error")
            self.b_setup.setVisible(True)
        for w in (self.lbl_backend, self.lbl_status):
            w.style().unpolish(w)
            w.style().polish(w)

    def check_install(self):
        self.refresh_backend()
        self.log("=" * 78)
        self.log("Backend: " + self.backend.kind + " -- " + self.backend.detail)
        if not self.backend.usable:
            self.log(f"Cannot execute {self.det.exe} here. 'Preview commands' and "
                     "'Export .sh' still work.")
            return
        for args in (["--version"], ["process", "--help"]):
            self.log("")
            self.log("$ " + self.backend.display(args))
            try:
                r = subprocess.run(self.backend.argv(args), capture_output=True,
                                   text=True, errors="replace", timeout=120,
                                   creationflags=_NO_WINDOW)
                self.log((r.stdout or "") + (r.stderr or ""))
            except Exception as exc:
                self.log("failed: " + str(exc))

    # -- queue management -------------------------------------------------

    @staticmethod
    def _scan_folder(path, recursive=True, suffix=".tpx3"):
        """Every raw file (.tpx3, .tpx4) in one folder, sorted,
        case-insensitive suffix."""
        p = Path(path)
        found = set()
        for pat in ("*" + suffix, "*" + suffix.upper()):
            try:
                found.update(p.rglob(pat) if recursive else p.glob(pat))
            except Exception:
                pass
        return sorted((f for f in found if f.is_file()), key=lambda f: str(f).lower())

    def add_folders(self, paths, recursive=True):
        """Append folders to the batch and queue whatever they contain."""
        known = {f["path"] for f in self.folders}
        added = 0
        for raw in paths:
            try:
                p = str(Path(str(raw).strip().strip('"').strip("'")))
            except Exception:
                continue
            if not p or p in known:
                continue
            if not Path(p).is_dir():
                self.log("Not a folder, ignored: " + p)
                continue
            known.add(p)
            self.folders.append({"path": p, "recursive": bool(recursive), "count": None})
            added += 1
        if added:
            self.scan_folders()
        else:
            self.folder_model.reset()
        return added

    def scan_folders(self):
        """Full rescan: new files, vanished files, and re-read metadata.

        Re-reading matters. _add() skips paths already queued, so a job's
        context is captured once, the first time the file is seen. Queue a
        measurement that is still running and there is no
        measurement_metadata.json yet, so every placeholder is empty and the
        name falls back to the bare ASI stem -- and it would stay that way for
        good, because Rescan used to add new files and nothing else.
        """
        if not self.folders:
            self.folder_model.reset()
            return
        new = 0
        for entry in self.folders:
            if not Path(entry["path"]).is_dir():
                entry["count"] = -1          # drive unplugged, folder renamed...
                continue
            files = self._scan_folder(entry["path"], entry["recursive"],
                                      self.det.suffix)
            entry["count"] = len(files)
            new += self._add(files, origin=entry["path"], quiet=True)
        gone = self._prune_missing()
        renamed = self._refresh_metadata()
        self.folder_model.reset()
        self.recompute_outputs()
        missing = sum(1 for f in self.folders if f["count"] == -1)
        empty = sum(1 for f in self.folders if f["count"] == 0)
        msg = (f"Scanned {len(self.folders)} folder(s): {len(self.jobs)} file(s) queued"
               + (f", {new} new" if new else ""))
        if renamed:
            msg += f", {renamed} metadata refresh(es)"
        if gone:
            msg += f", {gone} vanished file(s) dropped"
        if empty:
            msg += f", {empty} folder(s) with no {self.det.suffix}"
        if missing:
            msg += f", {missing} folder(s) NOT FOUND"
        self.log(msg)

    def _refresh_metadata(self):
        """Re-read measurement metadata for every job that is not running.

        A running job is skipped because its output path is already on the
        tpx3dump command line -- renaming it underneath would leave the queue
        describing a file the process is not writing.
        """
        changed = 0
        for job in self.jobs:
            if job.status == "running":
                continue
            try:
                ctx = measurement_context(job.src)
            except Exception:
                continue                 # unreadable metadata: keep what we had
            if ctx != job.ctx:
                job.ctx = ctx
                changed += 1
        return changed

    def _prune_missing(self):
        """Drop rows whose input file has disappeared since it was queued.

        Only ones still waiting: a done or failed row is a record of something
        that already happened and is not the rescan's to erase.
        """
        keep = [j for j in self.jobs
                if j.status not in ("queued", "CLASH") or j.src.is_file()]
        gone = len(self.jobs) - len(keep)
        if gone:
            self.jobs[:] = keep
        return gone

    def add_folders_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add folders to the batch")
        dlg.resize(820, 500)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)

        sfx = self.det.suffix
        head = QLabel(f"Every folder listed here is searched for {sfx} files, and "
                      "each one found is queued.\nWith the default output settings "
                      f"the .hdf5 is written next to its {sfx}, in that same folder.")
        head.setProperty("muted", True)
        lay.addWidget(head)

        lay.addWidget(QLabel("Folders:"))
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lay.addWidget(lst, 2)

        def browse():
            d = QFileDialog.getExistingDirectory(
                dlg, "Select a folder (repeat for more)",
                self.cfg.get("last_input", str(Path.home())), self.DLG)
            if d:
                self.cfg["last_input"] = d
                if not lst.findItems(d, Qt.MatchFlag.MatchExactly):
                    lst.addItem(d)

        def drop_selected():
            for item in lst.selectedItems():
                lst.takeItem(lst.row(item))

        hint = QLabel("(Browse can be clicked repeatedly)")
        hint.setProperty("faint", True)
        lay.addWidget(row(button("Browse...", browse),
                          button("Remove selected", drop_selected), hint, None))

        lay.addWidget(QLabel("...or paste paths, one per line, or drag folders "
                             "in from Explorer:"))
        paste = PathsEdit()
        paste.setFixedHeight(120)
        lay.addWidget(paste, 1)

        cb_rec = QCheckBox("Search subfolders (needed for the ASI "
                           "<measurement>/raw/ layout)")
        cb_rec.setChecked(True)
        lay.addWidget(cb_rec)

        bb = QDialogButtonBox()
        b_add = bb.addButton("Add to batch", QDialogButtonBox.ButtonRole.AcceptRole)
        b_add.setProperty("accent", True)
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        lst.itemDoubleClicked.connect(lambda _i: drop_selected())

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paths = [lst.item(i).text() for i in range(lst.count())]
        paths += [ln for ln in paste.toPlainText().splitlines() if ln.strip()]
        if paths and not self.add_folders(paths, cb_rec.isChecked()):
            QMessageBox.information(self, APP_NAME,
                                    "Nothing added - those folders were already in "
                                    "the batch, or are not folders.")

    def _add(self, paths, origin="", quiet=False):
        known = {j.src.resolve() for j in self.jobs}
        added = 0
        for p in paths:
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            if rp in known or not p.is_file():
                continue
            known.add(rp)
            self.jobs.append(Job(src=p, ctx=measurement_context(p), origin=origin))
            added += 1
        if not quiet:
            self.recompute_outputs()
            self.log(f"Added {added} file(s); queue now has {len(self.jobs)}.")
        return added

    def clear_queue(self):
        self.jobs = []
        self.folders = []
        self.folder_model.reset()
        self.recompute_outputs()

    def common_root(self):
        """Deepest folder shared by every queued input (for mirror mode)."""
        if not self.jobs:
            return None
        try:
            return Path(os.path.commonpath([str(j.src.parent) for j in self.jobs]))
        except Exception:
            return self.jobs[0].src.parent

    def recompute_outputs(self):
        mode = self.out_mode()
        self.e_outdir.setEnabled(mode != "beside")
        self.b_outdir.setEnabled(mode != "beside")
        template = self.e_template.text().strip() or DEFAULT_TEMPLATE
        outdir = Path(self.e_outdir.text()) if self.e_outdir.text().strip() else None
        root = self.common_root() if mode == "mirror" else None

        for job in self.jobs:
            name = render_name(template, job.ctx) + ".hdf5"
            if mode == "beside" or outdir is None:
                job.dst = job.src.with_name(name)
            elif mode == "flat":
                job.dst = outdir / name
            else:
                try:
                    rel = job.src.parent.relative_to(root)
                except Exception:
                    rel = Path()
                # ASI stores the binary in <measurement>/raw/; recreating that
                # level under the output root adds nothing, so drop it.
                if rel.name.lower() == "raw":
                    rel = rel.parent
                job.dst = outdir / rel / name

        # Flag collisions - two inputs mapping to one output would silently
        # clobber each other, which is the whole thing a rename tool must avoid.
        seen = {}
        for job in self.jobs:
            seen.setdefault(str(job.dst).lower(), []).append(job)
        for group in seen.values():
            if len(group) > 1:
                for job in group:
                    if job.status == "queued":
                        job.status = "CLASH"
                        job.note = "several inputs map to this output name"
            elif group[0].status == "CLASH":
                group[0].status, group[0].note = "queued", ""
        # An Overwrite tick belongs to one output path. Once the template or
        # the output folder moves a job somewhere nothing exists yet, the tick
        # has nothing to refer to, so drop it rather than let it linger.
        for job in self.jobs:
            if job.overwrite and not self.job_clobbers(job):
                job.overwrite = False
        self.job_model.reset()
        self.sync_overwrite_header()
        self.lbl_prog.setText("")
        self.pb.setValue(0)
        self.pb.setTextVisible(False)
        self.pb.setVisible(False)

    def job_clobbers(self, job) -> bool:
        """True when running this job would land on an .hdf5 that is there."""
        if not job.dst or job.status == "CLASH":
            return False
        try:
            return job.dst.exists()
        except Exception:
            return False

    def overwritable_jobs(self):
        return [j for j in self.jobs if self.job_clobbers(j)]

    def sync_overwrite_header(self):
        """Master checkbox reflects the rows: all / some / none ticked."""
        rows = self.overwritable_jobs()
        ticked = sum(1 for j in rows if j.overwrite)
        if not rows or ticked == 0:
            state = Qt.CheckState.Unchecked
        elif ticked == len(rows):
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        if getattr(self, "jhead", None):
            self.jhead.set_state(state)
        self.sync_rerun_button()

    def failed_jobs(self):
        return [i for i, j in enumerate(self.jobs) if j.status == "failed"]

    def sync_rerun_button(self):
        """Rerun failed: live (and yellow) while the queue holds failures and
        nothing is running; it says how many."""
        b = getattr(self, "b_rerun", None)
        if b is None:
            return
        n = len(self.failed_jobs())
        running = self.b_stop.isEnabled()
        b.setEnabled(bool(n) and not running)
        b.setText(f"Rerun failed ({n})" if n else "Rerun failed")
        b.setToolTip("Explain why these files failed, then process just them "
                     "again" if n else "No file has failed")
        state = "on" if n and not running else "off"
        if b.property("adv") != state:
            b.setProperty("adv", state)
            b.style().unpolish(b)
            b.style().polish(b)

    def rerun_failed(self):
        """Say why each file failed and whether that still holds, then run the
        failed files -- and only them -- again."""
        idx = self.failed_jobs()
        if not idx:
            return
        # The template or output folder may have changed since: judge the
        # names as they would be now.
        self.recompute_outputs()
        groups = {}
        for i in idx:
            job = self.jobs[i]
            kind = job.fail.kind if job.fail else "unknown"
            groups.setdefault(kind, []).append(job)

        NL = chr(10)
        parts, again = [], 0
        for kind, jobs in groups.items():
            f = jobs[0].fail
            reason = f.reason if f else (jobs[0].note or "reason not recorded")
            block = [f"{len(jobs)} x {reason}"]
            if f:
                block.append(f"What to change: {f.advice}")
            still = sum(1 for j in jobs if still_fails(kind, j.dst))
            again += still
            if still:
                block.append(f"NOT FIXED YET: {still} of these would fail again "
                             "with the current settings.")
            elif kind == "name_too_long":
                block.append("Fixed: every name now fits.")
            parts.append(NL.join(block))

        partial = [self.jobs[i] for i in idx if self.job_clobbers(self.jobs[i])]
        text = (f"{len(idx)} file(s) failed." + NL + NL +
                (NL + NL).join(parts) + NL + NL +
                (f"{len(partial)} of them left a partial .hdf5 behind; Overwrite "
                 "will be ticked on those so they are redone." + NL + NL
                 if partial else "") +
                "Only the failed files are run; the rest of the queue is left "
                "alone.")
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Warning if again else QMessageBox.Icon.Question)
        box.setText(text)
        go = box.addButton(f"Rerun anyway ({len(idx)})" if again
                           else f"Rerun {len(idx)} file(s)",
                           QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel if again else go)
        box.exec()
        if box.clickedButton() is not go:
            return
        for job in partial:
            job.overwrite = True
        self.job_model.overwrite_column_changed()
        self.sync_overwrite_header()
        self.log(f"Rerunning {len(idx)} failed file(s)"
                 + (f", Overwrite ticked on {len(partial)}" if partial else "") + ".")
        self.run_queue(only=idx)

    def toggle_all_overwrite(self):
        """Header checkbox: tick every row that has an output to overwrite."""
        rows = self.overwritable_jobs()
        if not rows:
            self.log("Nothing in the queue would overwrite an existing .hdf5.")
            return
        want = not all(j.overwrite for j in rows)
        for job in rows:
            job.overwrite = want
        self.job_model.overwrite_column_changed()
        self.sync_overwrite_header()
        self.log(("Overwrite ticked on " if want else "Overwrite cleared on ")
                 + f"{len(rows)} file(s) whose output already exists.")

    def _job_double_clicked(self, index):
        job = self.jobs[index.row()]
        if job.dst and job.dst.exists():
            self.e_h5.setText(str(job.dst))
            self.tabs.setCurrentWidget(self.tab_inspect)
            self.open_h5()

    def pick_outdir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select the output folder",
            self.e_outdir.text() or str(Path.home()), self.DLG)
        if d:
            self.e_outdir.setText(d)
            self.recompute_outputs()

    def template_presets(self):
        presets = PRESET_TEMPLATES
        dlg = QDialog(self)
        dlg.setWindowTitle("Name templates")
        dlg.resize(660, 260)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Double-click a template to use it:"))
        lst = QListWidget()
        for tmpl, example in presets:
            lst.addItem(f"{tmpl:34s} ->  {example}")
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox()
        b_use = bb.addButton("Use", QDialogButtonBox.ButtonRole.AcceptRole)
        b_use.setProperty("accent", True)
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        if dlg.exec() == QDialog.DialogCode.Accepted and lst.currentRow() >= 0:
            self.e_template.setText(presets[lst.currentRow()][0])
            self.recompute_outputs()

    # -- command construction --------------------------------------------

    def dump_args(self, job, backend=None, translate=None):
        """`translate` maps a path-valued flag; the backend's own by default."""
        b = backend or self.backend
        args = ["process", "-i", b.translate(job.src), "-o", b.translate(job.dst)]
        args += flag_args(self.flag_values(), translate or b.translate,
                          self.det.key)
        extra = self.e_extra.text().strip()
        if extra:
            args += shlex.split(extra, posix=True)
        return args

    def runnable_jobs(self, indices=None):
        out = []
        for i in (range(len(self.jobs)) if indices is None else indices):
            job = self.jobs[i]
            if job.status == "CLASH":
                continue
            if (self.cb_skip.isChecked() and not job.overwrite
                    and job.dst and job.dst.exists()):
                job.status, job.note = "skipped", "output exists"
                self.job_model.row_changed(i)
                continue
            out.append(i)
        return out

    def preview(self):
        if not self.jobs:
            QMessageBox.information(self, APP_NAME, "The queue is empty.")
            return
        if not self.flags_ok():
            return
        self.log("=" * 78)
        self.log(f"{len(self.jobs)} job(s), backend = {self.backend.kind}")
        b = self.backend if self.backend.usable else Backend("native", self.det.exe)
        for job in self.jobs:
            if job.status == "CLASH":
                self.log("# SKIPPED (name clash): " + job.src.name)
                continue
            self.log(b.display(self.dump_args(job, b)))
        self.log()

    def export_sh(self):
        if not self.jobs:
            QMessageBox.information(self, APP_NAME, "The queue is empty.")
            return
        if not self.flags_ok():
            return
        path, _ =QFileDialog.getSaveFileName(
            self, "Save a shell script to run on Linux", f"run_{self.det.exe}.sh",
            "Shell script (*.sh)", "", self.DLG)
        if not path:
            return
        exe = self.det.exe
        var = exe.upper()                  # TPX3DUMP / TPX4DUMP
        b = Backend("native", exe)

        def posix(p):
            return win_to_wsl(str(p)) if IS_WINDOWS else str(p)

        jobs = [j for j in self.jobs if j.status != "CLASH"]
        in_root = posix(self.common_root() or "/")
        try:
            out_root = posix(os.path.commonpath([str(j.dst.parent) for j in jobs]))
        except Exception:
            out_root = in_root

        def under(p, root_posix, var):
            """Rewrite an absolute path as "$VAR/relative" where possible."""
            pp = posix(p)
            if root_posix != "/" and pp.startswith(root_posix + "/"):
                return "\"$" + var + "\"/" + shlex.quote(pp[len(root_posix) + 1:])
            return shlex.quote(pp)

        lines = ["#!/usr/bin/env bash",
                 "# Generated by " + APP_NAME + " -- run this on the Linux machine.",
                 "#",
                 f"# 1. Put the Luna bin/ directory on PATH, or set {var} below",
                 f"#    to the absolute path of the {exe} executable.",
                 "# 2. Edit IN_ROOT / OUT_ROOT to match where the data lives there.",
                 "set -euo pipefail", "",
                 f"{var}=${{{var}:-{exe}}}",
                 "IN_ROOT=" + shlex.quote(in_root),
                 "OUT_ROOT=" + shlex.quote(out_root), ""]
        for job in self.jobs:
            if job.status == "CLASH":
                lines.append("# skipped (name clash): " + job.src.name)
                continue
            src = under(job.src, in_root, "IN_ROOT")
            dst = under(job.dst, out_root, "OUT_ROOT")
            tail = [shlex.quote(a) for a in self.dump_args(job, b, posix)[5:]]
            lines.append('mkdir -p "$(dirname ' + dst + ')"')
            lines.append(" ".join([f'"${var}"', "process", "-i", src, "-o", dst] + tail))
        try:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, "Could not write the script:\n" + str(exc))
            return
        self.log("Wrote " + path)

    # -- running (QProcess, one job at a time) ----------------------------

    def run_queue(self, only=None):
        """Run the queue, or with `only` (row indices) just those rows --
        Rerun failed uses that, leaving every other row's status as it is."""
        if only is not None and not isinstance(only, (list, tuple)):
            only = None                 # clicked(bool) from the Run button
        self.refresh_backend()
        if not self.backend.usable:
            QMessageBox.critical(
                self, APP_NAME,
                f"{self.det.exe} cannot be executed here.\n\n" + self.backend.detail +
                "\n\nSet the Luna folder on the Advanced tab, or use its "
                "'Export .sh' button to run this queue on a Linux machine.")
            return
        if not self.jobs:
            QMessageBox.information(self, APP_NAME, "The queue is empty.")
            return
        if self.out_mode() != "beside" and not self.e_outdir.text().strip():
            QMessageBox.critical(self, APP_NAME,
                                 "Choose an output folder on the Advanced tab, or "
                                 "switch back to 'Next to the input file'.")
            return
        if not self.flags_ok():
            return
        clashes =[j for j in self.jobs if j.status == "CLASH"]
        if clashes:
            QMessageBox.warning(
                self, APP_NAME,
                f"{len(clashes)} input(s) map to a duplicated output name and will "
                "be skipped.\nAdd {measurement} or {datetime} to the template to "
                "make the names unique.")
        pool = range(len(self.jobs)) if only is None else only
        for i in pool:
            job = self.jobs[i]
            if job.status in ("done", "failed", "skipped"):
                job.status, job.note, job.fail = "queued", "", None
                self.job_model.row_changed(i)
        todo = self.runnable_jobs(pool)
        if not todo:
            self.log("Nothing to do - every output already exists. "
                     "Tick 'Overwrite' in the queue to redo one anyway.")
            return
        if not self.check_wsl_drives(todo):
            for i, job in enumerate(self.jobs):
                if job.status == "queued":
                    self.job_model.row_changed(i)
            return

        self.save_settings()
        self.b_run.setEnabled(False)
        self.b_stop.setEnabled(True)
        self.stopping = False
        self.todo = list(todo)
        self.total = len(self.todo)
        self.done = self.ok = self.failed = 0
        self.pb.setMaximum(self.total)
        self.pb.setValue(0)
        self.pb.setTextVisible(True)
        self.pb.setVisible(True)
        self.lbl_prog.setText(f"0 / {self.total}")
        self.sync_rerun_button()
        self.log("=" * 78)
        self.log(f"Running {self.total} job(s) via {self.backend.kind}")
        self.t_all = time.time()
        self._start_next()

    def check_wsl_drives(self, todo) -> bool:
        """Make sure WSL can actually see the data this run touches.

        WSL auto-mounts fixed disks only, so a USB stick or another removable
        volume is invisible to tpx3dump: it logs a "Skipping file" warning and
        then panics with "index out of bounds: the len is 0". Mounting takes
        one root command and no password, so offer that instead of letting the
        run crash. Returns False when the run should not start.
        """
        if self.backend.kind != "wsl":
            return True

        NL = chr(10)
        letters, inputs = set(), []
        for i in todo:
            job = self.jobs[i]
            inputs.append(self.backend.translate(job.src))
            for path in (job.src, job.dst.parent if job.dst else None):
                if path is not None:
                    letter = drive_letter(path)
                    if letter:
                        letters.add(letter)

        missing = wsl_unmounted_drives(letters)
        if missing:
            names = ", ".join(d.upper() + ":" for d in missing)
            plural = "drives are" if len(missing) > 1 else "drive is"
            if QMessageBox.question(
                    self, APP_NAME,
                    names + " cannot be reached from WSL." + NL + NL +
                    "WSL mounts fixed disks automatically but leaves removable "
                    "ones (USB sticks, card readers, some external drives) "
                    "alone, so the " + plural + " simply not there as far as "
                    + self.det.exe + " is concerned -- it would skip every file and then "
                    "crash with 'index out of bounds'." + NL + NL +
                    "Mount it now? This needs no password, and lasts until WSL "
                    "next shuts down.") != QMessageBox.StandardButton.Yes:
                self.log("Run cancelled -- " + names + " is not mounted in WSL.")
                return False
            for letter in missing:
                ok, err = wsl_mount_drive(letter)
                self.log(("Mounted " if ok else "Could not mount ") +
                         letter.upper() + ": at /mnt/" + letter +
                         ("" if ok else " -- " + err))
            missing = wsl_unmounted_drives(letters)

        if not missing:
            missing_files = wsl_missing_paths(inputs)
            if not missing_files:
                return True
            shown = missing_files[:6]
            QMessageBox.critical(
                self, APP_NAME,
                str(len(missing_files)) + " input file(s) exist on Windows but "
                "not inside WSL:" + NL + NL +
                NL.join("    " + f for f in shown) +
                (NL + "    ..." if len(missing_files) > len(shown) else "") +
                NL + NL +
                + self.det.exe + " would skip them and then crash. Check the drive is "
                "still connected, or copy the data to an internal disk.")
            self.log("Run cancelled -- WSL cannot see " +
                     str(len(missing_files)) + " input file(s).")
            return False

        QMessageBox.critical(
            self, APP_NAME,
            "Still cannot reach " + ", ".join(d.upper() + ":" for d in missing) +
            " from WSL." + NL + NL +
            "Mount it by hand in a WSL terminal:" + NL +
            NL.join("    sudo mkdir -p /mnt/{0} && "
                    "sudo mount -t drvfs {1}: /mnt/{0}".format(d, d.upper())
                    for d in missing) + NL + NL +
            "Or copy the data onto an internal disk (C: or D:) and rescan.")
        return False

    def _start_next(self):
        if self.stopping or not self.todo:
            self._finish()
            return
        idx = self.todo.pop(0)
        self.cur = idx
        self._settled = False
        job = self.jobs[idx]
        job.status, job.note = "running", ""
        self.job_model.row_changed(idx)
        self.jtable.scrollTo(self.job_model.index(idx, 0))
        try:
            job.dst.parent.mkdir(parents=True, exist_ok=True)
            argv = self.backend.argv(self.dump_args(job))
        except Exception as exc:
            self._job_done(idx, -1, str(exc))
            return

        self.log("")
        self.log(f"[{self.done + 1}/{self.total}] {job.src.name}  ->  {job.dst.name}")
        self.log("$ " + " ".join(shlex.quote(a) for a in argv))
        self.t_job = time.time()

        self._reset_output()
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.readyReadStandardOutput.connect(self._read_proc)
        p.finished.connect(lambda code, _st, i=idx: self._job_done(i, code, ""))
        p.errorOccurred.connect(lambda err, i=idx: self._proc_error(i, err))
        self.proc = p
        p.start(argv[0], argv[1:])

    # Luna's output can arrive far faster than a text widget takes it line by
    # line: tpx4dump prints one long error for every packet it drops, which on
    # a real file is a flood. Appending and scrolling per line then starves
    # the event loop, the window stops responding, the pipe fills and the
    # converter blocks on it -- the whole run looks frozen. So lines are
    # buffered and written to the log in one go every LOG_FLUSH_MS, and once
    # REPEATS_SHOWN lines of one kind have been shown for a file, the rest are
    # counted instead and summed up when the file is done. Even the counting
    # is done a slice of at most DIGEST_MS at a time, so a burst of a million
    # lines never holds the window up for more than a moment.
    LOG_FLUSH_MS = 100
    REPEATS_SHOWN = 20
    DIGEST_MS = 15

    def _reset_output(self):
        self._out_tail = ""            # an incomplete last line, to be continued
        self._out_queue = deque()      # complete lines not looked at yet
        self._out_lines = []           # waiting for the next flush
        self._out_seen = {}            # line signature -> how many seen
        self._out_hidden = {}          # signature -> first line not shown
        # For naming the cause if the run fails: the last lines (a panic and
        # its message come at the very end) and any early error-looking line.
        self._out_recent = deque(maxlen=40)
        self._out_alarm = []

    def _read_proc(self):
        if not self.proc:
            return
        text = self._out_tail + bytes(self.proc.readAllStandardOutput()).decode(
            "utf-8", "replace")
        lines = text.split("\n")
        self._out_tail = lines.pop()
        if lines:
            idle = not self._out_queue
            self._out_queue.extend(lines)
            if idle:
                QTimer.singleShot(0, self._digest)

    def _digest(self, budget_ms=DIGEST_MS):
        """Look at queued lines for up to budget_ms, then let the window
        breathe; carries on from the event loop while lines remain."""
        q = self._out_queue
        stop = None if budget_ms is None else time.perf_counter() + budget_ms / 1000.0
        while q:
            for _ in range(min(500, len(q))):
                self._take_line(q.popleft())
            if stop is not None and time.perf_counter() > stop:
                break
        if q:
            QTimer.singleShot(0, self._digest)
        if not self._flush_timer.isActive():
            self._flush_timer.start(self.LOG_FLUSH_MS)

    def _take_line(self, line):
        line = line.rstrip()
        if not line:
            return
        # Lines of one kind differ only in their numbers: timestamps, packet
        # fields, line numbers. The head of the line with digits blanked out
        # tells them apart cheaply.
        sig = line[:120].translate(_DIGITS)
        n = self._out_seen.get(sig, 0) + 1
        self._out_seen[sig] = n
        self._out_recent.append(line)
        if (n == 1 and len(self._out_alarm) < 12
                and _ALARM.search(line) and "tpx4_unpacker" not in line):
            self._out_alarm.append(line)
        if n <= self.REPEATS_SHOWN:
            self._out_lines.append("  " + line)
        elif n == self.REPEATS_SHOWN + 1:
            self._out_hidden[sig] = line
            self._out_lines.append(f"  ... more lines like this are being counted, "
                                   f"not shown (after the first {self.REPEATS_SHOWN})")

    def _flush_output(self):
        if self._out_lines:
            self.log("\n".join(self._out_lines))
            self._out_lines = []

    def _end_output(self):
        """The job is over: last partial line, the rest of the buffer, and a
        count of every kind of line that was hidden. Returns the lines kept
        for diagnosing a failure."""
        self._flush_timer.stop()
        if self._out_tail:
            self._out_queue.append(self._out_tail)
            self._out_tail = ""
        self._digest(budget_ms=None)          # whatever is left, all of it
        for sig, example in self._out_hidden.items():
            hidden = self._out_seen[sig] - self.REPEATS_SHOWN
            # Drop Luna's "[source:line] [thread: ...]" prefix, so the summary
            # shows the message itself -- the error kind -- not the location.
            msg = _LOG_PREFIX.sub("", example)
            self._out_lines.append(f"  ({hidden:,} more lines like this were not "
                                   f"shown: {msg[:160]}...)")
        self._flush_output()
        kept = self._out_alarm + list(self._out_recent)
        self._reset_output()
        return kept

    def _proc_error(self, idx, err):
        # Only FailedToStart needs handling here; every other error is followed
        # by finished(), which settles the job normally.
        if err == QProcess.ProcessError.FailedToStart:
            msg = "executable not found or not runnable"
            self.log("  " + msg)
            self._job_done(idx, -1, msg)

    def _job_done(self, idx, code, err):
        if getattr(self, "_settled", True):
            return                      # finished() and errorOccurred() can both fire
        self._settled = True
        if self.proc is not None:
            self._read_proc()            # whatever is still in the pipe
            self.proc.deleteLater()
            self.proc = None
        output = self._end_output()
        job = self.jobs[idx]
        dt = time.time() - getattr(self, "t_job", time.time())
        job.fail = None

        if self.stopping and code != 0:
            job.status, job.note = "queued", "cancelled"
        elif not err and code == 0 and job.dst.exists():
            size = human_size(job.dst.stat().st_size)
            job.status, job.note = "done", f"{size} in {dt:.1f}s"
            self.log(f"  OK  {size} in {dt:.1f} s")
            self.ok += 1
            job.note += self._tag_output(job)
        else:
            job.fail = diagnose(output, code, job.dst, job.src, job.ctx, err)
            job.status, job.note = "failed", job.fail.reason
            self.log(f"  FAILED  {job.fail.reason}"
                     + ("" if err else f"  (exit code {code})"))
            self.log(f"  What to change: {job.fail.advice}")
            self.failed += 1

        self.job_model.row_changed(idx)
        self.sync_overwrite_header()
        self.done += 1
        self.pb.setValue(self.done)
        self.lbl_prog.setText(f"{self.done} / {self.total}")
        QTimer.singleShot(0, self._start_next)

    def _tag_output(self, job):
        """Post-process one finished output: the wrapper options.

        Runs inline between jobs on purpose -- it is the same sequential batch
        the user started, and doing it here means the file is complete before
        the queue moves on. Never fails the job: the .hdf5 Luna wrote is good
        either way, so a problem is reported and the run continues.
        """
        note = ""
        if self.tdc_after_run():
            ref = self.c_tdcref.currentText()
            try:
                res = add_tdc_columns(job.dst, ref, log=self.log)
                tagged = sum(v["tagged"] for v in res.values())
                note += f", TDC {ref} ({tagged:,} rows)"
            except Exception as exc:
                self.log("  TDC columns skipped: " + str(exc))
                note += ", no TDC"
        if self.timewalk_after_run():
            try:
                self._busy(True)
                res = add_timewalk_columns(
                    job.dst, ctot_cut_ns=self.sp_tw_cut.value(),
                    pixel_hits=self.cb_tw_hits.isChecked(), detector=self.det,
                    log=self.log)
                note += f", timewalk ({res[TW_CURVE]['delay_ns_lowest_tot']:.0f} ns max)"
            except Exception as exc:
                self.log("  Timewalk correction skipped: " + str(exc))
                note += ", no timewalk"
            finally:
                self._busy(False)
        return note

    def _finish(self):
        self.b_run.setEnabled(True)
        self.b_stop.setEnabled(False)
        # Every job just written is now something a rerun would overwrite.
        self.job_model.overwrite_column_changed()
        self.sync_overwrite_header()
        if self.stopping:
            self.log("Stopped by user.")
        self.log(f"Finished: {self.ok} ok, {self.failed} failed, "
                 f"{self.total - self.done} not run, "
                 f"{time.time() - self.t_all:.1f} s total.")
        if self.failed:
            # One line per cause, so a long batch's failures can be read off
            # here instead of being hunted down file by file.
            causes = {}
            for job in self.jobs:
                if job.status == "failed" and job.fail:
                    causes.setdefault(job.fail.kind, []).append(job)
            for jobs in causes.values():
                f = jobs[0].fail
                alike = len({j.fail.reason for j in jobs}) > 1
                self.log(f"  {len(jobs)} x {f.reason}" + (" (or similar)" if alike else ""))
                self.log(f"      What to change: {f.advice}")
            self.log("  Fix that, then press 'Rerun failed' above the Overwrite "
                     "column to process just these files again.")
        self.log()

    def stop_run(self):
        self.stopping = True
        self.todo = []
        self.log(f"Stop requested - terminating the current {self.det.exe}...")
        if self.proc is not None:
            self.proc.kill()

    # -- settings ---------------------------------------------------------

    def save_settings(self):
        self._store_detector_state()            # Luna folder, batch folders
        self.cfg.update({
            "detector": self.det.key, "out_mode": self.out_mode(),
            "out_dir": self.e_outdir.text(), "template": self.e_template.text(),
            "skip_existing": self.cb_skip.isChecked(),
            **self.flag_values(),
            "tdc_columns": self.cb_tdc.isChecked(),
            "tdc_reference": self.c_tdcref.currentText(),
            "timewalk_columns": self.cb_tw.isChecked(),
            "timewalk_ctot_cut": self.sp_tw_cut.value(),
            "timewalk_hits": self.cb_tw_hits.isChecked(),
            "dcr_time_source": self.c_dcr_time.currentData(),
            "dcr_noisy_k": self.sp_dcr_k.value(),
            "extra": self.e_extra.text(),
        })
        # Theme, style, colour changes, font and marker sizes.
        self._manager.store(self.cfg)
        save_config(self.cfg)

    def closeEvent(self, event):
        if self.proc is not None:
            if QMessageBox.question(
                    self, APP_NAME,
                    "A run is still in progress. Stop it and quit?"
            ) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_run()
        self.save_settings()
        if self._preferences is not None:
            self._preferences.close()
        event.accept()

    # -- inspect tab ------------------------------------------------------

    def _build_inspect(self, tab):
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)

        # Paste or drop a path and press Enter: it opens like Open does.
        self.e_h5 = PathEdit()
        self.e_h5.returnPressed.connect(self.open_h5)
        self.e_h5.path_dropped.connect(lambda _p: self.open_h5())
        lay.addWidget(row("HDF5 file:", self.e_h5,
                          button("Browse...", self.pick_h5),
                          button("Open", self.open_h5),
                          button("Use selected output", self.inspect_selected_output)))

        cap = QLabel("Datasets")
        cap.setProperty("muted", True)
        cap_hint = QLabel("double-click one to scroll through its rows")
        cap_hint.setProperty("faint", True)
        lay.addWidget(row(cap, cap_hint, None,
                          button("View rows...", self.view_dataset),
                          spacing=10))
        self.itable = QTableWidget(0, 5)
        self.itable.setHorizontalHeaderLabels(
            ["Name", "Shape", "Dtype", "Chunks", "Compression"])
        self.itable.verticalHeader().setVisible(False)
        self.itable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.itable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.itable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.itable.cellDoubleClicked.connect(lambda r, _c: self.view_dataset(r))
        ihdr = self.itable.horizontalHeader()
        ihdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ihdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.itable.setShowGrid(False)
        self.itable.setAlternatingRowColors(True)
        lay.addWidget(self.itable, 1)

        lay.addWidget(row(
            button("Hitmap, pixels", lambda: self.plot("hitmap")),
            button("Hitmap, clusters", lambda: self.plot("cmap")),
            button("ToT, peak pixel", lambda: self.plot("tot")),
            button("ToT, cluster total", lambda: self.plot("stot")),
            button("Cluster size histogram", lambda: self.plot("csize")),
            button("Time since TDC edge", lambda: self.plot("tdc")),
            button("Timewalk curve", lambda: self.plot("timewalk")),
            None))

        self.c_tdcref_i = QComboBox()
        self.c_tdcref_i.addItems(TDC_REFERENCES)
        self.c_tdcref_i.setCurrentText(self.cfg.get("tdc_reference",
                                                    TDC_REFERENCES[0]))
        self.c_tdcref_i.setToolTip(
            "Which TDC edge starts the clock. Shared with the same setting on "
            "the Advanced tab.")
        lay.addWidget(row(
            QLabel("TDC reference:"), self.c_tdcref_i,
            button("Add TDC columns to this file", self.write_tdc_columns),
            button("Preview frame", self.preview_tdc_frame),
            None))

        self.sp_tw_cut_i = self._ctot_cut_spin(
            self.cfg.get("timewalk_ctot_cut", TW_DEFAULT_CTOT_CUT_NS))
        self.cb_tw_hits_i = QCheckBox("also every pixel hit")
        self.cb_tw_hits_i.setChecked(bool(self.cfg.get("timewalk_hits", False)))
        self.cb_tw_hits_i.setToolTip(
            "Also add toa_tw as a last column of PixelHits: 8 more bytes per "
            "hit. Shared with the same setting on the Advanced tab.")
        lay.addWidget(row(
            QLabel("Timewalk ctot cut:"), self.sp_tw_cut_i, self.cb_tw_hits_i,
            button("Add timewalk columns to this file",
                   self.write_timewalk_columns),
            None))

        # Bottom panel: the file summary, and the DCR analysis beside it.
        self.itabs = QTabWidget()
        self.isum = QPlainTextEdit()
        self.isum.setReadOnly(True)
        self.isum.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.itabs.addTab(self.isum, "Summary")
        self.itabs.addTab(self._build_dcr_page(), "DCR")
        lay.addWidget(self.itabs, 1)

    def _build_dcr_page(self):
        """The DCR page: controls, the report, plots and export."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)

        self.c_dcr_time = QComboBox()
        for key, label in TIME_SOURCES.items():
            self.c_dcr_time.addItem(label, key)
        i = self.c_dcr_time.findData(
            self.cfg.get("dcr_time_source", DCR_DEFAULT_TIME_SOURCE))
        self.c_dcr_time.setCurrentIndex(max(i, 0))
        self.c_dcr_time.setToolTip(
            "What the counts are divided by.\n"
            "Frames, live time from ToA: first-to-last hit minus the gaps "
            "between frames, found in the hits themselves.\n"
            "Frames x exposure: NumberOfFrames x ExposureTime from "
            "measurement_metadata.json.\n"
            "ToA span: first to last hit, gaps between frames included.\n"
            "Wall clock: StartDateTime to StopDateTime, overhead included.")
        self.c_dcr_time.currentIndexChanged.connect(self._render_dcr)

        self.sp_dcr_k = QDoubleSpinBox()
        self.sp_dcr_k.setRange(1.5, 10000)
        self.sp_dcr_k.setDecimals(1)
        self.sp_dcr_k.setSingleStep(1)
        self.sp_dcr_k.setPrefix("> ")
        self.sp_dcr_k.setSuffix(" x median")
        self.sp_dcr_k.setValue(float(self.cfg.get("dcr_noisy_k",
                                                  DCR_DEFAULT_NOISY_K)))
        self.sp_dcr_k.setToolTip(
            "A pixel is noisy when its hit count is above this many times the "
            "median of the pixels that counted. Noisy pixels are left out of "
            "the 'clean' rates.")
        self.sp_dcr_k.valueChanged.connect(self._render_dcr)

        self.b_dcr = button("Compute DCR", self.compute_dcr, accent=True,
                            tip="Read every pixel hit and cluster of the open "
                                "file once; changing the time base or the "
                                "noisy cut afterwards needs no new read.")
        lay.addWidget(row(QLabel("Time base:"), self.c_dcr_time,
                          QLabel("Noisy pixel:"), self.sp_dcr_k,
                          self.b_dcr, None))

        self.dcr_text = QPlainTextEdit()
        self.dcr_text.setReadOnly(True)
        self.dcr_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.dcr_text.setPlaceholderText(
            "Open a file, then Compute DCR: rates per pixel and per cluster, "
            "noisy and silent pixels, and the rate frame by frame.")
        lay.addWidget(self.dcr_text, 1)

        lay.addWidget(row(
            button("DCR map, pixels", lambda: self.plot("dcr_map")),
            button("DCR map, clusters", lambda: self.plot("dcr_cmap")),
            button("Per-pixel DCR histogram", lambda: self.plot("dcr_hist")),
            button("Rate vs time", lambda: self.plot("dcr_time")),
            None,
            button("Export CSV...", self.export_dcr_csv,
                   tip="One row per pixel: hits, clusters, their rates, and "
                       "the noisy / silent flags.")))
        self.dcr_counts = None          # measure_dcr() result
        self.dcr_path = None            # the file it describes
        return page

    def pick_h5(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Select an HDF5 file", self.cfg.get("last_h5", ""),
            "HDF5 (*.hdf5 *.h5);;All files (*)", "", self.DLG)
        if p:
            self.cfg["last_h5"] = str(Path(p).parent)
            self.e_h5.setText(p)
            self.open_h5()

    def inspect_selected_output(self):
        rows = self.jtable.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, APP_NAME,
                                    "Select a row in the Process queue first.")
            return
        job = self.jobs[rows[0].row()]
        if not job.dst or not job.dst.exists():
            QMessageBox.information(self, APP_NAME, "That job has no output file yet.")
            return
        self.e_h5.setText(str(job.dst))
        self.open_h5()

    def open_h5(self):
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        path = Path(self.e_h5.text())
        self.itable.setRowCount(0)
        self.isum.clear()
        self.h5_listed = path          # what the Datasets table describes
        if self.dcr_path != path:
            self.dcr_counts = self.dcr_path = None
            self.dcr_text.clear()
        if not path.is_file():
            self.isum.setPlainText("No such file: " + str(path))
            return
        try:
            with h5py.File(path, "r") as f:
                rows, lines = [], [str(path),
                                   "file size: " + human_size(path.stat().st_size)]
                if dict(f.attrs):
                    lines.append("root attributes: " + str(dict(f.attrs)))
                det, judged = self._file_detector(f)
                self.h5_det = det
                lines.append(f"detector: {det.name}" + (
                    "  (judged from its ToT values)" if judged else
                    "  (no ToT to judge by -- assuming the detector selected "
                    "on the Process tab)"))

                def visit(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        rows.append((name, str(obj.shape), str(obj.dtype),
                                     str(obj.chunks), str(obj.compression)))
                f.visititems(visit)
                self.itable.setRowCount(len(rows))
                for r, vals in enumerate(rows):
                    for c, v in enumerate(vals):
                        self.itable.setItem(r, c, QTableWidgetItem(v))
                self.itable.resizeColumnsToContents()

                lines.append("")
                for key, label in (("PixelHits", "pixel hits"), ("Clusters", "clusters")):
                    if key in f:
                        n = f[key].shape[0]
                        lines.append(f"{label:14s} {n:,}")
                        if n:
                            lines.append("   fields: " + ", ".join(f[key].dtype.names or ()))
                if "PixelHits" in f and f["PixelHits"].shape[0]:
                    ph = f["PixelHits"]
                    head = ph[: min(200000, ph.shape[0])]
                    toa = head["toa"].astype("float64")
                    lines.append(f"   toa range (first {len(head):,} rows): "
                                 f"{toa.min():.0f} .. {toa.max():.0f}  "
                                 f"(units of {det.toa_seconds:g} s)")
                    lines.append(f"   x range {head['x'].min()}..{head['x'].max()}   "
                                 f"y range {head['y'].min()}..{head['y'].max()}")
                    if "tof" in (ph.dtype.names or ()):
                        valid = int((head["tof"] >= 0).sum())
                        lines.append(f"   tof: {valid:,} of {len(head):,} rows are >= 0 "
                                     + ("(ToF was computed)" if valid else
                                        "(tpx4dump computes no ToF)" if det is TPX4
                                        else "(no TDC reference -> ToF unset)"))
                if "Clusters" in f and f["Clusters"].shape[0]:
                    cl = f["Clusters"][: min(200000, f["Clusters"].shape[0])]
                    lines.append(f"   mean cluster size (first {len(cl):,}): "
                                 f"{cl['size'].mean():.2f}")
                lines.extend(self._tdc_summary(f, np, det))
                lines.extend(self._timewalk_summary(f))
                if "ExposureTimeBoundaries" in f:
                    etb = f["ExposureTimeBoundaries"][:]
                    lines.append(f"exposure time boundaries: {len(etb)} entries, "
                                 f"first {etb[:4].tolist() if len(etb) else []}")
                self.isum.setPlainText("\n".join(lines))
        except Exception:
            self.isum.setPlainText(traceback.format_exc())

    def view_dataset(self, r=None):
        """Open a scrollable window onto one dataset of the open file."""
        if r is None or r is False:
            r = self.itable.currentRow()
        item = self.itable.item(r, 0) if r >= 0 else None
        if item is None:
            QMessageBox.information(self, APP_NAME,
                                    "Open a file and select a dataset first.")
            return
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        try:
            DatasetViewer(self.h5_listed, item.text(), h5py, np,
                          self.mono, getattr(self, "h5_det", self.det),
                          self).show()
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))

    def _file_detector(self, f):
        """(Detector, judged) for an open file: judged from its ToT values,
        else the detector selected on the Process tab."""
        det = detect_from_file(f)
        return (det, True) if det else (self.det, False)

    def _tdc_summary(self, f, np, det=TPX3):
        """The TDC block of the Inspect summary: edges, rate, columns."""
        events = read_tdc_events(f, np)
        if events is None:
            why = ("tpx4dump writes no TDC data" if det is TPX4 else
                   "tpx3dump predates TDC support, or none was recorded")
            return ["TDC            /" + TDC_DATASET + " absent (" + why + ")"]
        raw_n = f[TDC_DATASET].shape[0]
        if len(events) == 0:
            return ["TDC            no edges recorded"]
        out = [f"TDC            {len(events):,} edge(s) "
               f"({raw_n:,} raw records; every chip repeats the packet)",
               "   " + describe_tdc_types(events, np)]
        for name in TOF_TDC_REFERENCES:
            sel = tdc_reference_edges(events, name, np)
            if len(sel) < 2:
                continue
            gaps = np.diff(sel["timestamp"].astype("int64")).astype("float64")
            gaps *= TDC_SECONDS_PER_TICK
            out.append(f"   {name:12s} {len(sel):,} edges, period "
                       f"{gaps.mean() * 1e6:.3f} us "
                       f"(+- {gaps.std() * 1e9:.1f} ns)")
        span = float(events["timestamp"][-1] -
                     events["timestamp"][0]) * TDC_SECONDS_PER_TICK
        out.append(f"   span         {span * 1e3:.3f} ms")
        for src_name, (_tf, col_name) in TDC_SOURCES.items():
            if col_name in f:
                a = f[col_name].attrs
                out.append(f"   /{col_name}: {f[col_name].shape[0]:,} rows, "
                           f"reference {a.get('tdc_reference', '?')}"
                           + ("" if a.get("written_by") == TDC_STAMP
                              else "  [not written by this GUI]"))
        return out

    def _timewalk_summary(self, f):
        """The timewalk block of the Inspect summary: curve and columns."""
        if TW_CURVE not in f:
            return ["timewalk       not corrected (no /" + TW_CURVE + ")"]
        a = f[TW_CURVE].attrs
        c = f[TW_CURVE][:]
        out = [f"timewalk       curve from {int(a.get('hits_used', 0)):,} hits, "
               f"ctot cut {a.get('ctot_cut_ns', '?'):g} ns"
               + ("" if a.get("written_by") == TW_STAMP
                  else "  [not written by this GUI]")]
        if len(c):
            out.append(f"   {c['delay_ns'][0]:.1f} ns at ToT {c['tot_ns'][0]:.0f} ns"
                       f" .. {c['delay_ns'][-1]:.2f} ns at ToT "
                       f"{c['tot_ns'][-1]:.0f} ns")
        for tname, (_t, _tot, field_name) in TW_FIELDS.items():
            if tname in f and field_name in (f[tname].dtype.names or ()):
                mine = f[tname].attrs.get(TW_FIELD_ATTR) == field_name
                out.append(f"   {tname}/{field_name}: last column"
                           + ("" if mine else "  [not written by this GUI]"))
        return out

    # -- timewalk columns -------------------------------------------------

    def write_timewalk_columns(self):
        """Measure this file's timewalk curve and write corrected times."""
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return
        cut = self.sp_tw_cut_i.value()
        hits = self.cb_tw_hits_i.isChecked()
        if QMessageBox.question(
                self, APP_NAME,
                f"Add timewalk-corrected times to\n{path.name}\n\n"
                f"ctot cut: {cut} ns\n\n"
                "This modifies the file. It adds ctoa_tw as the last column of "
                "Clusters" + (" and toa_tw as the last column of PixelHits"
                              if hits else "")
                + ", and the curve as /TimewalkCurve. The first time, the file "
                "is rewritten once (via a temporary copy beside it, so it "
                "needs that much free space); Luna's other columns are kept "
                "as they are.\n\nContinue?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.tabs.setCurrentWidget(self.tab_inspect)
        self.log(f"Adding timewalk columns to {path.name} (ctot cut {cut} ns)")
        try:
            self._busy(True)
            with h5py.File(path, "r") as f:
                det, _judged = self._file_detector(f)
            res = add_timewalk_columns(path, ctot_cut_ns=cut, pixel_hits=hits,
                                       detector=det, log=self.log)
        except Exception as exc:
            self.log("  FAILED: " + str(exc))
            QMessageBox.critical(self, APP_NAME,
                                 "Could not write the timewalk columns.\n\n"
                                 + str(exc))
            return
        finally:
            self._busy(False)
        self.open_h5()          # refresh the dataset table with the new ones
        c = res[TW_CURVE]
        QMessageBox.information(
            self, APP_NAME,
            f"Timewalk columns written.\n\nCurve from {c['hits_used']:,} hits "
            f"in {c['bins']} ToT bins; {c['delay_ns_lowest_tot']:.1f} ns of "
            "walk at the lowest ToT.\n\n" + "\n".join(
                f"{k}/{v['field']}: {v['rows']:,} rows" for k, v in res.items()
                if k != TW_CURVE))

    # -- TDC columns ------------------------------------------------------

    def write_tdc_columns(self):
        """Tag this file's hits and clusters with the TDC edge they follow."""
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return
        ref = self.c_tdcref_i.currentText()
        if QMessageBox.question(
                self, APP_NAME,
                f"Write TDC columns into\n{path.name}\n\n"
                f"Reference: {ref}\n\n"
                "This modifies the file in place. It adds /PixelHitsTDC and "
                "/ClustersTDC; PixelHits, Clusters and TDCEvents are left "
                "exactly as tpx3dump wrote them.\n\nContinue?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.tabs.setCurrentWidget(self.tab_inspect)
        self.log(f"Adding TDC columns to {path.name} ({ref})")
        try:
            self._busy(True)
            res = add_tdc_columns(path, ref, log=self.log)
        except Exception as exc:
            self.log("  FAILED: " + str(exc))
            QMessageBox.critical(self, APP_NAME,
                                 "Could not write the TDC columns.\n\n" + str(exc))
            return
        finally:
            self._busy(False)
        self.open_h5()          # refresh the dataset table with the new ones
        QMessageBox.information(
            self, APP_NAME,
            "TDC columns written.\n\n" + "\n".join(
                f"/{k}: {v['tagged']:,} of {v['rows']:,} rows tagged"
                for k, v in res.items()))

    def preview_tdc_frame(self):
        """Show the head of the joined frame, so the columns are visible."""
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        pd = require_pandas(self)
        if pd is None:
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return
        ROWS = 40
        blocks = []
        try:
            self._busy(True)
            edges = read_tdcs(path)
            blocks.append("read_tdcs() -- the edges themselves, deduplicated\n"
                          + edges.to_string(max_rows=ROWS))
            for which in TDC_SOURCES:
                try:
                    # limit= keeps this instant on a file with 10^8 hits; the
                    # stored columns are used when they are there, so what is
                    # shown is what a full read would give.
                    df = read_with_tdc(path, which, limit=ROWS)
                except ValueError as exc:
                    blocks.append(f"read_with_tdc(..., {which!r}) -- {exc}")
                    continue
                blocks.append(
                    f"read_with_tdc(..., {which!r})   reference "
                    f"{df.attrs['tdc_reference']}, "
                    + ("read from the file" if df.attrs["tdc_from_file"]
                       else "computed on the fly -- not stored yet")
                    + "\n" + df.to_string(max_rows=ROWS))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME,
                                 "Could not build the frame.\n\n" + str(exc))
            return
        finally:
            self._busy(False)

        dlg = QDialog(self)
        dlg.setWindowTitle(path.name + " -- first %d rows with TDC" % ROWS)
        dlg.resize(1000, 700)
        lay = QVBoxLayout(dlg)
        view = QPlainTextEdit("\n\n".join(blocks))
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        lay.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.show()              # modeless, like the plots
        self._open_plots = getattr(self, "_open_plots", [])
        self._open_plots.append(dlg)

    def _busy(self, on):
        """Hourglass while a synchronous read/write holds the event loop."""
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
        QApplication.processEvents()

    # -- DCR --------------------------------------------------------------

    def compute_dcr(self):
        """One pass over the open file; the DCR page then renders from it."""
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return
        self.itabs.setCurrentIndex(1)
        self.b_dcr.setEnabled(False)
        self._busy(True)
        shown = [0.0]

        def progress(frac, text):
            # A 6 GB file takes ~20 s: say how far along, a few times a second.
            now = time.monotonic()
            if now - shown[0] > 0.25:
                shown[0] = now
                self.dcr_text.setPlainText(
                    f"Reading {path.name}\n{text}   ({100 * frac:.0f} %)")
                QApplication.processEvents()
            return False

        try:
            with h5py.File(path, "r") as f:
                det, _judged = self._file_detector(f)
                counts = measure_dcr(f, det, find_measurement_metadata(path),
                                     progress)
        except Exception:
            self.dcr_text.setPlainText(traceback.format_exc())
            return
        finally:
            self._busy(False)
            self.b_dcr.setEnabled(True)
        self.dcr_counts, self.dcr_path = counts, path
        self._render_dcr()

    def _render_dcr(self, *_a):
        """Redraw the DCR report from the cached counts: no file read."""
        if self.dcr_counts is None:
            return
        lines, _maps = dcr_report(self.dcr_counts,
                                  self.c_dcr_time.currentData(),
                                  self.sp_dcr_k.value())
        self.dcr_text.setPlainText("\n".join([str(self.dcr_path), ""] + lines))

    def export_dcr_csv(self):
        if self.dcr_counts is None:
            QMessageBox.information(self, APP_NAME, "Compute DCR first.")
            return
        default = self.dcr_path.with_name(self.dcr_path.stem + "_dcr.csv")
        p, _ = QFileDialog.getSaveFileName(
            self, "Export DCR per pixel", str(default),
            "CSV (*.csv);;All files (*)", "", self.DLG)
        if not p:
            return
        try:
            write_dcr_csv(p, self.dcr_counts, self.c_dcr_time.currentData(),
                          self.sp_dcr_k.value(), h5_path=str(self.dcr_path))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not write the CSV:\n{exc}")
            return
        self.dcr_text.appendPlainText(f"\nwrote {p}")

    def _draw_dcr(self, what, path, fig, ax, np):
        """The DCR plots, drawn from the cached counts of this file."""
        c = self.dcr_counts
        if c is None or self.dcr_path != path:
            QMessageBox.information(self, APP_NAME,
                                    "Compute DCR for this file first (DCR tab).")
            return False
        T, used, _note = pick_time(c, self.c_dcr_time.currentData())
        if T is None:
            QMessageBox.information(self, APP_NAME,
                                    "No measurement time is available.")
            return False
        k = self.sp_dcr_k.value()
        m = dcr_maps(c, T, k, np)
        if what in ("dcr_map", "dcr_hist") and not c["n_hits"]:
            QMessageBox.information(self, APP_NAME, "This file has no pixel hits.")
            return False

        if what == "dcr_map":
            self._draw_hitmap(fig, ax, m["hit_rate"], np, "Hz / pixel",
                              f"DCR, pixels -- {fmt_rate(c['n_hits'] / T)} "
                              f"over {T:.4g} s")
        elif what == "dcr_cmap":
            if not c["n_clusters"]:
                QMessageBox.information(self, APP_NAME, "This file has no clusters.")
                return False
            self._draw_hitmap(fig, ax, m["cluster_rate"], np,
                              "clusters / s per pixel",
                              f"DCR, clusters -- {fmt_rate(c['n_clusters'] / T)} "
                              f"over {T:.4g} s")
        elif what == "dcr_hist":
            r = m["hit_rate"][~m["silent"]]
            lo, hi = float(r.min()), float(r.max())
            # Log bins: a noisy pixel can sit decades above the bulk.
            bins = (np.logspace(np.log10(lo), np.log10(hi * 1.0001), 120)
                    if hi > lo else 20)
            ax.hist(r, bins=bins, histtype="step")
            med = m["median_hits"] / T
            # Reference lines, not data: the theme's marker colour.
            ref = self._manager.theme.marker
            ax.axvline(med, ls="--", lw=1, color=ref,
                       label=f"median {fmt_rate(med)}")
            ax.axvline(m["noisy_cut_hits"] / T, ls=":", lw=1, color=ref,
                       label=f"noisy cut, {k:g} x median")
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.legend()
            ax.set(title=f"Per-pixel DCR -- {r.size:,} pixels that counted, "
                         f"{int(m['silent'].sum()):,} silent not shown",
                   xlabel=f"DCR (Hz)   [{TIME_SOURCES[used]}]",
                   ylabel="Pixels (-)")
        else:                                           # dcr_time
            # Each frame over its own live time, so neither the gaps between
            # frames nor the time base chosen above bend the curve.
            # y: the median pixel's DCR in each frame (or time bin), over the
            # pixels that counted in the whole run. Falls back to the mean
            # pixel when the per-frame maps could not be kept.
            live = c["frame_live_s"]
            if live is not None and len(live) > 1:
                x = c["frame_start_s"] + live / 2
                dt = live
                totals = (c["frame_hits"], c["frame_clusters"])
                how = f"one point per frame ({len(live)})"
            elif c["bin_edges_s"] is not None:
                e = c["bin_edges_s"]
                dt = np.diff(e)
                x = (e[:-1] + e[1:]) / 2
                totals = (c["bin_hits"], c["bin_clusters"])
                how = f"{dt[0]:.3g} s bins"
            else:
                QMessageBox.information(self, APP_NAME,
                                        "Too few hits to follow over time.")
                return False
            # Medians exist per frame or per bin; use them only if they match
            # the slots chosen above.
            meds = (c["med_hits"], c["med_clusters"])
            if c["med_by_frame"] != (live is not None and len(live) > 1):
                meds = (None, None)
            counted = int((c["hit_map"] > 0).sum() if c["n_hits"]
                          else (c["cluster_map"] > 0).sum())
            panels = []
            for label, med, tot in (("Pixel hits", meds[0], totals[0]),
                                    ("Clusters", meds[1], totals[1])):
                if tot is None or not np.any(tot):
                    continue
                if med is not None:
                    panels.append((label, "median", med / dt))
                else:
                    panels.append((label, "mean", tot / max(counted, 1) / dt))
            if not panels:
                QMessageBox.information(self, APP_NAME,
                                        "Nothing to follow over time.")
                return False
            ax.remove()
            axes = fig.subplots(len(panels), 1, sharex=True, squeeze=False)[:, 0]
            for a, (label, stat, r) in zip(axes, panels):
                a.plot(x, r, marker=".", lw=1)
                a.set_ylabel(f"{label}, {stat}\npixel DCR (Hz)")
                a.set_title(f"{label}: {stat} pixel {fmt_rate(float(np.median(r)))}"
                            f" (median over time)", fontsize="medium")
            note = ""
            if any(stat == "mean" for _l, stat, _r in panels):
                note = ("\nmedian unavailable (" + (c.get("med_why") or
                        "frames differ") + "): mean per pixel shown")
            fig.suptitle(f"DCR vs time -- {how}, {counted:,} pixels "
                         f"that counted{note}")
            axes[-1].set_xlabel("Time (s)")
        return True

    # -- plots ------------------------------------------------------------

    def plot(self, what):
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        try:
            import matplotlib
            matplotlib.use("QtAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import (
                FigureCanvasQTAgg, NavigationToolbar2QT)
        except Exception:
            QMessageBox.critical(self, APP_NAME,
                                 "matplotlib is required for plots:\n"
                                 "    python -m pip install matplotlib")
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return

        CAP = 8_000_000          # rows read at most, keeps the UI responsive
        # The plot is drawn in the theme as it is now; a later theme change
        # applies to the plots opened after it.
        m = self._manager
        with plot_style_context(m.preset_key, m.mpl_rc(), m.mpl_rc_changes()):
            fig = Figure(figsize=PLOT_FIGSIZE, dpi=100)
            ax = fig.add_subplot(111)
            ok = self._draw_plot(what, path, fig, ax, CAP, h5py, np)
            if ok:
                self._glow(fig)
                fig.tight_layout()
        if not ok:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(path.name + " -- " + PLOT_TITLES.get(what, what))
        dlg.resize(760, 660)
        lay = QVBoxLayout(dlg)
        canvas = FigureCanvasQTAgg(fig)
        lay.addWidget(NavigationToolbar2QT(canvas, dlg))
        lay.addWidget(canvas, 1)
        dlg.show()          # modeless: compare several plots side by side
        self._open_plots = getattr(self, "_open_plots", [])
        self._open_plots.append(dlg)

    def _draw_plot(self, what, path, fig, ax, CAP, h5py, np):
        """Draw one plot onto ax. Returns False if there was nothing to draw.

        Runs inside the style context so every artist -- including the
        colorbar, which is its own axes -- picks up the style rcParams.
        """
        if what.startswith("dcr_"):
            return self._draw_dcr(what, path, fig, ax, np)
        try:
            with h5py.File(path, "r") as f:
                if what == "tdc":
                    return self._draw_tdc(f, ax, CAP, np)
                if what == "timewalk":
                    return self._draw_timewalk(f, ax, CAP, np)
                # Only the pixel hitmap comes from PixelHits; everything else
                # is a cluster-level quantity and reads Clusters.
                if what == "hitmap":
                    if "PixelHits" not in f or not f["PixelHits"].shape[0]:
                        QMessageBox.information(
                            self, APP_NAME, "This file has no pixel hits "
                                            "(processed with --discard-pixel-data?).")
                        return False
                    d = f["PixelHits"]
                    n = min(CAP, d.shape[0])
                    img = self._accumulate_xy(d, n, np, "x", "y")
                    self._draw_hitmap(fig, ax, img, np, "hits / pixel",
                                      f"Hitmap, pixels -- {n:,} hits")
                else:
                    if "Clusters" not in f or not f["Clusters"].shape[0]:
                        QMessageBox.information(
                            self, APP_NAME, "This file has no clusters "
                                            "(processed with --disable-clustering?).")
                        return False
                    d = f["Clusters"]
                    n = min(CAP, d.shape[0])
                    if what == "cmap":
                        img = self._accumulate_xy(d, n, np, "cx", "cy")
                        self._draw_hitmap(fig, ax, img, np,
                                          "clusters / pixel",
                                          f"Hitmap, clusters -- {n:,} clusters")
                    elif what == "tot":
                        # Clusters/ctot is the *peak pixel* ToT of the cluster,
                        # not its total -- verified against PixelHits: ctot ==
                        # max(tot) over the cluster's hits for every cluster in
                        # the reference file, and it saturates at exactly the
                        # single-pixel maximum. Clusters/sum_tot is the total;
                        # that is the "stot" plot below.
                        det, _judged = self._file_detector(f)
                        ctot = (self._gather(d, n, np, "ctot").astype("float64")
                                * (det.tot_seconds * 1e9))          # -> ns
                        # One bin per ToT step (25 ns on Timepix3), the finest
                        # binning that carries no aliasing -- or a whole
                        # number of steps once that would pass TOT_MAX_BINS,
                        # as it does for Timepix4's 0.195 ns step.
                        edges, step = tot_bin_edges(float(ctot.max()),
                                                    det.tot_lsb_ns, TOT_MAX_BINS, np)
                        ax.hist(ctot, bins=edges, histtype="step",)
                        ax.set(title=f"Peak-pixel ToT -- {n:,} clusters",
                               xlabel=f"ToT (ns)   ({step:g} ns bins)",
                               ylabel="Counts (-)", yscale="log")
                    elif what == "stot":
                        # The cluster's summed ToT: a deposited-charge proxy,
                        # unlike ctot which saturates once the charge starts
                        # spreading to neighbouring pixels instead of driving
                        # the central one higher.
                        det, _judged = self._file_detector(f)
                        stot = (self._gather(d, n, np, "sum_tot").astype("float64")
                                * (det.tot_seconds * 1e9))          # -> ns
                        # Still a whole number of ToT steps, just a coarser
                        # one: sum_tot runs to ~227 us and the native 25 ns
                        # tick would be ~9000 bins.
                        edges, step = tot_bin_edges(float(stot.max()),
                                                    det.tot_lsb_ns,
                                                    STOT_TARGET_BINS, np)
                        ax.hist(stot, bins=edges, histtype="step",)
                        ax.set(title=f"Cluster total ToT -- {n:,} clusters",
                               xlabel=f"summed ToT (ns)   ({step:g} ns bins)",
                               ylabel="Counts (-)", yscale="log")
                    else:                                   # csize
                        s = self._gather(d, n, np, "size").astype("int64")
                        ax.hist(s, bins=CSIZE_BINS, range=(0, CSIZE_MAX),)
                        title = f"Cluster size -- {n:,} clusters"
                        over = int((s > CSIZE_MAX).sum())
                        if over:        # never truncate silently
                            title += f"   ({over:,} above {CSIZE_MAX} not shown)"
                        ax.set(title=title, xlabel="Cluster size (-)",
                               ylabel="Counts (-)")
        except Exception:
            QMessageBox.critical(self, APP_NAME, traceback.format_exc())
            return False
        return True

    def _draw_tdc(self, f, ax, CAP, np):
        """Histogram of how long after its TDC edge each cluster arrived.

        Computed from /TDCEvents rather than read from PixelHits/tof, so it
        works whether or not --tof-tdc-reference was passed and whichever
        reference is picked now. Clusters, not hits: one entry per particle.
        """
        events = read_tdc_events(f, np)
        if events is None or len(events) == 0:
            QMessageBox.information(
                self, APP_NAME,
                "This file has no TDC edges to measure from.")
            return False
        ref = self.c_tdcref_i.currentText()
        edges = tdc_reference_edges(events, ref, np)
        if len(edges) == 0:
            QMessageBox.information(
                self, APP_NAME, f"No {ref} edges in this file.\nIt has "
                + describe_tdc_types(events, np) + ".")
            return False
        src = "Clusters" if ("Clusters" in f and f["Clusters"].shape[0]) else "PixelHits"
        if src not in f or not f[src].shape[0]:
            QMessageBox.information(self, APP_NAME,
                                    "This file has no hits or clusters.")
            return False
        field_name = TDC_SOURCES[src][0]
        n = min(CAP, f[src].shape[0])
        times = self._gather(f[src], n, np, field_name)
        cols = tag_times_with_tdc(times, edges, np)
        good = cols["tdc_dt"][cols["tdc_index"] >= 0].astype("float64")
        if not len(good):
            QMessageBox.information(
                self, APP_NAME,
                f"Every row precedes the first {ref} edge, so none of them "
                "has a time to measure.")
            return False
        us = good * (TDC_SECONDS_PER_TICK * 1e6)
        ax.hist(us, bins=200, histtype="step")
        dropped = n - len(good)
        title = f"Time since {ref} -- {len(good):,} {src.lower()}"
        if dropped:                 # never truncate silently
            title += f"   ({dropped:,} before the first edge)"
        ax.set(title=title, xlabel="t - t(TDC)  (us)", ylabel="Counts (-)",
               yscale="log")
        return True

    def _draw_timewalk(self, f, ax, CAP, np):
        """Timewalk (mean delay) and jitter (sigma) against hit ToT.

        The stored /TimewalkCurve when its ctot cut matches the box, else
        measured now from the first CAP hits -- so the cut can be tried out
        before anything is written.
        """
        cut = self.sp_tw_cut_i.value()
        stored = (TW_CURVE in f and
                  float(f[TW_CURVE].attrs.get("ctot_cut_ns", -1)) == cut)
        if stored:
            curve = f[TW_CURVE][:]
            used = int(f[TW_CURVE].attrs.get("hits_used", 0))
            src = "stored in the file"
        else:
            det, _judged = self._file_detector(f)
            try:
                curve, used = measure_timewalk(f, det, cut, CAP, np)
            except ValueError as exc:
                QMessageBox.information(self, APP_NAME, str(exc))
                return False
            src = "measured now, not stored"
        ax.plot(curve["tot_ns"], curve["delay_ns"], ".-", label="Timewalk (mean delay)")
        ax.plot(curve["tot_ns"], curve["sigma_ns"], ".-", label="Jitter (sigma)")
        ax.set_yscale("log")
        ax.set(title=f"Timewalk, ctot cut {cut} ns -- {used:,} hits\n({src})",
               xlabel="Hit ToT (ns)", ylabel="Time (ns)")
        ax.legend()
        return True

    def _glow(self, fig):
        """The glow under the traces, when the theme wants it.

        From mplcyberpunk, an optional extra: without it the plot is simply
        drawn without the glow. Only lines glow, so histograms and hitmaps
        are left as they are.
        """
        if not self._manager.theme.glow:
            return
        try:
            import mplcyberpunk
        except Exception:
            return
        for a in fig.axes:
            if a.get_lines():
                try:
                    mplcyberpunk.make_lines_glow(a, diff_linewidth=1.1)
                except Exception:
                    pass        # decoration; never worth losing the plot over

    def _style_colorbar(self, cb):
        """Theme the colorbar explicitly.

        A colorbar lives on its own Axes, so none of the theming applied to the
        main axes reaches it -- its ticks and label keep matplotlib default
        near-black and vanish against a dark figure. Called inside the style
        context, so rcParams are the theme's.
        """
        import matplotlib as mpl
        text, tick = mpl.rcParams["text.color"], mpl.rcParams["ytick.color"]
        edge = mpl.rcParams["axes.edgecolor"]
        cb.ax.yaxis.label.set_color(text)
        cb.ax.tick_params(colors=tick)
        if cb.outline is not None:
            cb.outline.set_edgecolor(edge)
        return cb

    @staticmethod
    def _gather(dset, n, np, field_name, step=2_000_000):
        parts = [dset[i:min(i + step, n)][field_name] for i in range(0, n, step)]
        return np.concatenate(parts) if parts else np.array([])

    def _accumulate_xy(self, dset, n, np, fx, fy, step=2_000_000):
        """2D histogram built in slices so huge files do not blow up memory.

        Width and height follow the data separately: Timepix4 is 448 x 512,
        and a square image would show 64 columns that cannot hold a hit.
        Never smaller than one Timepix3 chip.
        """
        h = w = 0
        img = None
        for i in range(0, n, step):
            chunk = dset[i:min(i + step, n)]
            x = chunk[fx].astype("int64")
            y = chunk[fy].astype("int64")
            need_w = int(x.max(initial=0)) + 1
            need_h = int(y.max(initial=0)) + 1
            if img is None or need_w > w or need_h > h:
                new_w, new_h = max(need_w, 256, w), max(need_h, 256, h)
                grown = np.zeros((new_h, new_w), dtype="int64")
                if img is not None:
                    grown[:h, :w] = img
                img, h, w = grown, new_h, new_w
            flat = np.bincount(y * w + x, minlength=h * w)
            img += flat.reshape(h, w)
        return img if img is not None else np.zeros((256, 256), dtype="int64")

    def _draw_hitmap(self, fig, ax, img, np, unit, title):
        """imshow a hitmap, keeping a few runaway pixels off the colour scale.

        One hot or reference pixel can hold a third of all hits (a Timepix4
        corner pixel firing at the laser's 190 kHz, for one) and a linear scale
        up to it paints everything else as zero. When the hottest pixel is far
        above the 99.9th percentile of the hit pixels, the scale stops there,
        the colour bar gets an arrow, and the title names what was clipped.
        """
        hit = img[img > 0]
        vmax = float(hit.max()) if hit.size else 1.0
        note = ""
        if hit.size:
            cap = float(np.percentile(hit, HITMAP_CLIP_PERCENTILE))
            if vmax > HITMAP_CLIP_FACTOR * cap:
                over = int((img > cap).sum())
                y0, x0 = np.unravel_index(int(img.argmax()), img.shape)
                note = (f"\n{over} pixel(s) above the colour scale -- hottest "
                        f"({x0}, {y0}): {int(img.max()):,}")
                vmax = cap
        im = ax.imshow(img, origin="lower", aspect="equal", vmin=0, vmax=vmax)
        self._style_colorbar(
            fig.colorbar(im, ax=ax, label=unit,
                         extend="max" if note else "neither"))
        # Never a grid over an image, whatever the theme says: it would be
        # drawn across the pixels it is meant to help read.
        ax.grid(False)
        ax.set(title=title + note, xlabel="x (pixels)", ylabel="y (pixels)")

    # -- window geometry ---------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:            # first map only; never fight the user
            self._fitted = True         # once they have resized it themselves
            # Deferred by one event-loop turn on purpose: inside showEvent the
            # frame has not been applied yet and frameGeometry() still returns
            # the bare client rect, so the title bar measures as zero and the
            # window ends up exactly one title bar too tall.
            QTimer.singleShot(0, self._fit_to_screen)

    def _fit_to_screen(self):
        """Shrink and centre the window if its *frame* does not fit the screen.

        The frame -- title bar and resize borders -- is not part of the layout,
        so a client area sized to the work area still hangs off the bottom edge.
        Must run after the window is mapped, where frameGeometry() finally
        reports something real.
        """
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        frame = self.frameGeometry()
        chrome_w = max(0, frame.width() - self.width())
        chrome_h = max(0, frame.height() - self.height())
        # Fractional scaling (125% here) means Qt's logical size does not land
        # on a whole number of physical pixels, so a window sized to exactly
        # the work area still spills a pixel or two. 8 px of slack is cheaper
        # than reasoning about the rounding.
        margin = 8
        self.resize(min(self.width(), avail.width() - chrome_w - margin),
                    min(self.height(), avail.height() - chrome_h - margin))
        frame = self.frameGeometry()
        frame.moveCenter(avail.center())
        self.move(frame.topLeft())
