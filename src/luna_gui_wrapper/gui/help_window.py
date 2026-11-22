"""The Help window: what every tab, option and flag does, inside the app.

Opened from the Help menu or F1. It is one window, hidden rather than
destroyed on close, so it reopens where the reader left off.

The flag reference and the column units are generated from the same tables
the Advanced tab and the row viewer use (FLAG_GROUPS, field_units), so they
cannot drift apart. The prose is written here. The page is rebuilt on a theme
change, since rich text takes its colours from the HTML, not the stylesheet.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QTextBrowser, QVBoxLayout)

from .. import __version__
from ..functions.common import APP_NAME
from ..functions.config import CONFIG_PATH
from ..functions.detectors import TPX3, TPX4, field_units
from ..functions.flags import FLAG_GROUPS
from ..functions.naming import DEFAULT_TEMPLATE
from ..functions.plotting import PLOT_TITLES
from .widgets import row

# (anchor, title) in page order; the list on the left is built from this.
SECTIONS = [
    ("start", "Getting started"),
    ("detectors", "Timepix3 and Timepix4"),
    ("process", "Process tab"),
    ("advanced", "Advanced tab"),
    ("naming", "Name templates"),
    ("flags", "Luna flags"),
    ("inspect", "Inspect HDF5 tab"),
    ("file", "What is in the file"),
    ("tdc", "TDC"),
    ("timewalk", "Timewalk correction"),
    ("dcr", "Dark count rate"),
    ("themes", "Themes and preferences"),
    ("trouble", "Troubleshooting"),
    ("about", "Settings and about"),
]

PLACEHOLDERS = [
    ("{stem}", "fCqk_000000", "the raw filename (.tpx3 / .tpx4)"),
    ("{measurement}", "Measurement_Aug_07_2026_12h52m45s", "measurement folder"),
    ("{campaign}", "data_DCR_07.08.2026", "the folder above that"),
    ("{date} {time} {datetime}", "2026-08-07, 12-52-45", "StartDateTime"),
    ("{comment}", "DCR-0V-gain", "CommentAtTimeOfMeasurement, or comment.txt"),
]

PLOT_NOTES = {
    "hitmap": ("PixelHits x, y", "hits per pixel, including cluster spread; "
               "sized to the chip (448 x 512 on Timepix4); a few runaway "
               "pixels are kept off the colour scale and named in the title"),
    "cmap": ("Clusters cx, cy", "each cluster counted once, at its centroid; "
             "same colour-scale rule"),
    "tot": ("Clusters ctot", "peak-pixel ToT in ns; one bin per ToT step on "
            "Timepix3 (25 ns), a whole number of steps on Timepix4; log y"),
    "stot": ("Clusters sum_tot", "total ToT of the cluster in ns — the "
             "deposited-charge proxy; ~300 bins snapped to ToT steps, log y"),
    "csize": ("Clusters size", "pixels per cluster, 0-40; anything above is "
              "counted in the title"),
    "tdc": ("Clusters ctoa - TDCEvents", "time since the reference edge, over "
            "one trigger period, log y"),
    "timewalk": ("PixelHits toa - its cluster's ctoa", "timewalk (mean delay) "
                 "and jitter against hit ToT, log y; the stored curve when its "
                 "ctot cut matches the box, else measured from the first 8 M "
                 "hits without writing anything"),
}

TROUBLE = [
    ("Status reads none, \"no WSL distribution installed\"",
     "Run <code>wsl --install -d Ubuntu</code> in PowerShell, then press "
     "<b>Check install</b>. No restart needed."),
    ("tpx3dump not found under the Luna folder",
     "Point at the install root or its <code>bin</code> folder, not at the .zip."),
    ("<code>index out of bounds: the len is 0</code> after "
     "<code>Skipping file ...</code>",
     "WSL cannot see the drive the data is on — normal for USB sticks. "
     "Answer <b>Yes</b> when the GUI offers to mount it."),
    ("UNC path rejected", "Map <code>\\\\server\\share</code> to a drive letter first."),
    ("<code>H5Fcreate(): unable to create file</code>, "
     "<i>output name too long</i>",
     "A file name may be at most 255 characters, and <code>{comment}</code> "
     "can take a long <code>comment.txt</code> into it. Shorten the name "
     "template, then press <b>Rerun failed</b>."),
    ("Files report <i>skipped - output exists</i>",
     "That is <b>Skip files whose output already exists</b>. Tick "
     "<b>Overwrite</b> on the rows to redo, or untick the option."),
    ("A run refuses to start with a flag error",
     "A value tpx3dump would reject, e.g. <code>--eps-t 100</code> without a "
     "unit. The message names the flag; fix it on the Advanced tab."),
    ("Inspect tab does nothing",
     "Install the analysis packages: <code>pip install h5py numpy pandas "
     "matplotlib</code>."),
    ("Inspect cannot read a file written with Blosc compression",
     "h5py needs <code>pip install hdf5plugin</code> for Blosc. Deflate needs "
     "nothing extra."),
    ("\"No /TDCEvents in this file\"",
     "The file predates tpx3dump's TDC support, or the run recorded no TDC. "
     "Reprocess the .tpx3."),
    ("Most rows report no TDC edge",
     "They come before the first reference edge — normal at the start of a run."),
    ("\"Too few multi-pixel clusters\" for the timewalk",
     "Few clusters reach the ctot cut (dim light, or mostly single-pixel "
     "clusters). Lower the cut, or check that the file was clustered and kept "
     "its pixel hits."),
    ("Batch is slow on Windows",
     "/mnt/d goes through WSL's file bridge; for big jobs copy the raw data "
     "into the WSL filesystem."),
]


def _table(rows, head, pal, widths=()):
    """A simple striped table; cells are HTML already."""
    out = ['<table width="100%" cellspacing="0" cellpadding="5">', "<tr>"]
    for i, h in enumerate(head):
        w = f' width="{widths[i]}"' if i < len(widths) else ""
        out.append(f'<th align="left"{w} bgcolor="{pal["surface_container_high"]}">'
                   f"{h}</th>")
    out.append("</tr>")
    for n, cells in enumerate(rows):
        bg = pal["surface_container"] if n % 2 else pal["surface_container_low"]
        out.append(f'<tr bgcolor="{bg}">'
                   + "".join(f'<td valign="top">{c}</td>' for c in cells)
                   + "</tr>")
    out.append("</table>")
    return "".join(out)


def _prose(text):
    """Escape for HTML, with the code's " -- " set as a proper dash."""
    return escape(text).replace(" -- ", " — ")


