"""Persisted settings: one JSON file in the user's home directory."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".luna_gui_wrapper.json"
# Earlier names, newest first: before the Luna GUI Wrapper rename, and before
# that. Read only while CONFIG_PATH is missing, so an existing Luna path,
# folder list and theme survive the rename.
LEGACY_CONFIG_PATHS = (Path.home() / ".luna_tpx3_gui_qt.json",
                       Path.home() / ".tpx3dump_gui_qt.json")

def load_config() -> dict:
    # Nothing writes back to a legacy file -- save_config() always uses
    # CONFIG_PATH, which then takes precedence.
    for path in (CONFIG_PATH, *LEGACY_CONFIG_PATHS):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass  # a config we cannot persist is not worth interrupting the user
