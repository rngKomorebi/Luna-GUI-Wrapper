# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 16-11-2026

### Added

- Timepix4: a **Detector** switch (Timepix3 | Timepix4) on the Process tab
  runs Luna's `tpx4dump` over `.tpx4` files the same way as `tpx3dump` over
  `.tpx3`. Each detector keeps its own Luna folder and batch folders. Only
  the current converter's flags are shown and passed; `tpx4dump`'s
  `--input-format`, `--max-delay` and `--enable-gray-decoding` are added.
  The TDC columns option is hidden for Timepix4, which records no TDC edges.
  As with Timepix3, Luna is not bundled: the GUI runs the user's own copy.
- Inspect HDF5 tells Timepix3 from Timepix4 files by their ToT values and
  uses each one's units (Timepix4 counts ToA and ToT in 1e-16 s) in the
  summary, the ToT plots and the row viewer's column tooltips.
- The Luna folder may be the archive's outer folder: the converter is also
  looked for one level down, as ASI's Timepix4 archive nests a same-named
  folder.
- Failed files are logged: a `FAILED` line names the cause and what to change
  (output name too long, file locked, disk full, drive not visible to WSL, a
  rejected flag, a crash with its message...). The row shows the cause, and
  the end of the run sums the failures up by cause.
- **Rerun failed (N)** above the Overwrite column, yellow once anything has
  failed. It explains each cause and warns if it still holds with the current
  settings, ticks Overwrite where a partial `.hdf5` was left behind, and runs
  only the failed files.
- **Save log...** next to Clear log.

### Changed

- Renamed **Luna Tpx3 GUI** to **Luna GUI Wrapper**, now that it handles
  Timepix4 too: repository `Luna-GUI-Wrapper`, package `luna_gui_wrapper`,
  pip name and console script `luna-gui-wrapper`. Settings are now saved to
  `~/.luna_gui_wrapper.json`; the old `~/.luna_tpx3_gui_qt.json` is still
  read when the new file does not exist yet. The installers remove the old
  launcher / shortcut, and `run_gui.bat` / `run_gui.sh` still find a venv
  built under the old name. HDF5 files keep the `luna_tpx3_gui.tdc_columns`
  stamp, so TDC columns written before the rename are still recognised.
- README cut down to an introduction, a short install and run section and a
  Timepix3 / Timepix4 table. The detail moved into the Sphinx docs: Overview,
  Installation, Usage, Inspect HDF5, TDC, Troubleshooting. Screenshots
  retaken.
- Name templates: the placeholder list, the Help table and the presets show
  only `{stem}` `{measurement}` `{campaign}` `{date}` `{time}` `{datetime}`
  `{comment}`. The metadata placeholders (`{bias}`, `{duration}`,
  `{exposure}`, `{polarity}`, `{size}`, `{thr_coarse}` and the rest) are no
  longer listed, but a saved template that uses them still works.
- The app icon is now `icon/icon.png` at 512 px (was a 1024 px, 740 KB
  `screen.png`); `install-linux.sh` installs it under `hicolor/512x512` and
  removes the old 1024 px copy.

### Fixed

- The log kept only its last 20,000 lines, so a long batch lost its start (a
  560-file Timepix4 run kept files 312-560 only). It is now kept whole.
- The count of hidden repeated lines cut off before the error kind
  (`ToAArithmet...`); it now drops Luna's source-location prefix and shows
  the message.
- The window froze while processing a Timepix4 file. `tpx4dump` prints one
  error line per dropped packet (212,706 for one 84 MB file), and the log took
  them one redraw at a time, until the event loop starved, the output pipe
  filled and the converter blocked on it. Converter output is now written to
  the log in batches, and after the first 20 lines of one kind the rest are
  counted and summed up when the file is done. Replaying that file's output at
  10x its real rate, the window never paused longer than 29 ms.