# Which converter accepts a flag, as the flag tables show it.
_FOR = {("tpx3", "tpx4"): "both", ("tpx3",): "Timepix3", ("tpx4",): "Timepix4"}


def _units_html(pal):
    """Column meanings for both detectors side by side."""
    u3, u4 = field_units(TPX3), field_units(TPX4)
    cols = list(u3) + [k for k in u4 if k not in u3]
    return _table([[f"<code>{escape(k)}</code>", escape(u3.get(k, "")),
                    escape(u4.get(k, ""))] for k in cols],
                  ["Column", "Timepix3", "Timepix4"], pal, ("18%", "41%"))


def _flags_html(pal):
    parts = []
    for title, group in FLAG_GROUPS:
        rows = []
        for f in group:
            what = _prose(f.note[0].upper() + f.note[1:]) + "."
            if f.tip:
                what += f'<br><span class="faint">{_prose(f.tip)}</span>'
            if f.choices and f.kind == "choice":
                what += ('<br><span class="faint">Values: '
                         + ", ".join(f"<code>{escape(c)}</code>" for c in f.choices)
                         + "</span>")
            if f.gui_default:
                dflt = (f"<code>{escape(f.gui_default)}</code><br>"
                        f'<span class="faint">Luna: {escape(f.default)}</span>')
            else:
                dflt = f"<code>{escape(f.default)}</code>" if f.default else ""
            rows.append([f"<code>{escape(f.flag)}</code>", dflt,
                         _FOR.get(f.detectors, ""), what])
        parts.append(f"<h3>{escape(title)}</h3>"
                     + _table(rows, ["Flag", "Default", "For", "What it does"], pal,
                              ("28%", "11%", "11%")))
    return "".join(parts)


