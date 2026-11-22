"""Timewalk curve measurement and the HDF5 write/read round trip, on a
synthetic Timepix3 file with a known walk."""

import pytest

from luna_gui_wrapper.functions import timewalk as tw
from luna_gui_wrapper.functions.detectors import TPX3

np = pytest.importorskip("numpy")

TICKS_PER_NS = 10_000           # Timepix3: 100 fs ticks
LSB_TICKS = 15_625              # 1.5625 ns ToA step
REF_TOT = 2000                  # ns, the bright reference pixel of each cluster
HITS_DTYPE = [("toa", "<u8"), ("cid", "<i8"), ("tot", "<u8"), ("dtoa", "<i4"),
              ("x", "<u2"), ("y", "<u2"), ("tof", "<i8")]
CLUSTERS_DTYPE = [("id", "<i8"), ("size", "<u8"), ("ctoa", "<u8"),
                  ("sum_tot", "<u8"), ("ctot", "<u8"), ("cx", "<u2"),
                  ("cy", "<u2")]


def walk_ns(tot):
    return 100.0 * np.exp(-np.asarray(tot, dtype=float) / 200.0)


def synthetic(n_clusters=8000, size=4, seed=1):
    """Clusters of one bright pixel plus dimmer ones, all fired at the same
    moment and delayed by walk_ns(tot), quantised to the 1.5625 ns step."""
    rng = np.random.default_rng(seed)
    t0 = 10**9 + np.arange(n_clusters) * 10**7          # 1 us apart
    tots = rng.choice(np.arange(25, 1525, 25), size=(n_clusters, size - 1))
    tots = np.concatenate([np.full((n_clusters, 1), REF_TOT), tots], axis=1)
    jitter = rng.normal(0, 1.0, tots.shape)
    t = t0[:, None] + (walk_ns(tots) + jitter) * TICKS_PER_NS
    toa = (np.round(t / LSB_TICKS) * LSB_TICKS).astype("uint64")
    hits = np.zeros(toa.size, dtype=HITS_DTYPE)
    hits["toa"] = toa.ravel()
    hits["tot"] = tots.ravel()
    hits["cid"] = np.repeat(np.arange(n_clusters), size)
    hits["tof"] = -1
    cl = np.zeros(n_clusters, dtype=CLUSTERS_DTYPE)
    cl["id"] = np.arange(n_clusters)
    cl["size"] = size
    cl["ctoa"] = toa[:, 0]
    cl["ctot"] = REF_TOT
    cl["sum_tot"] = tots.sum(axis=1)
    hits["dtoa"] = (hits["toa"].astype("int64")
                    - np.repeat(cl["ctoa"], size).astype("int64"))
    return hits, cl


def write_file(path, hits, cl):
    h5py = pytest.importorskip("h5py")
    # Chunked and resizable, as Luna writes them.
    with h5py.File(path, "w") as f:
        f.create_dataset("PixelHits", data=hits, chunks=(1500,), maxshape=(None,))
        f.create_dataset("Clusters", data=cl, chunks=(1500,), maxshape=(None,))
        f["PixelHits"].attrs["luna"] = "kept"


def test_curve_recovers_known_walk():
    hits, cl = synthetic()
    curve, used = tw.measure_timewalk({"PixelHits": hits, "Clusters": cl}, TPX3,
                                      ctot_cut_ns=1000)
    assert used == len(hits) - len(cl)          # every non-reference hit
    # Relative to the reference pixel, which itself walks walk_ns(REF_TOT).
    expected = walk_ns(curve["tot_ns"]) - walk_ns(REF_TOT)
    assert np.abs(curve["delay_ns"] - expected).max() < 0.5
    assert curve["delay_ns"][0] > 80            # ~88 ns at ToT 25 ns


def test_ctot_cut_excludes_dim_references():
    hits, cl = synthetic()
    with pytest.raises(ValueError, match="Too few"):
        tw.measure_timewalk({"PixelHits": hits, "Clusters": cl}, TPX3,
                            ctot_cut_ns=REF_TOT + 25)


def test_needs_clusters_and_hits():
    hits, cl = synthetic(n_clusters=10)
    with pytest.raises(ValueError, match="no pixel hits"):
        tw.measure_timewalk({"Clusters": cl}, TPX3)
    with pytest.raises(ValueError, match="no clusters"):
        tw.measure_timewalk({"PixelHits": hits}, TPX3)


def test_peak_ignores_flat_background():
    centres = np.arange(-200, 201) * 1.0
    counts = 50 + 10_000 * np.exp(-0.5 * ((centres - 30) / 3) ** 2)
    m, s = tw.peak_of(counts, centres, np)
    assert abs(m - 30) < 0.2 and abs(s - 3) < 0.5


