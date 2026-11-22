# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.2] - 22-11-2026

### Changed

- `--eps-s` defaults to **2** in this GUI instead of 2.5 (Luna's own default
  is 1), since Luna's `--eps-s` is a whole number of pixels.
- The `--eps-s` field takes positive whole numbers only (1, 2, 3, ...):
  anything else cannot be typed in, and a run refuses a value like `0` or
  `2.5` before it starts. A saved value that is not a positive whole number
  (e.g. `2.5`) is dropped and the default used instead.

## [0.6.1] - 22-11-2026

### Added

- **Luna comment** box under the name template on the Advanced tab: text typed
  there (e.g. `--eps-t 300 ns`) is appended to every output name as
  `_{luna_comment}`, so the default becomes
  `{date}_{time}_{comment}_{stem}_{luna_comment}`. A line under the box shows
  the resulting template; empty adds nothing. It counts towards the Advanced
  flags summary and is not saved between sessions.

### Changed

- The Advanced tab's boxes are told apart by colour: the Luna flags box has a
  faint yellow wash and a yellow stripe on its left, like the Process tab's
  **Advanced flags** button, and the Wrapper options box the same in the
  **Wrapper options** button's green. Every theme gets both, worked out from
  its own warning and OK colours.
- `--eps-s` and `--eps-t` default to **2.5** and **300ns** in this GUI
  (Luna's own are 1 and 100ns). The empty field shows the value in grey, and
  a run passes it unless another value is typed in. Tooltips and the flag
  guide name both defaults.
- README, Install: besides `git clone`, the GUI can be had by downloading the
  latest release's source archive and unpacking it; the install steps that
  follow are the same.

### Fixed

- README told Linux users to run `./install-linux.sh`, which fails with
  *Permission denied* in a fresh clone or an unpacked release, because the
  script is not stored as executable. It now says `bash install-linux.sh`.
- The per-file **Overwrite** boxes in the queue are drawn like the header's
  box, visible ticked and unticked, and a click anywhere in the cell toggles
  one. Quick repeated clicks, on a row or the header, no longer cancel each
  other out, which had made the box look stuck.

## [0.6.0] - 18-11-2026

### Added

- Themes, ported from daplis-rtp. **View → Theme** offers twelve: **Luna
  light** (the default) and **Luna dark**, which are the previous light and
  dark palettes unchanged, plus daplis-rtp's ten: Cyberpunk, Midnight, Night
  wave, Blueprint, High contrast, Daylight, Komorebi, Earth, Solarized and
  Daplis (publication). Every theme is drawn with the app's own stylesheet, so
  the layout stays the same, and the yellow Advanced-flags and green
  wrapper-options buttons keep their meaning.
- **View → Preferences...** (Ctrl+,), daplis-rtp's two-column window: every
  window colour (background, panels, input fields, buttons, borders, three
  text shades, accent), the OK / warning / error colours, the plot colours
  (figure and plot background, ticks and labels, axes frame, grid, reference
  lines), five trace colours, the interface and plot font sizes, the marker
  size, grid and glow. Not modal: changes apply to the window as they are
  made, and to plots opened afterwards.
- A dark title bar on every window on Windows 10 (20H1+) and 11, whatever the
  theme, as in daplis-rtp.
- Plots follow the theme. The Luna themes keep their komorebi_mpl styles
  (`sci_pure`, `night_wave`), with any Preferences change laid on top; the
  other themes draw in their own colours with inward ticks on all four sides.
  Hitmaps never get a grid.
- Optional dependency `mplcyberpunk` (the glow), in `requirements.txt` and
  the new `themes` extra.
- A Help section, *Themes and preferences*; tests for the themes and the
  title bar.

### Changed

- The theme, colour changes and sizes are saved with the other
  settings on exit. A config saved by an earlier version opens on the same
  look (`light` → Luna light, `dark` → Luna dark).
- The theme is applied before the window is built. As a result the
  *Folders to process* and *Files found* tables on the Process tab now start
  level, as intended; before, the left one sat about 11 px higher.
- One look across all three tabs. Spin boxes (the timewalk ctot cut, the DCR
  noisy-pixel cut, Preferences) are now drawn like the other input fields,
  rounded and in the field colour; before, they were the one field left
  flat, square and darker. The log, the file summary and the DCR report are
  now at the interface font size instead of a point below it, which had
  made the Inspect tab, where those boxes take most of the room, look
  fainter than the others.

## [0.5.0] - 18-11-2026

### Added

- Dark count rate on the Inspect HDF5 tab. The panel under the plot buttons
  is now two pages, **Summary** and **DCR**. **Compute DCR** reads every pixel
  hit and cluster once and reports the rate per pixel, per cluster and per
  area, silent and noisy pixels (more than k x the median, k = 10 by
  default), and "clean" rates without them, and the rate frame by frame.
  Changing the time base or k redraws without reading the file again.
- Four time bases, all listed: live time from the ToA gaps between frames
  (default, no metadata needed), frames x exposure and wall clock from
  `measurement_metadata.json`, and the first-to-last ToA span.
- DCR plots: maps for pixels and clusters, a per-pixel DCR histogram, and the
  rate vs time, showing the median pixel's DCR in Hz frame by frame for hits
  and clusters. The median is interpolated within the middle count, so it
  does not step in whole counts. **Export CSV...** writes one row per pixel.
- Qt-free `functions/dcr.py`, a Help section, and docs/dcr.md.

## [0.4.0] - 18-11-2026

### Added

- Timewalk correction without a TDC, for Timepix3 and Timepix4. The curve is
  measured from each file's own clusters: each hit's ToA relative to its
  cluster's largest-ToT pixel, peak per 25 ns ToT bin, built from the first
  50 M hits in ~10 s. The corrected times are added as the last column of
  the tables: `Clusters/ctoa_tw`, plus optionally `PixelHits/toa_tw`. The
  curve is stored as `/TimewalkCurve`. Adding a column rewrites the file once,
  via a temporary copy that replaces it only when complete. Later runs
  update the column in place.
- Advanced tab: **Timewalk-correct each output .hdf5**, with a ctot cut
  (default 1000 ns) and **also every pixel hit**, run after each file of a
  batch.
- Inspect HDF5: **Add timewalk columns to this file**, and a **Timewalk
  curve** plot of delay and jitter against ToT. The plot can try a ctot cut
  without writing anything. The summary lists the stored curve and columns.
- `add_timewalk_columns()`, `read_with_timewalk()` and
  `read_timewalk_curve()` in the Qt-free API. New docs page
  [Timewalk correction](docs/timewalk.md) and Help section.

### Changed

- Process tab: a light-green **Wrapper options (N)** button beside
  **Advanced flags**, shown while TDC columns or the timewalk correction are
  on. These no longer count towards **Advanced flags**, which now lists only
  what changes the Luna command or the output placement.
- Advanced tab: the *After processing* box is now **Wrapper options (run by
  this GUI after Luna, not Luna flags)**. On Timepix4 it hides only the TDC
  row instead of the whole box.

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
