"""DCR: live time from the frame gaps, the four time bases, noisy and silent
pixels, per-frame counts and the CSV, on a synthetic Timepix3 file."""

import json

import pytest

from luna_gui_wrapper.functions import dcr
from luna_gui_wrapper.functions.detectors import TPX3

np = pytest.importorskip("numpy")
h5py = pytest.importorskip("h5py")

TICKS = 1e13                    # Timepix3 ToA ticks per second
FRAMES = 5
EXPOSURE = 0.1                  # s
PERIOD = 0.12                   # s: 20 ms dead between frames
HITS_PER_FRAME = 20_000
SIDE = 64                       # hits land on a 64 x 64 corner; the rest is silent
NOISY = (10, 20)                # (x, y) of the one noisy pixel
NOISY_EXTRA = 400               # its extra hits per frame
HITS_DTYPE = [("toa", "<u8"), ("cid", "<i8"), ("tot", "<u8"), ("dtoa", "<i4"),
              ("x", "<u2"), ("y", "<u2"), ("tof", "<i8")]
CLUSTERS_DTYPE = [("id", "<i8"), ("size", "<u8"), ("ctoa", "<u8"),
                  ("sum_tot", "<u8"), ("ctot", "<u8"), ("cx", "<u2"),
                  ("cy", "<u2")]


def synthetic(seed=3, hits_per_frame=HITS_PER_FRAME):
    rng = np.random.default_rng(seed)
    parts = []
    for k in range(FRAMES):
        n = hits_per_frame + NOISY_EXTRA
        t = (k * PERIOD + rng.uniform(0, EXPOSURE, n)) * TICKS
        x = rng.integers(0, SIDE, n)
        y = rng.integers(0, SIDE, n)
        x[:NOISY_EXTRA], y[:NOISY_EXTRA] = NOISY
        parts.append((t, x, y))
    t = np.concatenate([p[0] for p in parts]) + 1e9     # not starting at 0
    x = np.concatenate([p[1] for p in parts])
    y = np.concatenate([p[2] for p in parts])
    order = np.argsort(t)
    hits = np.zeros(len(t), dtype=HITS_DTYPE)
    hits["toa"] = t[order].astype("uint64")
    hits["x"], hits["y"] = x[order], y[order]
    hits["tot"] = 100
    hits["cid"] = np.arange(len(t))
    # One cluster per hit: dark counts are mostly single pixels.
    cl = np.zeros(len(t), dtype=CLUSTERS_DTYPE)
    cl["id"] = np.arange(len(t))
    cl["size"] = 1
    cl["ctoa"] = hits["toa"]
    cl["cx"], cl["cy"] = hits["x"], hits["y"]
    return hits, cl


def write(tmp_path, hits, cl, meta=True, etb=None):
    """An ASI-like layout: <measurement>/raw/<file>.hdf5, JSON one level up."""
    raw = tmp_path / "Measurement_X" / "raw"
    raw.mkdir(parents=True)
    path = raw / "dark.hdf5"
    with h5py.File(path, "w") as f:
        f.create_dataset("PixelHits", data=hits, chunks=(1500,), maxshape=(None,))
        f.create_dataset("Clusters", data=cl, chunks=(1500,), maxshape=(None,))
        # Cumulative row indices, deliberately not matching the table: only
        # their count may be used.
        f.create_dataset("ExposureTimeBoundaries",
                         data=etb if etb is not None
                         else np.arange(1, FRAMES + 1, dtype="uint64") * 10**6)
    if meta:
        (raw.parent / "measurement_metadata.json").write_text(json.dumps({
            "StartDateTime": "2026-10-19T14:43:40.000000",
            "StopDateTime": "2026-10-19T14:43:41.250000",
            "NumberOfFrames": FRAMES,
            "Detector": {"Config": {"ExposureTime": EXPOSURE,
                                    "TriggerPeriod": PERIOD}}}))
    return path


def measure(path, **kw):
    with h5py.File(path, "r") as f:
        return dcr.measure_dcr(f, TPX3, dcr.find_measurement_metadata(path), **kw)


@pytest.fixture
def dark(tmp_path):
    hits, cl = synthetic()
    return write(tmp_path, hits, cl), hits, cl