def test_hdf5_round_trip(tmp_path):
    h5py = pytest.importorskip("h5py")
    pytest.importorskip("pandas")
    hits, cl = synthetic()
    path = tmp_path / "run.hdf5"
    write_file(path, hits, cl)

    res = tw.add_timewalk_columns(path, ctot_cut_ns=1000, pixel_hits=True)
    assert res["Clusters"] == {"rows": len(cl), "field": "ctoa_tw"}
    assert res["PixelHits"] == {"rows": len(hits), "field": "toa_tw"}
    assert res[tw.TW_CURVE]["rewritten"] is True
    with h5py.File(path, "r") as f:
        ph, c = f["PixelHits"], f["Clusters"]
        # The corrected time is the last column; everything Luna wrote is
        # still there, unchanged, with its chunking and resizability.
        assert ph.dtype.names[-1] == "toa_tw" and c.dtype.names[-1] == "ctoa_tw"
        assert ph.dtype.names[:-1] == hits.dtype.names
        for name in hits.dtype.names:
            assert (ph[name] == hits[name]).all()
        for name in cl.dtype.names:
            assert (c[name] == cl[name]).all()
        assert ph.chunks == (1500,) and ph.maxshape == (None,)
        assert ph.attrs["luna"] == "kept"
        toa_tw, ctoa_tw = ph["toa_tw"], c["ctoa_tw"]
        assert f[tw.TW_CURVE].attrs["written_by"] == tw.TW_STAMP
        assert set(f) == {"PixelHits", "Clusters", tw.TW_CURVE}
    assert not (tmp_path / "run.hdf5.timewalk-tmp").exists()
    # The reference pixel and its cluster get the same corrected time.
    ref = hits["tot"] == REF_TOT
    assert (toa_tw[ref] == ctoa_tw[hits["cid"][ref]]).all()
    # Correcting shrinks the spread inside clusters to about the jitter.
    raw = (hits["toa"].astype("int64") - cl["ctoa"][hits["cid"]].astype("int64"))
    cor = toa_tw.astype("int64") - ctoa_tw[hits["cid"]].astype("int64")
    assert cor[~ref].std() < 0.1 * raw[~ref].std()
    assert abs(cor[~ref].mean()) / TICKS_PER_NS < 0.5

    df = tw.read_with_timewalk(path, "Clusters")
    assert df.attrs["timewalk_from_file"] is True
    assert (df["ctoa_tw"].to_numpy() == ctoa_tw).all()
    curve = tw.read_timewalk_curve(path)
    assert curve.attrs["ctot_cut_ns"] == 1000

    # A rerun updates the fields in place -- both of them, even without the
    # per-hit option, so PixelHits/toa_tw never goes stale.
    res = tw.add_timewalk_columns(path, ctot_cut_ns=800, pixel_hits=False)
    assert res[tw.TW_CURVE]["rewritten"] is False
    assert set(res) == {"Clusters", "PixelHits", tw.TW_CURVE}
    with h5py.File(path, "r") as f:
        assert f[tw.TW_CURVE].attrs["ctot_cut_ns"] == 800
        assert f["PixelHits"].dtype.names.count("toa_tw") == 1


def test_clusters_only_then_hits(tmp_path):
    h5py = pytest.importorskip("h5py")
    pytest.importorskip("pandas")
    hits, cl = synthetic(n_clusters=6000)
    path = tmp_path / "run.hdf5"
    write_file(path, hits, cl)

    tw.add_timewalk_columns(path, ctot_cut_ns=1000)
    with h5py.File(path, "r") as f:
        assert "toa_tw" not in f["PixelHits"].dtype.names
        ctoa_tw = f["Clusters"]["ctoa_tw"]
    # Without the stored field the reader computes toa_tw from the curve.
    computed = tw.read_with_timewalk(path, "PixelHits")
    assert computed.attrs["timewalk_from_file"] is False

    # Adding the per-hit field later rewrites again, to the same values.
    tw.add_timewalk_columns(path, ctot_cut_ns=1000, pixel_hits=True)
    stored = tw.read_with_timewalk(path, "PixelHits")
    assert stored.attrs["timewalk_from_file"] is True
    assert (stored["toa_tw"].to_numpy() == computed["toa_tw"].to_numpy()).all()
    with h5py.File(path, "r") as f:
        assert (f["Clusters"]["ctoa_tw"] == ctoa_tw).all()
        assert f["Clusters"].dtype.names.count("ctoa_tw") == 1


def test_drops_legacy_datasets(tmp_path):
    """Files from the first version carry separate /ClustersTimewalk etc."""
    h5py = pytest.importorskip("h5py")
    hits, cl = synthetic(n_clusters=6000)
    path = tmp_path / "run.hdf5"
    write_file(path, hits, cl)
    with h5py.File(path, "r+") as f:
        f.create_dataset("ClustersTimewalk", data=np.zeros(3)).attrs[
            "written_by"] = tw.TW_STAMP
    tw.add_timewalk_columns(path)
    with h5py.File(path, "r") as f:
        assert "ClustersTimewalk" not in f
        assert "ctoa_tw" in f["Clusters"].dtype.names


def test_refuses_foreign_field(tmp_path):
    h5py = pytest.importorskip("h5py")
    hits, cl = synthetic(n_clusters=2000)
    foreign = np.zeros(len(cl), dtype=tw._with_field(cl.dtype, "ctoa_tw", np))
    for name in cl.dtype.names:
        foreign[name] = cl[name]
    path = tmp_path / "run.hdf5"
    write_file(path, hits, foreign)
    with pytest.raises(ValueError, match="not written by this GUI"):
        tw.add_timewalk_columns(path)
    with h5py.File(path, "r") as f:
        assert tw.TW_CURVE not in f              # nothing written on refusal


def test_corrected_times_match_the_stored_field(tmp_path):
    h5py = pytest.importorskip("h5py")
    hits, cl = synthetic()
    path = tmp_path / "run.hdf5"
    write_file(path, hits, cl)
    tw.add_timewalk_columns(path, ctot_cut_ns=1000)
    with h5py.File(path, "r") as f:
        stored = f["Clusters"]["ctoa_tw"]
        block = f["Clusters"].fields(["ctoa", "ctot"])[:]
        curve = f[tw.TW_CURVE][:]
    assert (tw.corrected_times(block, "Clusters", curve, TPX3, np) == stored).all()