- Timepix4 hitmaps showed an all-dark chip. One corner pixel held a third of
  the hits (firing at the laser's 190 kHz) and set a linear colour scale that
  drew everything else, the laser spot included, as zero; the image was also
  square, so 64 columns past the 448-wide chip showed as empty. Hitmaps are
  now sized to the data's own width and height, and when the hottest pixel is
  more than 5x the 99.9th percentile of hit pixels the colour scale stops
  there, with an arrow on the colour bar and the clipped pixels named in the
  title. Hitmaps without such outliers are unchanged.

## [0.2.0] - 01-11-2026

### Added

- Inspect HDF5 tab: double-click a dataset (or **View rows...**) to scroll
  through its rows in a window of their own. Only the rows on screen are read,
  so even a 300-million-row dataset opens instantly; jump to any row, first or
  last; column headers give type and unit; Ctrl+C copies the selection.
- Advanced tab: a control for every `tpx3dump process` option, including the
  ones that previously needed *extra arguments* (`--layout`, `--n-phases`,
  `--clustering-algorithm`, `--kuttruff-buffer-size`, `--discard-pixel-data`,
  the compression options, `--hdf5-chunk-size`, the timewalk options and
  `--ctot-cut`). Each has a one-line note on what it does and a tooltip with
  the details and `tpx3dump`'s default.
- Values `tpx3dump` would reject (a time without its unit, a non-number) are
  caught before Run, Preview or Export .sh.
- Help menu above the tabs (F1): a Help window explaining every tab, option
  and flag, plus name templates, the file's columns and units, TDC and
  troubleshooting, with a topic list and a Find box. The flag reference is
  generated from the same table as the Advanced tab, so the two cannot
  disagree. **All flags explained...** on the Advanced tab jumps straight to
  it.
- Path fields (Luna folder, output folder, HDF5 file, timewalk file) drop the
  quotes of a pasted *Copy as path* and accept a file or folder dragged in
  from Explorer; the Add folders paste box takes dragged folders too. A path
  pasted or dropped into **HDF5 file** opens straight away.

### Changed

- Process tab: the amber "Advanced: ..." line is now an **Advanced flags**
  button -- grey for a plain run, yellow with a count once anything deviates
  -- that lists every setting in effect, one per row.
- Process tab: **Add files...** and **Remove** are gone; **Clear all** is now
  **Clear**. The *Measurement folder* column is gone from **Files found**
  (hover a row for the full input and output paths).
- The Light/Dark buttons moved into a **View** menu, left of **Help**.
- On Windows the file dialogs are Explorer's own (Alt+D, paste into the
  address bar, Quick Access). They follow Windows' light/dark setting rather
  than the app's.
- The flags are defined once, in `functions/flags.py`, which drives the
  widgets, settings, summary line, reset and command line alike.

### Fixed

- README examples passed `--eps-t 100`; `tpx3dump` expects a unit, e.g.
  `200ns`.
- A code comment claimed that without `--tof-tdc-reference` tpx3dump uses a
  default edge; it computes no ToF at all.

## [0.1.0] - 30-09-2026

First public release.

Luna is not included: the GUI drives the user's own, unmodified `tpx3dump`.
There is deliberately no bundled executable on any platform, so the GUI cannot
be passed on with the Luna binaries packed inside; it runs from source on both
Linux and Windows.

### Added

- Process tab: queue `.tpx3` files or whole folders (searched recursively),
  run `tpx3dump process` over the batch, stream its output into the log.
- Backend detection: native `tpx3dump` on Linux, the Linux build through WSL
  on Windows, with Windows -> `/mnt/...` path translation and a pre-run check
  (and offer to mount) for drives WSL cannot see.
- Advanced tab: output placement (beside / flat / mirrored tree), name
  templates built from `measurement_metadata.json`, `tpx3dump` flags, command
  preview and `.sh` export.
- Inspect HDF5 tab: dataset summary, TDC edge statistics, six plots, and the
  TDC columns (`/PixelHitsTDC`, `/ClustersTDC`) written beside the originals.
- Qt-free Python API: `read_tdcs`, `add_tdc_columns`, `read_with_tdc`.
- Light and dark themes; plot styles from `komorebi_mpl` when installed.
- Linux menu launcher and Windows Desktop shortcut installers.
  `install-linux.sh` builds the private venv (from `requirements.txt`) and the
  Desktop icon by default; `--no-venv` and `--no-desktop-icon` opt out.
  `install-windows.ps1` likewise builds a venv from `requirements.txt`, at
  `%USERPROFILE%\venvs\luna-tpx3-gui` (`-VenvName` renames it, `-NoVenv`
  skips it), and `run_gui.bat` uses that venv too.
- Packaging: `pyproject.toml` with the `luna-tpx3-gui` console script and the
  `analysis` / `dev` extras; `python -m luna_tpx3_gui` also starts the app.
- pytest suite for the Qt-free core, ruff via pre-commit, and GitHub Actions
  for the tests (Ubuntu and Windows, Python 3.10-3.13) and the Sphinx docs.
- README: a prominent "Luna is not included" note with a who-does-what table,
  and worked examples (whole campaigns, many folders at once, Rescan during a
  live campaign, flat / mirrored output, batch-wide flags, selective
  overwrite, `.sh` export, TDC columns).
- Advanced tab: a Browse button for the output folder.

### Changed

- Code split from the single `luna_tpx3_gui_qt.py` into the
  `src/luna_tpx3_gui` package (`functions/` Qt-free core, `gui/` Qt app).
- Advanced tab re-laid out: it scrolls instead of squeezing its fields when
  the window is short, the flags sit in an aligned two-column grid, and the
  action buttons stay pinned below the options. The intro showing the default
  `tpx3dump` command is larger, with the command set off as a code block.