def help_html(pal) -> str:
    """The whole help page as HTML, coloured for palette `pal`."""
    ph = _table([[f"<code>{escape(p)}</code>", escape(e), escape(s)]
                 for p, e, s in PLACEHOLDERS],
                ["Placeholder", "Example", "From"], pal, ("30%", "32%"))
    plots = _table([[f"<b>{escape(PLOT_TITLES[k])}</b>", escape(src), escape(what)]
                    for k, (src, what) in PLOT_NOTES.items()],
                   ["Plot", "Reads", "Shows"], pal, ("24%", "26%"))
    units = _units_html(pal)
    trouble = _table([[s, fix] for s, fix in TROUBLE],
                     ["Symptom", "Cause and fix"], pal, ("38%",))

    return f"""
<a name="start"></a><h2 class="first">Getting started</h2>
<p>The GUI runs your own Luna over a batch of raw files and writes one
<code>.hdf5</code> per file: <code>tpx3dump</code> for Timepix3
(<code>.tpx3</code>), <code>tpx4dump</code> for Timepix4 (<code>.tpx4</code>).
Luna is not included; you point the GUI at your installation once per
detector. On Windows it runs Luna's Linux build through WSL.</p>
<ol>
<li><b>Process</b> → <b>Detector</b>: pick <b>Timepix3</b> or
<b>Timepix4</b>.</li>
<li><b>Advanced</b> → <b>Luna installation</b> → <b>Browse...</b> to the Luna
folder for that detector → <b>Check install</b>. A one-time step.</li>
<li><b>Process</b> → <b>Add folders...</b> → <b>Run queue</b>.</li>
<li>Double-click a finished row to open its <code>.hdf5</code> on
<b>Inspect HDF5</b>.</li>
</ol>
<p>Left alone, every queued file is processed with exactly</p>
<pre>tpx3dump process -i NAME.tpx3 -o NAME.hdf5</pre>
<p>or, on Timepix4,</p>
<pre>tpx4dump process -i NAME.tpx4 -o NAME.hdf5</pre>
<p>with the output written beside the input. Anything else you set turns the
<b>Advanced flags</b> button on the Process tab yellow, so a non-default run is
never a surprise. Your raw files are never moved, renamed or modified.</p>
<h3>Paths, the Explorer way</h3>
<ul>
<li>On Windows every <b>Browse...</b> opens Explorer's own dialog: Alt+D jumps
to its address bar, paste a path there, Ctrl+A selects all, Quick Access and
recent folders are all there.</li>
<li>Every path field takes a pasted path; the quotes Explorer's <i>Copy as
path</i> adds are dropped. A file or folder dragged in from Explorer lands as
its path.</li>
<li>On Inspect HDF5, paste or drop a file into <b>HDF5 file</b> and it opens
(Enter opens a typed path).</li>
</ul>

<a name="detectors"></a><h2>Timepix3 and Timepix4</h2>
<p>The <b>Detector</b> switch at the top of the Process tab picks which Luna
converter runs and which raw files a folder scan queues.</p>
<ul>
<li><b>Separate setups.</b> Each detector keeps its own Luna folder and its
own batch folders, so switching swaps the whole setup; switch back and the
other one is as you left it. The switch is locked while a run is going.</li>
<li><b>Flags.</b> The converters share most options. The Advanced tab shows
only the current detector's flags, and only those are passed; a value set for
the other one is kept for when you switch back. See <a href="#flags">Luna
flags</a>, whose tables say which detector each flag is for.</li>
<li><b>Same file layout, different units.</b> Both write
<code>PixelHits</code>, <code>Clusters</code> and
<code>ExposureTimeBoundaries</code> with the same columns, but Timepix4 counts
ToA <i>and</i> ToT in 1e-16 s where Timepix3 counts ToA in 1e-13 s and ToT in
ns. The Inspect tab tells the two apart by the file's ToT values and reads
each in its own units; see <a href="#file">What is in the file</a>.</li>
<li><b>No TDC on Timepix4.</b> <code>tpx4dump</code> writes no
<code>TDCEvents</code> and has no <code>--tof-tdc-reference</code>, so the TDC
columns, the ToF column and the TDC plot are Timepix3 only.</li>
<li><b>Luna folder.</b> ASI's Timepix4 archive unpacks into a folder holding a
folder of the same name; picking either works, as does the <code>bin</code>
folder itself.</li>
<li><b>A noisy log is normal.</b> <code>tpx4dump</code> logs an
<code>[ERROR] ... Packet is ignored</code> line for every packet it drops —
hundreds of thousands for one file. The file is still written. The log shows
the first 20 lines of each kind and counts the rest, with one summary line per
kind when the file is done, so the window stays responsive.</li>
</ul>

<a name="process"></a><h2>Process tab</h2>
<p>The everyday job: add input, press Run, watch the log.</p>
<ul>
<li><b>Detector</b>: <b>Timepix3</b> or <b>Timepix4</b>; see
<a href="#detectors">Timepix3 and Timepix4</a>.</li>
<li><b>Status line</b>: whether the detector's converter can run here, and how
(native or WSL). <b>Set up Luna...</b> appears until it can.</li>
<li><b>Advanced flags</b>: grey while every file runs as the plain command,
yellow with a count as soon as anything differs: output placement, renaming,
overwriting, each flag passed. Click it for the full list, one setting per
row.</li>
<li><b>Wrapper options</b> (light green, beside it): shown only while this
GUI's own post-processing is on — TDC columns or the timewalk correction.
These run after Luna and never change the Luna command, so they are counted
here rather than in Advanced flags. Click it for the list.</li>
<li><b>Add folders...</b> queues every <code>.tpx3</code> (or, on Timepix4,
<code>.tpx4</code>) under one or more folders;
<b>Search subfolders</b> reaches the files inside each measurement's
<code>raw</code> folder. <b>Browse...</b> opens Explorer's own folder picker
(Alt+D for its address bar). Or paste several paths, one per line, or drag
folders in from Explorer; <i>Copy as path</i> works as-is.</li>
<li><b>Rescan</b>: re-reads the batch folders: queues new files, drops rows
whose input has gone, re-reads the metadata. During a live campaign,
<i>Rescan, Run, repeat</i> is the whole routine. Only run a measurement once it
has finished.</li>
<li><b>Clear</b> empties the queue and the folder list.</li>
<li><b>Folders to process</b>: the batch folders with their file counts,
remembered between sessions.</li>
<li><b>Files found</b>: each input with the output it will get and its status
(<i>queued, running, done, failed, skipped, CLASH</i>). Tick <b>Overwrite</b> on
a row to redo a file whose output exists; the box in the column header ticks
them all. Double-click a row to inspect its output. Hover a failed row for
why it failed and what to change.</li>
<li><b>Rerun failed (N)</b>, above the Overwrite column, turns yellow once a
file has failed. It lists the causes with what to change, warns if a cause
still holds with the current settings (e.g. an output name still over 255
characters), ticks <b>Overwrite</b> where a failed run left a partial
<code>.hdf5</code>, and then runs only the failed files.</li>
<li><b>Run queue</b> processes the files one at a time; <b>Stop</b> ends the
current file and the rest.</li>
<li><b>Log</b>: the converter's own output, kept whole for the entire
session. A line printed over and over (Timepix4 prints one per dropped packet)
is shown 20 times per file and then counted. A failed file gets a
<code>FAILED</code> line with its cause and what to change, and the end of
the run sums the failures up by cause. <b>Save log...</b> writes it all to a
text file.</li>
</ul>
<p>On Windows, before a run the GUI checks that WSL can see the drives
involved, and offers to mount one that it cannot (typically a USB disk).</p>

<a name="advanced"></a><h2>Advanced tab</h2>
<p>Everything here is optional.</p>
<h3>Luna installation</h3>
<p><b>Folder</b> is the Luna install root or its <code>bin</code> folder, for
the detector selected on the Process tab; each detector remembers its own.
<b>Check install</b> re-detects the backend and prints the converter's
<code>--version</code> and <code>process --help</code> into the log — the
authoritative flag list for your Luna version.</p>
<h3>Output</h3>
<ul>
<li><b>Next to the input file</b> (default) — each <code>.hdf5</code> beside
its raw file.</li>
<li><b>Output folder (flat)</b>: every <code>.hdf5</code> in one folder.</li>
<li><b>Output folder (mirror tree)</b>: the campaign's folder structure
rebuilt under the output folder, without the <code>raw</code> level.</li>
<li><b>Name template</b>: how outputs are named; see
<a href="#naming">Name templates</a>. <b>Presets...</b> offers common ones.</li>
<li><b>Luna comment</b>: an optional note for this run, e.g. what was changed
in Luna (<code>--eps-t 300 ns</code>). Anything typed here is appended to the
end of every output name, and the line below the box shows the template it
turns into. Left empty, nothing is added. It is not saved between sessions.</li>
<li><b>Skip files whose output already exists</b> (on by default) — untick to
overwrite everything, or tick <b>Overwrite</b> on single rows instead.</li>
</ul>
<h3>tpx3dump / tpx4dump flags</h3>
<p>Every option of the current detector's <code>process</code> command, with a
note on each; see <a href="#flags">Luna flags</a>. Blank means the
converter's own default. <b>extra arguments</b> is passed verbatim after them,
for anything a newer Luna adds.</p>
<h3>Wrapper options</h3>
<p>Not Luna flags: once the converter finishes a file, this GUI reopens it and
writes extra datasets into it itself.</p>
<ul>
<li><b>Add TDC columns to each output .hdf5</b> (Timepix3 only): tags every
hit and cluster with the TDC edge it follows; see <a href="#tdc">TDC</a>.
Hidden on Timepix4, whose files carry no TDC edges.</li>
<li><b>Timewalk-correct each output .hdf5</b>: measures the file's timewalk
curve from its own clusters and writes corrected cluster times; see
<a href="#timewalk">Timewalk correction</a>. <b>ctot cut</b> picks the
clusters that build the curve; <b>also every pixel hit</b> writes a corrected
time per hit too, at the cost of one more pass over all hits.</li>
</ul>
<h3>Buttons</h3>
<ul>
<li><b>Preview commands</b>: prints the exact command for every queued file,
without running anything.</li>
<li><b>Export .sh</b>: writes a shell script that runs the queue on a Linux
machine, with the input and output roots as variables to edit there.</li>
<li><b>Reset to defaults</b>: everything on this tab back to the plain run;
the Luna folder and the queue are kept.</li>
</ul>

<a name="naming"></a><h2>Name templates</h2>
<p>The default <code>{escape(DEFAULT_TEMPLATE)}</code> gives, for example,
<code>2026-08-07_12-52-45_DCR-0V-gain_fCqk_000000.hdf5</code>. The values come
from <code>measurement_metadata.json</code> and <code>comment.txt</code> in the
measurement folder.</p>
{ph}
<p>A placeholder with no value drops out and the separators collapse. If two
inputs would get the same name, both rows are marked <b>CLASH</b> and skipped
rather than one overwriting the other — keep <code>{{time}}</code> or
<code>{{stem}}</code> in the template to avoid it.</p>
<p>A <b>Luna comment</b> typed on the Advanced tab is added as
<code>_{{luna_comment}}</code> on the end: with <code>--eps-t 300 ns</code> the
default becomes <code>{{date}}_{{time}}_{{comment}}_{{stem}}_{{luna_comment}}</code>,
giving <code>2026-08-07_12-52-45_DCR-0V-gain_fCqk_000000_eps-t-300-ns.hdf5</code>.
Characters a file name cannot hold become <code>-</code>, and leading dashes
are dropped. A template that already contains <code>{{luna_comment}}</code>
puts it there instead of on the end.</p>

<a name="flags"></a><h2>Luna flags</h2>
<p>Taken from <code>tpx3dump process --help</code> and <code>tpx4dump process
--help</code>; <b>For</b> says which converter accepts each, and only those are
shown on the Advanced tab. Blank fields pass nothing, so the converter uses the
default shown — the same for both where both have the flag. Times carry their unit
(<code>s ms us ns ps fs</code>): write <code>200ns</code>, not
<code>200</code>; a bare number is refused before anything runs.</p>
{_flags_html(pal)}

<a name="inspect"></a><h2>Inspect HDF5 tab</h2>
<p>Look inside a result. <b>Browse...</b> to a file, or <b>Use selected
output</b> for the row selected on the Process tab, then <b>Open</b>.</p>
<ul>
<li><b>Datasets</b>: every dataset with its shape, type, chunking and
compression.</li>
<li><b>View rows...</b>, or double-click a dataset — its rows in a window of
their own. It scrolls through the whole dataset, however large: only the rows
on screen are read. <b>Row</b>, <b>First</b> and <b>Last</b> jump anywhere; row
numbers count from 0, as h5py does. Hover a column header for its type and
unit; Ctrl+C copies the selected cells.</li>
<li><b>Summary</b> (bottom) — counts, fields, ToA and pixel ranges, whether
ToF was computed, mean cluster size, the TDC edges and their period.</li>
<li><b>TDC reference</b>: which edge starts the clock for the TDC columns and
the TDC plot; the same setting as on the Advanced tab.</li>
<li><b>Add TDC columns to this file</b>: writes them now, for this file.</li>
<li><b>Preview frame</b>: the first rows of the data joined with their TDC
columns.</li>
<li><b>Timewalk ctot cut</b>, <b>also every pixel hit</b>: the same settings
as on the Advanced tab. <b>Add timewalk columns to this file</b> writes them
now, for this file.</li>
</ul>
<p>The seven plots read the file in slices, so large files are fine, and each
opens in its own window for side-by-side comparison.</p>
{plots}

<a name="file"></a><h2>What is in the file</h2>
<ul>
<li><code>PixelHits</code>: one row per pixel hit.</li>
<li><code>Clusters</code>: one row per cluster of hits.</li>
<li><code>TDCEvents</code>: every TDC edge, repeated once per chip
(Timepix3 only).</li>
<li><code>ExposureTimeBoundaries</code>: the frame boundaries of the
acquisition.</li>
<li><code>PixelHitsTDC</code>, <code>ClustersTDC</code>: the TDC columns, if
this GUI wrote them.</li>
<li><code>TimewalkCurve</code>: the timewalk curve, if this GUI corrected
the file. The corrected times themselves are the last column of the tables:
<code>Clusters/ctoa_tw</code>, and <code>PixelHits/toa_tw</code> with
<b>also every pixel hit</b>.</li>
</ul>
<p>Within one file all timestamps count ticks of one clock, so subtracting
them is meaningful. The units differ by detector, per Luna's own unit-conversion
example: on <b>Timepix3</b>, <code>toa</code>, <code>ctoa</code> and the TDC
<code>timestamp</code> count 1e-13 s (100 fs) and ToT is in ns, in 25 ns steps;
on <b>Timepix4</b>, ToA <i>and</i> ToT count 1e-16 s (100 as), ToT in steps of
0.195 ns. The Inspect summary names the detector it judged a file to be from,
and the plots and row viewer use that detector's units.</p>
{units}

<a name="tdc"></a><h2>TDC</h2>
<p><i>Timepix3 only: <code>tpx4dump</code> writes no TDC data.</i></p>
<p><code>TDCEvents</code> holds every TDC edge <code>tpx3dump</code> saw:
<code>tdc_type</code> (1 TDC1Rising, 2 TDC1Falling, 3 TDC2Rising,
4 TDC2Falling), <code>trigger_count</code> and <code>timestamp</code>. Every
chip repeats the packet — a quad stores each edge four times — so everything
here deduplicates first; the summary shows both counts.</p>
<p><b>Add TDC columns</b> tags each hit and cluster with the last reference edge
before it and writes the result to <code>/PixelHitsTDC</code> and
<code>/ClustersTDC</code>, row-aligned with <code>PixelHits</code> and
<code>Clusters</code>: <code>tdc</code> (the edge's timestamp),
<code>tdc_dt</code> (time since it), <code>tdc_index</code>,
<code>tdc_trigger</code> and <code>tdc_type</code>. Rows before the first edge
get -1. The original datasets are never rewritten, and the GUI refuses to
replace TDC columns it did not write.</p>
<p>This is independent of <code>--tof-tdc-reference</code>, which makes
<code>tpx3dump</code> fill <code>PixelHits/tof</code> during processing. Where
both use the same edge they agree exactly; the TDC columns can be recomputed
against another edge without reprocessing the <code>.tpx3</code>. <b>Any
edge</b> tags from the latest edge of any type.</p>

<a name="timewalk"></a><h2>Timewalk correction</h2>
<p>A small signal crosses the threshold later than a large one, so a pixel's
ToA depends on its own ToT: tens of ns, up to ~100 ns, for the faintest hits.
No TDC or test pulses are needed to correct it. All pixels of one cluster fired
at the same moment, and the pixel with the largest ToT (<code>ctot</code>,
whose ToA is <code>ctoa</code>) walks least, so it serves as the clock.</p>
<ol>
<li>For every hit of a cluster with <code>ctot</code> &ge; the <b>ctot
cut</b>, take <code>toa - ctoa</code> (the reference pixel itself is left
out).</li>
<li>Per 25 ns ToT bin, find the peak of that delay (an iterated 3-sigma
truncated mean, robust against pile-up background). That is the
<b>curve</b>, delay(ToT); its width is the jitter. The first 50 M hits are
used, which takes ~10 s.</li>
<li>Add <code>ctoa_tw = ctoa - delay(ctot)</code> as the last column of
<code>Clusters</code>, and with <b>also every pixel hit</b>
<code>toa_tw = toa - delay(tot)</code> as the last column of
<code>PixelHits</code>, in the same ticks as the source. The curve goes to
<code>/TimewalkCurve</code> (<code>tot_ns</code>, <code>delay_ns</code>,
<code>sigma_ns</code>, <code>n</code>) with the settings as attributes.</li>
</ol>
<p>Correcting each pixel on its own means the reference's own walk drops out
of time differences. The curve is relative to the high-ToT limit; the
constant offset to the true arrival time needs an external reference and does
not matter for time differences between photons.</p>
<p>A focused spot is not needed: dark counts across the whole sensor work as
well, as long as clusters have more than one pixel. The curve depends on the
threshold and other settings and varies a little across the chip (a few ns at
mid ToT), so it is measured per file.</p>
<p>An HDF5 table cannot grow a column in place, so the first correction of a
file rewrites it once: into a temporary file beside it, swapped in only when
complete, so it needs free space for one more copy. Luna's columns, chunking
and attributes are kept as they were. Later runs update the column in place;
a column added earlier is always updated too, so it never goes stale. The GUI
refuses to touch a <code>ctoa_tw</code>/<code>toa_tw</code> column it did not
add.</p>
<p>Not the same as Luna's own <code>--calculate-timewalk-statistics</code> /
<code>apply-timewalk-correction</code> (Timepix3 only), which averages the
delay without rejecting background and rewrites <code>toa</code> in
place.</p>

<a name="dcr"></a><h2>Dark count rate</h2>
<p>The <b>DCR</b> page beside the summary on the Inspect HDF5 tab. Open a
file and press <b>Compute DCR</b>: one pass over every pixel hit and cluster
(about 20 s for a 6 GB file) counts them per pixel and per frame. The time
base and the noisy cut can be changed afterwards without reading the file
again.</p>
<p><b>Time base</b> — what the counts are divided by. All four are computed
and listed; the one picked is used.</p>
<ul>
<li><b>Frames, live time from ToA</b> (default): first to last hit minus the
gaps between frames. ToA is sorted, so with N frames the N−1 widest ToA gaps
are the dead time between them; N is the number of entries in
<code>ExposureTimeBoundaries</code>. Needs no metadata, and matches frames ×
exposure to 0.01 % on 0.495 s frames.</li>
<li><b>Frames × exposure</b>: <code>NumberOfFrames</code> ×
<code>ExposureTime</code> from <code>measurement_metadata.json</code>, found
in the folders above the file.</li>
<li><b>ToA span</b>: first to last hit, the gaps between frames counted as
live (~1 % long for 0.495 s frames every 0.5 s).</li>
<li><b>Wall clock</b>: <code>StartDateTime</code> to
<code>StopDateTime</code>, start-up and readout included: an upper bound.</li>
</ul>
<p><code>ExposureTimeBoundaries</code> holds row indices, not times, and they
do not always match <code>PixelHits</code>; only their count is used. A base
that is unavailable falls back to the next one, and the report says so.</p>
<p><b>Noisy</b> pixels have more than k × the median hit count of the pixels
that counted; <b>silent</b> ones counted nothing. The <b>clean</b> rates leave
the noisy pixels' hits out, and both noisy and silent pixels out of the area;
clean cluster rates leave out clusters centred on a noisy pixel. Rates per
area use 55 µm pixels.</p>
<p>Plots: DCR maps for pixels and clusters, a log-log histogram of the
per-pixel DCR with the median and noisy cut marked, and <b>Rate vs time</b>:
the median pixel's DCR in Hz, frame by frame (or in 100 time bins for a
single frame), for hits and clusters in two panels. Counts per pixel per
frame are small integers, so the median is interpolated within the middle
count rather than moving in whole-count steps.
<b>Export CSV...</b> writes one row per pixel.</p>

<a name="themes"></a><h2>Themes and preferences</h2>
<p><b>View</b> → <b>Theme</b> sets the colours of the window and of the
plots. <b>Luna light</b> (the default) and <b>Luna dark</b> are the app's own;
the other ten come from daplis-rtp. Cyberpunk, Midnight, Night wave, Blueprint
and High contrast are dark; Daylight, Komorebi, Earth, Solarized and Daplis
(publication) are light. Every theme keeps the same layout, the same fonts on
every tab, and the meaning of the yellow <b>Advanced flags</b> and green
wrapper-options buttons.</p>
<p><b>View</b> → <b>Preferences...</b> (Ctrl+,) changes any single
colour: the window's (background, panels, input fields, buttons, borders,
three shades of text, the accent), the three status colours, the plots'
(figure and plot background, ticks and labels, axes frame, grid, reference
lines) and five trace colours. It also sets the interface and plot font sizes,
the marker size, the grid, and a glow under the traces (with
<code>mplcyberpunk</code> installed). Every change applies at once to the
window; plots take the theme in force when they are opened. Picking a theme
again clears your changes to it; <b>Reset to defaults</b> clears everything.
The window can stay open beside the main one.</p>
<p>The Luna themes draw their plots with the komorebi_mpl styles
<code>sci_pure</code> and <code>night_wave</code>, as before, with any
change made in Preferences on top. On Windows every window gets a dark title
bar, whatever the theme.</p>

<a name="trouble"></a><h2>Troubleshooting</h2>
{trouble}

<a name="about"></a><h2>Settings and about</h2>
<p>{escape(APP_NAME)}, version {escape(__version__)}. F1 opens this window
from anywhere in the app.</p>
<p>Settings — detector, the Luna folder and batch folders of each detector,
template, flags, TDC reference, theme and preferences — are saved on
exit to <code>{escape(str(CONFIG_PATH))}</code>. The <b>View</b> menu holds the
theme and Preferences (see
<a href="#themes">Themes and preferences</a>).</p>
<p>This program only wraps Luna: it runs your unmodified
<code>tpx3dump</code> or <code>tpx4dump</code> through its command line and
contains no part of it.</p>
"""


