"""Timepix3 / Timepix4: telling files apart, finding the converter, ToT bins."""

import numpy as np

from luna_gui_wrapper.functions.backend import detect_backend
from luna_gui_wrapper.functions.detectors import TPX3, TPX4, detect_from_file
from luna_gui_wrapper.functions.plotting import tot_bin_edges

HIT = [("toa", "<u8"), ("tot", "<u8"), ("x", "<u2"), ("y", "<u2")]


def _hits(tots):
    a = np.zeros(len(tots), dtype=HIT)
    a["tot"] = tots
    return a


def test_detect_from_file_by_tot():
    # A dict of numpy arrays answers the same questions an h5py file does.
    assert detect_from_file({"PixelHits": _hits([500, 400, 25575])}) is TPX3
    assert detect_from_file({"PixelHits": _hits([0, 1953125, 1990234375])}) is TPX4


def test_detect_from_file_undecided():
    assert detect_from_file({}) is None
    assert detect_from_file({"PixelHits": _hits([0, 0, 0])}) is None


def test_detect_falls_back_to_clusters():
    cl = np.zeros(2, dtype=[("ctot", "<u8"), ("size", "<u8")])
    cl["ctot"] = [13539062500, 238281250]
    assert detect_from_file({"PixelHits": _hits([]), "Clusters": cl}) is TPX4


def test_tpx4dump_found_one_level_down(tmp_path):
    # ASI's archive unpacks into a folder holding a same-named folder.
    inner = tmp_path / "luna-tpx4" / "luna-tpx4" / "bin"
    inner.mkdir(parents=True)
    (inner / "tpx4dump").write_text("")
    b = detect_backend(str(tmp_path / "luna-tpx4"), "tpx4dump")
    assert "tpx4dump" in (b.exe or b.detail)
    assert "No tpx4dump" not in b.detail
    assert "No tpx3dump" in detect_backend(str(tmp_path / "luna-tpx4")).detail


def test_tot_bins_tpx3_native_step():
    edges, step = tot_bin_edges(25575.0, TPX3.tot_lsb_ns, 2000, np)
    assert step == 25.0
    assert edges[-1] >= 25575.0


def test_tot_bins_tpx4_capped():
    hi = 13539062500 * TPX4.tot_seconds * 1e9          # ~1354 ns
    edges, step = tot_bin_edges(hi, TPX4.tot_lsb_ns, 2000, np)
    assert len(edges) - 1 <= 2000
    assert abs(step / TPX4.tot_lsb_ns - round(step / TPX4.tot_lsb_ns)) < 1e-9
    assert edges[-1] >= hi


def test_next_dt_sorts_before_differencing():
    from luna_gui_wrapper.functions.plotting import next_dt_ticks
    dt = next_dt_ticks(np.array([30, 10, 20, 60], dtype="uint64"), np)
    assert dt.tolist() == [10, 10, 30]


def test_next_dt_range_keeps_eps_t_inside():
    from luna_gui_wrapper.functions.plotting import (NEXT_DT_EPS_SPAN,
                                                     NEXT_DT_MAX_NS,
                                                     next_dt_range_ns)
    assert next_dt_range_ns(None) == NEXT_DT_MAX_NS
    assert next_dt_range_ns(100.0) == NEXT_DT_MAX_NS
    assert next_dt_range_ns(2000.0) == NEXT_DT_EPS_SPAN * 2000.0