def test_four_time_bases(dark):
    path, hits, _cl = dark
    c = measure(path)
    t = c["times"]
    # Live time from the hits: within the gap to the first/last hit of each
    # frame, which is ~5 us at 200 kHz.
    assert t["frames_toa"] == pytest.approx(FRAMES * EXPOSURE, rel=1e-3)
    assert t["frames_meta"] == pytest.approx(FRAMES * EXPOSURE)
    assert t["toa_span"] == pytest.approx((FRAMES - 1) * PERIOD + EXPOSURE, rel=1e-3)
    assert t["wall_clock"] == pytest.approx(1.25)
    assert c["n_frames"] == FRAMES
    assert c["frame_hits"].sum() == len(hits)
    assert c["frame_clusters"].sum() == len(hits)
    assert c["frame_hits"].tolist() == [HITS_PER_FRAME + NOISY_EXTRA] * FRAMES
    assert c["frame_live_s"] == pytest.approx([EXPOSURE] * FRAMES, rel=1e-3)
    assert c["frame_start_s"] == pytest.approx(np.arange(FRAMES) * PERIOD, abs=1e-4)


def test_noisy_silent_and_clean_rates(dark):
    path, hits, _cl = dark
    c = measure(path)
    T = c["times"]["frames_toa"]
    m = dcr.dcr_maps(c, T, 10)
    assert m["noisy"].sum() == 1 and m["noisy"][NOISY[1], NOISY[0]]
    assert m["silent"].sum() == 256 * 256 - SIDE * SIDE
    assert c["hit_map"].sum() == len(hits)
    lines, _m = dcr.dcr_report(c, "frames_toa", 10)
    text = "\n".join(lines)
    assert "1 pixel(s) above 10 x median" in text
    # Clean: every hit off the noisy pixel, over the pixels that are neither
    # noisy nor silent.
    on_noisy = int(c["hit_map"][NOISY[1], NOISY[0]])
    expect = (len(hits) - on_noisy) / T / (SIDE * SIDE - 1)
    assert expect == pytest.approx(FRAMES * HITS_PER_FRAME / T / (SIDE * SIDE),
                                   rel=0.01)
    clean_line = next(ln for ln in lines if ln.strip().startswith("clean")
                      and "Hz/pixel" in ln)
    assert clean_line.split()[1] == dcr.fmt_rate(expect).split()[0]


def test_small_blocks_match_one_block(dark):
    """Gaps that straddle two blocks must still be found."""
    path, _hits, _cl = dark
    a = measure(path)
    b = measure(path, step=997)
    assert b["times"]["frames_toa"] == pytest.approx(a["times"]["frames_toa"])
    assert b["frame_hits"].tolist() == a["frame_hits"].tolist()
    assert (b["hit_map"] == a["hit_map"]).all()


def test_no_metadata_falls_back(tmp_path):
    hits, cl = synthetic()
    path = write(tmp_path, hits, cl, meta=False)
    assert dcr.find_measurement_metadata(path) is None
    c = measure(path)
    assert c["times"]["frames_meta"] is None and c["times"]["wall_clock"] is None
    T, used, note = dcr.pick_time(c, "frames_meta")
    assert used == "frames_toa" and "no measurement_metadata.json" in note
    assert T == pytest.approx(FRAMES * EXPOSURE, rel=1e-3)


def test_unsorted_toa_gives_no_frame_live_time(tmp_path):
    hits, cl = synthetic()
    hits[[100, 200]] = hits[[200, 100]]
    c = measure(write(tmp_path, hits, cl))
    assert c["times"]["frames_toa"] is None
    assert "not sorted" in c["why"]["frames_toa"]
    T, used, _note = dcr.pick_time(c, "frames_toa")
    assert used == "frames_meta" and T == pytest.approx(FRAMES * EXPOSURE)


def test_sparse_frames_do_not_separate(tmp_path):
    """Too few hits to tell a frame gap from an ordinary pause."""
    hits, cl = synthetic(hits_per_frame=3)
    hits = hits[hits["x"] != NOISY[0]]
    cl = cl[cl["cx"] != NOISY[0]]
    c = measure(write(tmp_path, hits, cl))
    assert c["times"]["frames_toa"] is None
    assert "do not separate" in c["why"]["frames_toa"] or \
        "fewer hits" in c["why"]["frames_toa"]


