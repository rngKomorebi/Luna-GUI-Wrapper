"""Entry point: create the QApplication and show the main window.

Called by the `luna-gui-wrapper` console script, by `python -m luna_gui_wrapper`,
and by src/main.py (which the launchers and shortcuts start).
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .functions.common import (APP_NAME, APP_USER_MODEL_ID, DESKTOP_FILE_NAME,
                               ICON_PATH, IS_WINDOWS)
from .gui.main_window import MainWindow
from .gui.theme import theme_manager
from .gui.title_bar import install_dark_title_bars


def set_linux_desktop_name(app):
    """Tell Qt which .desktop file describes this app.

    A Wayland shell has no WM_CLASS to go on: it matches a window to its
    launcher by app_id, which Qt takes from this value. Without it GNOME
    cannot find luna-gui-wrapper.desktop, so the dash and the task switcher
    fall back to a generic gear however the window icon is set.
    """
    if IS_WINDOWS:
        return
    try:
        app.setDesktopFileName(DESKTOP_FILE_NAME)
    except Exception:
        pass


def set_windows_app_id():
    """Give Windows an explicit AppUserModelID.

    The taskbar groups windows -- and chooses their icon -- by this id. A
    script hosted by python.exe inherits the interpreter identity, so the
    taskbar shows the Python logo however carefully setWindowIcon() is called.
    Harmless everywhere else; failure is not worth reporting.
    """
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID)
    except Exception:
        pass


def main():
    set_windows_app_id()            # before any window exists
    # On X11, Qt takes the WM_CLASS instance name from argv[0], and the
    # launcher's StartupWMClass has to match it for the dock to show the right
    # icon. argv[0] differs with every way of starting the app (src/main.py,
    # python -m, the console script), so pin it to the
    # .desktop id instead of letting it follow the launch path.
    app = QApplication([DESKTOP_FILE_NAME] + sys.argv[1:])
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    set_linux_desktop_name(app)
    # Before the widgets it applies to, so that nothing is built in the
    # default palette and re-polished into the themed one.
    theme_manager().apply_to_app(app)
    # Before any window is shown, so that none of them - the main window,
    # Preferences, Help, the message boxes - first appears with the light
    # system title bar.
    install_dark_title_bars(app)
    if ICON_PATH:
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
