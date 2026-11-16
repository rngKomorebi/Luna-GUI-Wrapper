# Contributing

Two branches: `main` (stable) and `develop` (active development). Fork, work
on a branch off `develop`, and open a pull request against it.
`pytest tests/` runs the test suite, which needs no display. See
[CONTRIBUTING.md](https://github.com/rngKomorebi/Luna-GUI-Wrapper/blob/main/CONTRIBUTING.md)
for the full workflow.

Bugs and feature requests:
[GitHub issues](https://github.com/rngKomorebi/Luna-GUI-Wrapper/issues).

## Project layout

```
src/
  main.py                 direct-run entry point; what the launchers start
  luna_gui_wrapper/
    functions/            Qt-free core -- importable without PySide6
      backend.py            native / WSL detection, path translation, drive mounts
      flags.py              the Luna flags: notes, defaults, detectors, argv, checks
      detectors.py          Timepix3 / Timepix4: converter, raw files, units
      failures.py           why a run failed, and what to change before a rerun
      naming.py             metadata -> name templates, the Job record
      tdc.py                /TDCEvents dedup, TDC columns, read_with_tdc()
      config.py             ~/.luna_gui_wrapper.json
      plotting.py           plot constants, komorebi_mpl styling
      common.py             app identity, icon path
    gui/                  the Qt application
      main_window.py        Process, Advanced and Inspect HDF5 tabs
      dataset_view.py       the scrollable row viewer for one dataset
      help_window.py        the Help window (Help menu, F1)
      models.py, widgets.py, style.py
    icon/                 app icon
tests/                    pytest suite for the Qt-free core
docs/                     this documentation (Sphinx + MyST) and its screenshots
```