def style_sheet(pal, mono, size=10) -> str:
    """CSS for the rich text, which the app stylesheet does not reach."""
    # Sized and spaced for reading rather than scanning: a body a point above
    # the interface font with open line spacing, section titles in the
    # heading colour, bold terms in the text colour so they stand out from
    # the prose around them. At the default 10 pt: 11 / 15 / 12 / 10 pt.
    return f"""
        body {{ color: {pal['text']}; font-size: {size + 1}pt; }}
        p {{ line-height: 135%; margin-top: 4px; margin-bottom: 8px; }}
        li {{ line-height: 135%; margin-bottom: 4px; }}
        ul, ol {{ margin-top: 2px; margin-bottom: 8px; }}
        h2 {{ font-size: {size + 5}pt; font-weight: 700; color: {pal['heading']};
              margin-top: 28px; margin-bottom: 6px; }}
        h2.first {{ margin-top: 0; }}
        h3 {{ font-size: {size + 2}pt; font-weight: 700; color: {pal['text']};
              margin-top: 18px; margin-bottom: 4px; }}
        b {{ color: {pal['text']}; font-weight: 700; }}
        a {{ color: {pal['heading']}; text-decoration: none; }}
        code {{ font-family: "{mono}"; font-size: {size}pt; color: {pal['text']};
                background-color: {pal['surface_container_high']}; }}
        pre {{ font-family: "{mono}"; font-size: {size}pt;
               background-color: {pal['surface_container_high']}; }}
        th {{ color: {pal['text_muted']}; font-weight: 700; }}
        td {{ line-height: 130%; }}
        .muted {{ color: {pal['text_muted']}; }}
        .faint {{ color: {pal['text_faint']}; font-size: {size}pt; }}
    """


