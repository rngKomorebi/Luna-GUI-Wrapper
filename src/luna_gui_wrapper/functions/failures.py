"""Why a converter run failed, and what to change before running it again.

Qt-free. The GUI hands over the end of the converter's output plus the job's
paths; diagnose() picks the known cause out of it. A cause tied to the current
settings (an output name that is too long) can be checked again later with
still_fails(), so a rerun can warn when nothing has been changed yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# The longest file name Windows (NTFS: 255 UTF-16 units) and Linux (ext4: 255
# bytes) accept. A path component over it cannot be created at all.
NAME_MAX = 255


@dataclass
class Failure:
    kind: str          # short key, groups failures with one cause
    reason: str        # what happened, one line
    advice: str        # what to change before rerunning


def name_length(path) -> int:
    """Length of the file name as the stricter of the two file systems counts
    it: characters for NTFS, UTF-8 bytes for Linux."""
    name = Path(path).name
    return max(len(name), len(name.encode("utf-8")))


def _too_long(dst, ctx=None) -> Failure:
    n = name_length(dst)
    comment = (ctx or {}).get("comment", "")
    culprit = (f" This folder's comment alone adds {len(comment)} characters."
               if len(comment) > 60 else "")
    return Failure(
        "name_too_long",
        f"output name too long: {n} characters, the limit is {NAME_MAX}",
        "Shorten the name template on the Advanced tab, e.g. drop {comment} "
        "or use {stem}." + culprit)


def _panic_message(lines):
    """The line after Rust's `thread 'main' panicked at ...:` -- the message."""
    for i, ln in enumerate(lines):
        if "panicked at" in ln:
            rest = ln.split("panicked at", 1)[1].strip()
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if rest.endswith(":") and nxt:
                return nxt
            return rest
    return ""


def diagnose(lines, code, dst=None, src=None, ctx=None, err="") -> Failure:
    """Name the cause of one failed run.

    lines: the converter's last output lines (plus any error lines seen
    earlier); code: its exit code (-1 if it never ran); err: a message from
    the GUI side when there is no exit code to go on.
    """
    lines = [ln.rstrip() for ln in lines if ln and ln.strip()]
    text = "\n".join(lines)
    low = text.lower()
    exe_hint = "Check the Luna folder on the Advanced tab (Set up Luna...)."

    if err:
        if "not found" in err or "not runnable" in err:
            return Failure("not_started", "the converter could not be started",
                           exe_hint)
        if dst is not None and name_length(dst) > NAME_MAX:
            return _too_long(dst, ctx)
        return Failure("gui_error", err,
                       "Check that the output folder can be created and written.")

    if dst is not None and name_length(dst) > NAME_MAX:
        # Whatever the converter printed, this name can never be created.
        return _too_long(dst, ctx)

    if "no space left on device" in low:
        return Failure("disk_full", "the disk is full",
                       "Free space on the output drive (an .hdf5 can be 5-8x "
                       "the size of its raw file), or choose another output "
                       "folder.")

    if "h5fcreate" in low or "failed to open hdf5" in low or "unable to create file" in low:
        if "lock" in low or "resource temporarily unavailable" in low:
            return Failure("locked", "the output .hdf5 is open in another program",
                           "Close it in HDFView, Python or this app's Inspect "
                           "tab.")
        if "permission denied" in low:
            return Failure("no_permission",
                           "no permission to write in the output folder",
                           "Choose an output folder you can write to.")
        return Failure("cannot_create", "the output .hdf5 could not be created",
                       "Check that the output folder exists and is writable, "
                       "that the file is not open elsewhere, and that the "
                       "disk is not full.")

    if "index out of bounds: the len is 0" in low or "skipping file" in low:
        return Failure("input_unreadable", "the converter could not read the input file",
                       "On Windows this usually means WSL cannot see the drive "
                       "(USB disks): run again and accept the offer to mount "
                       "it, or copy the data to an internal disk.")

    for ln in lines:
        s = ln.strip()
        if re.match(r"error: (unexpected argument|invalid value|unrecognized|"
                    r"the argument|a value is required)", s):
            return Failure("bad_arguments", "the converter rejected the command line: "
                           + s[7:].strip(),
                           "Fix the flag on the Advanced tab (Advanced flags or "
                           "extra arguments).")

    if code in (137, -9, 9):
        return Failure("killed", "the converter was killed (often out of memory)",
                       "Close other programs, or lower --n-threads / "
                       "--hdf5-chunk-size on the Advanced tab.")

    if code == 0:
        return Failure("no_output", "the converter finished but wrote no output",
                       "Read this file's log above; the input may hold no data.")

    msg = _panic_message(lines)
    if msg:
        return Failure("crash", f"the converter crashed: {msg[:160]}",
                       "Read this file's log above. If it repeats, report it to "
                       "ASI with the log.")
    return Failure("exit_code", f"the converter stopped with exit code {code}",
                   "Read this file's log above for the cause.")


def still_fails(kind, dst) -> bool:
    """Would a cause tied to the settings hit again with the job as it is now?
    Only the name length can be checked ahead of a run; anything else is
    left to the rerun itself."""
    if kind == "name_too_long":
        return dst is not None and name_length(dst) > NAME_MAX
    return False
