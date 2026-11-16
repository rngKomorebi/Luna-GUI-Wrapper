# Contributing

Thank you for your interest in contributing to Luna GUI Wrapper!

## Branch model

- `main` — stable, release-ready. Pushes to it publish the docs site.
  Do **not** push directly here.
- `develop` — active development. All new work goes here.

## Workflow

1. Fork the repository.
2. Create a feature branch from `develop`:
   ```bash
   git checkout develop
   git checkout -b feature/your-feature-name
   ```
3. Make your changes following the code style guidelines below.
4. Add or update tests in `tests/`.
5. Update `CHANGELOG.md` under `[Unreleased]`.
6. Submit a pull request targeting the `develop` branch.

## Development setup

```bash
git clone https://github.com/rngKomorebi/Luna-GUI-Wrapper
cd Luna-GUI-Wrapper
pip install -e ".[analysis,dev]"
pre-commit install
```

## Where things live

| Path | What |
|---|---|
| `src/luna_gui_wrapper/functions/` | Qt-free core: backend/WSL, Timepix3/Timepix4 detectors, Luna flags, failure diagnosis, naming, config, TDC, plot styling. **Must not import PySide6** — `tests/test_import.py` checks this. |
| `src/luna_gui_wrapper/gui/` | The Qt app: main window, Help window, row viewer, table models, widgets, stylesheet. |
| `src/luna_gui_wrapper/icon/` | App icon (shipped as package data). |
| `src/main.py` | Direct-run entry point; what the launchers and shortcuts start. |
| `docs/` | The Sphinx (MyST) documentation and its screenshots; CI builds and publishes it. |

## Running the app locally

```bash
python src/main.py
# or, after `pip install -e .`:
luna-gui-wrapper
# or:
python -m luna_gui_wrapper
```

## No bundled executables

The project deliberately ships no PyInstaller (or similar) build on any
platform. A self-contained bundle makes it too easy to pass the GUI on with
the Luna binaries packed inside, which Luna's licence does not allow. The app
runs from source through `run_gui.sh` / `run_gui.bat` and the shortcuts the two
install scripts create. Please do not add a bundling spec or a release
workflow, and never commit any Luna file — see the licence note in docs/license.md.

## Code style

[PEP 8](https://peps.python.org/pep-0008/) and
[PEP 257](https://peps.python.org/pep-0257/). The pre-commit hook runs
`ruff check`; there is deliberately no auto-formatter, so keep to the
surrounding code's layout.

## Running tests

```bash
pytest tests/
```

Tests cover the Qt-free core and need no display.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format
where possible (`feat:`, `fix:`, `docs:`, `test:`).
