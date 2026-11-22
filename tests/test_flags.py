"""The tpx3dump flag table: argv construction and value checks."""

from luna_gui_wrapper.functions.flags import (FLAGS, flag_args, flag_bits,
                                           flag_problems)


# What an all-empty Advanced tab passes: only the flags with a GUI default.
GUI_DEFAULTS = ["--eps-s", "2.5", "--eps-t", "300ns"]


def test_unset_flags_pass_only_gui_defaults():
    assert flag_args({}) == GUI_DEFAULTS
    assert flag_args({f.key: "" for f in FLAGS}) == GUI_DEFAULTS
    assert flag_args({}, detector="tpx4") == GUI_DEFAULTS


def test_a_typed_value_beats_the_gui_default():
    assert flag_args({"eps_s": "1", "eps_t": "100ns"}) == ["--eps-s", "1",
                                                          "--eps-t", "100ns"]
    assert flag_args({"eps_s": " ", "eps_t": "50 ns"}) == ["--eps-s", "2.5",
                                                          "--eps-t", "50ns"]


def test_values_switches_and_choices():
    args = flag_args({"eps_t": "200 ns", "layout": "quad", "raw_only": True,
                      "disable_clustering": False, "log_level": ""})
    assert args == ["--layout", "quad", "--eps-s", "2.5", "--eps-t", "200ns",
                    "--raw-only"]


def test_switch_choice_needs_its_box():
    off = {"tof_tdc_reference_on": False, "tof_tdc_reference": "TDC2Falling"}
    assert flag_args(off) == GUI_DEFAULTS
    on = dict(off, tof_tdc_reference_on=True)
    assert flag_args(on) == ["--tof-tdc-reference", "TDC2Falling"] + GUI_DEFAULTS


def test_paths_are_translated():
    bits = flag_bits({"timewalk_file": r"C:\runs\tw.hdf5"},
                     translate=lambda p: "/mnt/c/runs/tw.hdf5")
    assert ["--timewalk-file", "/mnt/c/runs/tw.hdf5"] in bits


def test_problems():
    assert flag_problems({"eps_t": "100ns", "time_bin_interval": "0.495s",
                          "eps_s": "1.5", "num_time_bins": "3"}) == []
    bad = flag_problems({"eps_t": "100", "time_bin_interval": "500 parsecs",
                         "num_time_bins": "3.5", "eps_s": "one"})
    assert len(bad) == 4
    assert any(p.startswith("--eps-t needs a number with a unit") for p in bad)


def test_only_the_detectors_flags_are_passed():
    vals = {"layout": "quad", "input_format": "nikhef", "eps_t": "200ns"}
    assert flag_args(vals, detector="tpx3") == ["--layout", "quad",
                                                "--eps-s", "2.5",
                                                "--eps-t", "200ns"]
    assert flag_args(vals, detector="tpx4") == ["--input-format", "nikhef",
                                                "--eps-s", "2.5",
                                                "--eps-t", "200ns"]


def test_max_delay_must_be_below_one():
    assert flag_problems({"max_delay": "0.5"}, "tpx4") == []
    assert len(flag_problems({"max_delay": "1.5"}, "tpx4")) == 1
    assert flag_problems({"max_delay": "1.5"}, "tpx3") == []   # not a tpx3 flag


def test_keys_and_flags_are_unique():
    assert len({f.key for f in FLAGS}) == len(FLAGS)
    assert len({f.flag for f in FLAGS}) == len(FLAGS)