def test_single_frame_uses_span_and_time_bins(tmp_path):
    hits, cl = synthetic()
    c = measure(write(tmp_path, hits, cl, etb=np.array([len(hits)], "uint64")))
    assert c["n_frames"] == 1
    assert c["times"]["frames_toa"] == pytest.approx(c["times"]["toa_span"])
    assert c["bin_hits"].sum() == len(hits)
    assert c["bin_clusters"].sum() == len(hits)


def test_progress_can_cancel(dark):
    path, _h, _c = dark
    assert measure(path, progress=lambda frac, text: True, step=10_000) is None


def test_csv(dark, tmp_path):
    path, hits, _cl = dark
    c = measure(path)
    out = tmp_path / "dcr.csv"
    dcr.write_dcr_csv(out, c, "frames_toa", 10, h5_path=str(path))
    rows = np.loadtxt(out, delimiter=",")
    assert rows.shape == (256 * 256, 8)
    assert rows[:, 2].sum() == len(hits)
    noisy = rows[rows[:, 6] == 1]
    assert noisy.shape[0] == 1 and tuple(noisy[0, :2]) == NOISY
    assert "time base: Frames, live time from ToA" in out.read_text()


def direct_frame_medians(hits, field_x="x", field_y="y", t_field="toa"):
    """Per-frame interp_median over the pixels that counted, the slow way."""
    counted = np.zeros((256, 256), bool)
    counted[hits["y"], hits["x"]] = True
    t = hits[t_field].astype(float) / TICKS - 1e9 / TICKS
    frame = np.floor(t / PERIOD).astype(int)
    out = []
    for k in range(FRAMES):
        sel = hits[frame == k]
        mp = np.zeros((256, 256), int)
        np.add.at(mp, (sel[field_y], sel[field_x]), 1)
        out.append(dcr.interp_median(mp[counted], np))
    return np.array(out)


@pytest.mark.parametrize("step", [dcr.READ_STEP, 997])
def test_per_frame_medians_match_direct(dark, step):
    path, hits, cl = dark
    c = measure(path, step=step)
    assert c["med_by_frame"]
    assert c["med_hits"] == pytest.approx(direct_frame_medians(hits))
    clm = np.zeros(len(cl), dtype=[("x", "<u2"), ("y", "<u2"), ("toa", "<u8")])
    clm["x"], clm["y"], clm["toa"] = cl["cx"], cl["cy"], cl["ctoa"]
    assert c["med_clusters"] == pytest.approx(direct_frame_medians(clm))
    lines, _m = dcr.dcr_report(c)
    assert any(ln.strip().startswith("median pixel") for ln in lines)


def test_single_frame_medians_per_time_bin(tmp_path):
    hits, cl = synthetic()
    c = measure(write(tmp_path, hits, cl, etb=np.array([len(hits)], "uint64")))
    assert not c["med_by_frame"]
    assert len(c["med_hits"]) == dcr.TIME_BINS
    assert len(c["med_clusters"]) == dcr.TIME_BINS


def test_medians_skipped_above_memory_cap(dark, monkeypatch):
    path, _h, _c = dark
    monkeypatch.setattr(dcr, "MAX_SLOT_CELLS", 3 * 256 * 256)
    c = measure(path)
    assert c["med_hits"] is None and c["med_clusters"] is None
    assert "too many frames" in c["med_why"]
    assert c["times"]["frames_toa"] is not None      # the rest is unaffected


def test_interp_median():
    assert dcr.interp_median(np.array([5, 5, 5]), np) == 5.0
    # 3 of 6 below 4, 2 at 4: the half-way point is 0 into the [3.5, 4.5) class
    assert dcr.interp_median(np.array([1, 2, 3, 4, 4, 9]), np) == 3.5
    # Poisson counts: no staircase -- a 2 % change of the mean moves it
    rng = np.random.default_rng(0)
    a = dcr.interp_median(rng.poisson(30.0, 60_000), np)
    b = dcr.interp_median(rng.poisson(30.6, 60_000), np)
    assert 0.4 < b - a < 0.8


def test_fmt_rate():
    assert dcr.fmt_rate(3_716_000) == "3.716 MHz"
    assert dcr.fmt_rate(457.6e3) == "457.6 kHz"
    assert dcr.fmt_rate(56.7) == "56.7 Hz"
    assert dcr.fmt_rate(0.0123) == "0.0123 Hz"
