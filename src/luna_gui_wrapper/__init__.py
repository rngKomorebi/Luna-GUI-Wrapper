"""Luna GUI Wrapper -- Qt 6 (PySide6) front end for ASI Luna's tpx3dump
(Timepix3) and tpx4dump (Timepix4).

Browse to the data, let the GUI work out the names, and run the whole batch,
instead of typing tpx3dump / tpx4dump process -i ... -o ... once per file.

This program does not contain, modify, decompile or redistribute any part of
Luna. It runs the *unmodified* Luna executables as subprocesses through their
documented command line interface.

The TDC helpers are Qt-free and importable on their own, e.g. from a notebook:

    import luna_gui_wrapper as g
    g.read_tdcs("run.hdf5")                     # the edges, deduplicated
    g.add_tdc_columns("run.hdf5", "TDC1Rising")  # write the columns
    df = g.read_with_tdc("run.hdf5", "Clusters") # frame with the TDC columns

Importing the package does not import PySide6; only the GUI modules do.
"""

# Single source of the version: pyproject.toml reads it from here, so a
# plain source checkout (no package metadata) still knows it.
__version__ = "0.3.0"

from .functions.tdc import (
    add_tdc_columns,
    read_tdcs,
    read_with_tdc,
)  # noqa: E402

__all__ = ["__version__", "add_tdc_columns", "read_tdcs", "read_with_tdc"]
