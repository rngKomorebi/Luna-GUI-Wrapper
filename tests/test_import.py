"""Package-level checks: version, public API, and the Qt-free core."""

import subprocess
import sys


def test_version():
    import luna_gui_wrapper

    assert isinstance(luna_gui_wrapper.__version__, str)
    assert luna_gui_wrapper.__version__.count(".") >= 1


def test_public_tdc_api():
    import luna_gui_wrapper as g

    for name in ("read_tdcs", "add_tdc_columns", "read_with_tdc"):
        assert callable(getattr(g, name))


def test_public_timewalk_api():
    import luna_gui_wrapper as g

    for name in ("add_timewalk_columns", "read_with_timewalk",
                 "read_timewalk_curve"):
        assert callable(getattr(g, name))


def test_core_does_not_import_qt():
    """functions/ must stay importable without PySide6 or a display.

    Run in a fresh interpreter, since another test may already have imported
    Qt into this one.
    """
    code = (
        "import sys, luna_gui_wrapper, luna_gui_wrapper.functions.backend, "
        "luna_gui_wrapper.functions.naming, luna_gui_wrapper.functions.tdc, "
        "luna_gui_wrapper.functions.timewalk, luna_gui_wrapper.functions.dcr, "
        "luna_gui_wrapper.functions.config, luna_gui_wrapper.functions.plotting; "
        "assert not any(m.startswith('PySide6') for m in sys.modules), "
        "[m for m in sys.modules if m.startswith('PySide6')]"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