class HelpWindow(QDialog):
    """Topic list on the left, the page on the right, a find box on top."""

    def __init__(self, pal, mono, parent=None, size=10):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME + " — Help")
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.e_find = QLineEdit()
        self.e_find.setPlaceholderText("Search the guide... (Enter for next)")
        self.e_find.setClearButtonEnabled(True)
        self.e_find.returnPressed.connect(self.find_next)
        self.lbl_find = QLabel("")
        self.lbl_find.setProperty("faint", True)
        lay.addWidget(row("Find:", self.e_find, self.lbl_find))

        body = QHBoxLayout()
        body.setSpacing(8)
        self.nav = QListWidget()
        self.nav.setProperty("nav", True)
        self.nav.addItems([title for _a, title in SECTIONS])
        self.nav.setFixedWidth(210)
        self.nav.currentRowChanged.connect(
            lambda r: r >= 0 and self.view.scrollToAnchor(SECTIONS[r][0]))
        body.addWidget(self.nav)

        self.view = QTextBrowser()
        # The text wraps to the width, so a horizontal bar is only ever the
        # few pixels the vertical bar takes when it appears.
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Links are handled here: #anchors scroll the page and select the
        # topic, web links go to the browser.
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        body.addWidget(self.view, 1)
        lay.addLayout(body, 1)

        self.mono = mono
        self.set_palette(pal, size)

    def set_palette(self, pal, size=10):
        """Re-render in new colours and size, keeping the reader's place."""
        bar = self.view.verticalScrollBar()
        pos = bar.value()
        self.view.document().setDefaultStyleSheet(
            style_sheet(pal, self.mono, size))
        self.view.setHtml(help_html(pal))
        bar.setValue(pos)

    def show_section(self, anchor):
        for r, (a, _t) in enumerate(SECTIONS):
            if a == anchor:
                self.nav.setCurrentRow(r)
                self.view.scrollToAnchor(anchor)

    def _link(self, url):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
        elif url.fragment():
            self.show_section(url.fragment())

    def find_next(self):
        text = self.e_find.text().strip()
        if not text:
            return
        if not self.view.find(text):
            # Wrap around: back to the top and try once more.
            cur = self.view.textCursor()
            cur.movePosition(cur.MoveOperation.Start)
            self.view.setTextCursor(cur)
            if not self.view.find(text):
                self.lbl_find.setText("not found")
                return
            self.lbl_find.setText("wrapped to the top")
            return
        self.lbl_find.setText("")
