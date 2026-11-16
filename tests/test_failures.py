"""Failure diagnosis: the converter's last words -> cause and advice."""

from pathlib import Path

from luna_gui_wrapper.functions.failures import (NAME_MAX, diagnose, name_length,
                                              still_fails)

HDF5_PANIC = [
    "thread 'main' (19265) panicked at crates/luna-offline/luna-core/src/sink/"
    "hdf5_wrapper.rs:52:58:",
    "Failed to open hdf5 file.: H5Fcreate(): unable to create file: unable to "
    "open file: name = '/mnt/d/x.hdf5', errno = 36, error message = 'File name "
    "too long', flags = 13, o_flags = 242",
    "note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace",
]


def test_long_name_is_named_as_the_cause():
    dst = Path("D:/data/raw") / ("V-300-" + "x" * 290 + "_fCPv_000010.hdf5")
    f = diagnose(HDF5_PANIC, 101, dst, ctx={"comment": "y" * 278})
    assert f.kind == "name_too_long"
    assert str(name_length(dst)) in f.reason and str(NAME_MAX) in f.reason
    assert "{comment}" in f.advice and "278" in f.advice
    assert still_fails(f.kind, dst)
    assert not still_fails(f.kind, dst.with_name("fCPv_000010.hdf5"))


def test_hdf5_create_failure_with_a_short_name():
    f = diagnose(HDF5_PANIC[:2], 101, Path("D:/data/out.hdf5"))
    assert f.kind == "cannot_create"


def test_locked_output():
    lines = ["H5Fcreate(): unable to lock file, errno = 11, error message = "
             "'Resource temporarily unavailable'"]
    assert diagnose(lines, 101, Path("D:/a.hdf5")).kind == "locked"


def test_disk_full_and_unmounted_drive():
    assert diagnose(["write failed: No space left on device"], 101).kind == "disk_full"
    lines = ["[WARN]: Skipping file /mnt/e/a.tpx3",
             "thread 'main' panicked at src/x.rs:1:1:",
             "index out of bounds: the len is 0 but the index is 0"]
    assert diagnose(lines, 101).kind == "input_unreadable"


def test_rejected_flag():
    f = diagnose(["error: unexpected argument '--foo' found", "Usage: tpx4dump"], 2)
    assert f.kind == "bad_arguments" and "--foo" in f.reason


def test_unknown_panic_quotes_its_message():
    lines = ["thread 'main' (1) panicked at src/graph.rs:9:9:",
             "attempt to subtract with overflow"]
    f = diagnose(lines, 101)
    assert f.kind == "crash" and "subtract with overflow" in f.reason


def test_exit_zero_without_output_and_plain_exit_code():
    assert diagnose([], 0).kind == "no_output"
    assert diagnose(["just some info"], 3).kind == "exit_code"


def test_gui_side_errors():
    assert diagnose([], -1, err="executable not found or not runnable").kind == "not_started"
    assert diagnose([], -1, err="[WinError 5] Access is denied").kind == "gui_error"


def test_other_causes_are_not_judged_ahead_of_a_run():
    assert not still_fails("crash", Path("a.hdf5"))
