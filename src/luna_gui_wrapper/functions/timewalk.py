"""Timewalk post-processing: measure the timewalk curve from the clusters in
the file itself and add timewalk-corrected times to its tables.

No TDC or test pulses are needed. All pixels of one cluster fired at the same
moment, so their spread in ToA is timewalk plus jitter. The pixel with the
largest ToT (the one tpx3dump/tpx4dump report as ctot, whose ToA is ctoa) has
the least timewalk and serves as the clock:

    dt = toa(hit) - ctoa(its cluster)     vs.     ToT(hit)

Only clusters with ctot >= ctot_cut take part, so the reference itself walks
little. Per ToT bin the peak of dt is found with an iterated 3-sigma
truncated mean (robust against the flat background of pile-up hits, and
unlike a median not stuck to the 1.5625 ns ToA grid). The result is one curve
per file, delay(ToT), and every time is corrected by it:

    toa_tw  = toa  - delay(tot)
    ctoa_tw = ctoa - delay(ctot)

The corrected times become the last field of the tables themselves --
Clusters/ctoa_tw, and PixelHits/toa_tw on request -- and the curve is kept as
/TimewalkCurve. An HDF5 compound dataset has a fixed dtype, so the first run
on a file rewrites it once (into a temporary file beside it, swapped in only
when complete); later runs update the field in place.

Correcting each pixel on its own means the reference's own walk drops out of
any time difference. The curve is relative to the high-ToT limit; the constant
offset to true arrival time is unknowable without an external reference and
does not matter for time differences.

Qt-free. h5py, numpy and pandas are imported inside the functions that need
them, so importing this module needs none of them.
"""

from __future__ import annotations

from .detectors import detect_from_file

# Table -> (time field, ToT field, corrected field appended to that table).
TW_FIELDS = {"Clusters": ("ctoa", "ctot", "ctoa_tw"),
             "PixelHits": ("toa", "tot", "toa_tw")}
TW_CURVE = "TimewalkCurve"
# Separate datasets the first version of this feature wrote; dropped when a
# file is converted to the in-table fields.
TW_LEGACY = ("ClustersTimewalk", "PixelHitsTimewalk")
TW_CURVE_FIELDS = [("tot_ns", "<f8"),     # mean hit ToT in the bin
                   ("delay_ns", "<f8"),   # peak of toa - ctoa: the timewalk
                   ("sigma_ns", "<f8"),   # width of that peak: the jitter
                   ("n", "<i8")]          # hits in the bin

# Marks what this GUI wrote, so a rerun replaces its own curve and fields and
# refuses to touch anything else under those names. On a table it sits in the
# attribute TW_FIELD_ATTR, naming the field.
TW_STAMP = "luna_gui_wrapper.timewalk"
TW_FIELD_ATTR = "timewalk_field"

# Clusters whose peak-pixel ToT is below this are not used to build the curve:
# their reference pixel walks too much itself. 1000 ns keeps that walk below
# ~5 ns on a Timepix3Cam; Luna's own --ctot-cut defaults to 450.
TW_DEFAULT_CTOT_CUT_NS = 1000.0

# Curve binning. 25 ns is one Timepix3 ToT step, so there every bin is one ToT
# value. Hits above TW_TOT_MAX_NS are left out of the curve (the walk there is
# far below one ToA step) and get the last bin's value.
TW_TOT_BIN_NS = 25.0
TW_TOT_MAX_NS = 10_000.0
# dt window around zero; the walk of a 25 ns hit is ~100 ns.
TW_DT_HALF_NS = 400.0
# A bin needs this many hits for its peak to count.
TW_MIN_COUNTS = 200

# The curve settles long before a big file ends: 50 M hits take ~10 s and the
# per-bin statistics are already in the 10^4-10^6 range.
TW_CURVE_MAX_HITS = 50_000_000
TW_CHUNK = 2_000_000


def _cluster_slice(clusters, lo, hi):
    """Clusters[lo:hi+1] as (ctoa, ctot), checking that id is the row number.

    Hits arrive in time order, so one chunk of hits belongs to a short run of
    consecutive clusters and only that run is read, three fields of it.
    """
    try:
        c = clusters.fields(["id", "ctoa", "ctot"])[lo:hi + 1]
    except (AttributeError, TypeError):       # a numpy array in the tests
        c = clusters[lo:hi + 1]
    if len(c) != hi - lo + 1 or c["id"][0] != lo or c["id"][-1] != hi:
        raise ValueError("Clusters/id is not the row number, so hits cannot be "
                         "matched to their cluster.")
    return c["ctoa"], c["ctot"]


def accumulate_timewalk(hits, ctoa, ctot, lo, det, ctot_cut_ns, H, tot_sum, np):
    """Add one chunk of hits to the dt-vs-ToT histogram H (in place).

    `ctoa`/`ctot` are the cluster fields for cluster ids lo, lo+1, ...
    Returns how many hits went in.
    """
    cid = hits["cid"]
    ok = cid >= 0
    k = cid[ok] - lo
    tick_ns = det.toa_seconds * 1e9
    tot_scale = det.tot_seconds * 1e9
    # toa - ctoa computed here, not read from dtoa: tpx4dump stores dtoa as
    # int32 of 1e-16 s ticks, which wraps beyond +-214 ns.
    ticks = hits["toa"][ok].astype("int64") - ctoa[k].astype("int64")
    tot = hits["tot"][ok]
    c_tot = ctot[k]
    half = (H.shape[1] - 1) // 2
    dt_bin = np.rint(ticks * (tick_ns / det.toa_lsb_ns)).astype("int64")
    tot_ns = tot.astype("float64") * tot_scale
    keep = ((c_tot.astype("float64") * tot_scale >= ctot_cut_ns)
            # the reference pixel itself: dt = 0 by definition
            & ~((ticks == 0) & (tot == c_tot))
            & (np.abs(dt_bin) <= half) & (tot_ns < TW_TOT_MAX_NS))
    if not keep.any():
        return 0
    tb = (tot_ns[keep] // TW_TOT_BIN_NS).astype("int64")
    idx = tb * H.shape[1] + dt_bin[keep] + half
    H += np.bincount(idx, minlength=H.size).reshape(H.shape)
    tot_sum += np.bincount(tb, weights=tot_ns[keep], minlength=len(tot_sum))
    return int(keep.sum())


def peak_of(counts, centres, np, iterations=12):
    """(centre, sigma) of the peak in one histogram row: an iterated 3-sigma
    truncated mean, started at the mode."""
    m = centres[int(np.argmax(counts))]
    s = 30.0
    for _ in range(iterations):
        w = counts * (np.abs(centres - m) < 3 * s)
        tot = w.sum()
        if tot == 0:
            break
        m = float((w * centres).sum() / tot)
        s = max(float(np.sqrt((w * (centres - m) ** 2).sum() / tot)),
                0.5 * float(centres[1] - centres[0]))
    return m, s


def curve_from_histogram(H, tot_sum, dt_lsb_ns, np, min_counts=TW_MIN_COUNTS):
    """The curve as a structured array, one row per well-filled ToT bin."""
    half = (H.shape[1] - 1) // 2
    centres = (np.arange(H.shape[1]) - half) * dt_lsb_ns
    rows = []
    for b in range(H.shape[0]):
        n = int(H[b].sum())
        if n < min_counts:
            continue
        m, s = peak_of(H[b].astype("float64"), centres, np)
        rows.append((tot_sum[b] / n, m, s, n))
    return np.array(rows, dtype=np.dtype(TW_CURVE_FIELDS))


def timewalk_delay_ns(tot_ns, curve, np):
    """delay(ToT) in ns, linear between bins and held at both ends."""
    return np.interp(tot_ns, curve["tot_ns"], curve["delay_ns"])


def measure_timewalk(f, det, ctot_cut_ns=TW_DEFAULT_CTOT_CUT_NS,
                     max_hits=TW_CURVE_MAX_HITS, np=None):
    """(curve, hits used) from an open file. Raises if there is nothing to
    measure from."""
    if np is None:
        import numpy as np
    if "PixelHits" not in f or not f["PixelHits"].shape[0]:
        raise ValueError("This file has no pixel hits to measure the timewalk "
                         "from (processed with --discard-pixel-data?).")
    if "Clusters" not in f or not f["Clusters"].shape[0]:
        raise ValueError("This file has no clusters (processed with "
                         "--disable-clustering?), and the timewalk is measured "
                         "inside clusters.")
    ph, cl = f["PixelHits"], f["Clusters"]
    n = ph.shape[0] if not max_hits else min(ph.shape[0], int(max_hits))
    half = int(round(TW_DT_HALF_NS / det.toa_lsb_ns))
    n_tot = int(TW_TOT_MAX_NS / TW_TOT_BIN_NS)
    H = np.zeros((n_tot, 2 * half + 1), dtype="int64")
    tot_sum = np.zeros(n_tot)
    used = 0
    for i in range(0, n, TW_CHUNK):
        hits = ph[i:min(i + TW_CHUNK, n)]
        cid = hits["cid"]
        if not (cid >= 0).any():
            continue
        lo, hi = int(cid[cid >= 0].min()), int(cid.max())
        ctoa, ctot = _cluster_slice(cl, lo, hi)
        used += accumulate_timewalk(hits, ctoa, ctot, lo, det, ctot_cut_ns,
                                    H, tot_sum, np)
    curve = curve_from_histogram(H, tot_sum, det.toa_lsb_ns, np)
    if len(curve) < 2:
        raise ValueError(
            "Too few multi-pixel clusters with ctot >= %g ns to measure a "
            "timewalk curve (%s hits used). Try a lower ctot cut."
            % (ctot_cut_ns, format(used, ",")))
    return curve, used


def _owned_field(ds, field):
    """True if `field` is in table `ds` and this GUI put it there; raises if
    the field is there but someone else's."""
    if field not in (ds.dtype.names or ()):
        return False
    if ds.attrs.get(TW_FIELD_ATTR) != field:
        raise ValueError("%s already has a field '%s' that was not written by "
                         "this GUI. Refusing to replace it." % (ds.name, field))
    return True


def _corrected(block, t_field, tot_field, curve, det, np):
    """t - delay(ToT) for one block of rows, in the table's own ticks."""
    delay = timewalk_delay_ns(np.asarray(block[tot_field]) * (det.tot_seconds * 1e9),
                              curve, np)
    corr = np.rint(delay / (det.toa_seconds * 1e9)).astype("int64")
    t = np.asarray(block[t_field]).astype("int64")
    return np.clip(t - corr, 0, None).astype("uint64")


def corrected_times(block, table, curve, det, np):
    """The corrected time (ctoa_tw / toa_tw) for rows of `table` that do not
    carry the field, from a timewalk curve; the values the field would hold.
    `block` needs the table's time and ToT fields."""
    t_field, tot_field, _field = TW_FIELDS[table]
    return _corrected(block, t_field, tot_field, curve, det, np)


def _with_field(dtype, field, np):
    """`dtype` with a u8 `field` appended after its last byte, keeping the
    original names, offsets and padding exactly."""
    names = list(dtype.names)
    return np.dtype({"names": names + [field],
                     "formats": [dtype.fields[n][0] for n in names] + ["<u8"],
                     "offsets": [dtype.fields[n][1] for n in names]
                     + [dtype.itemsize],
                     "itemsize": dtype.itemsize + 8})


def _copy_table_with_field(src, dst_parent, field, t_field, tot_field, curve,
                           det, np, h5py):
    """Write `src` into `dst_parent` under the same name with `field` appended,
    keeping its chunking, compression, maxshape and attributes."""
    dtype = _with_field(src.dtype, field, np)
    name = src.name.rsplit("/", 1)[-1]
    # Luna's own creation properties, so filters (any compression, even a
    # plugin one) carry over. The chunk layout also records the row size,
    # which has grown, so it is set again from the chunk dimensions.
    dcpl = src.id.get_create_plist().copy()
    if src.chunks:
        dcpl.set_chunk(src.chunks)
    dsid = h5py.h5d.create(dst_parent.id, name.encode(),
                           h5py.h5t.py_create(dtype, logical=True),
                           src.id.get_space(), dcpl=dcpl)
    dst = h5py.Dataset(dsid)
    for k, v in src.attrs.items():
        dst.attrs[k] = v
    n = src.shape[0]
    for i in range(0, n, TW_CHUNK):
        j = min(i + TW_CHUNK, n)
        block = src[i:j]
        out = np.zeros(j - i, dtype=dtype)
        for col in src.dtype.names:
            out[col] = block[col]
        out[field] = _corrected(block, t_field, tot_field, curve, det, np)
        dst[i:j] = out
    dst.attrs[TW_FIELD_ATTR] = field
    return dst


def _update_field(ds, field, t_field, tot_field, curve, det, np):
    """Recompute an existing field in place, a slice at a time."""
    n = ds.shape[0]
    for i in range(0, n, TW_CHUNK):
        j = min(i + TW_CHUNK, n)
        block = ds[i:j]
        block[field] = _corrected(block, t_field, tot_field, curve, det, np)
        ds[i:j] = block


def _write_curve(f, curve, attrs):
    if TW_CURVE in f:
        del f[TW_CURVE]
    f.create_dataset(TW_CURVE, data=curve).attrs.update(attrs)


def add_timewalk_columns(path, ctot_cut_ns=TW_DEFAULT_CTOT_CUT_NS,
                         pixel_hits=False, max_hits=TW_CURVE_MAX_HITS,
                         detector=None, log=None):
    """Measure this file's timewalk curve and add corrected times to its tables.

    Clusters gets a last field `ctoa_tw`; with `pixel_hits`, PixelHits gets
    `toa_tw` too. Both are in the table's own ticks. The curve is stored as
    /TimewalkCurve. A table that already carries the field from an earlier
    run is updated to the new curve, whatever `pixel_hits` says, so it never
    goes stale.

    Adding a field means rewriting the file once: it is written to a
    temporary file beside the original and swapped in only when complete,
    which needs free space for one more copy of the file. Later runs update
    the fields in place.

    Returns a summary dict, and raises on anything wrong.
    """
    import os
    import shutil
    from pathlib import Path

    import h5py
    import numpy as np

    say = log if log is not None else (lambda _m: None)
    path = Path(path)
    with h5py.File(path, "r") as f:
        det = detector or detect_from_file(f)
        if det is None:
            raise ValueError("Cannot tell Timepix3 from Timepix4 in this file: "
                             "it has no non-zero ToT.")
        for name in (TW_CURVE,) + TW_LEGACY:
            if name in f and f[name].attrs.get("written_by") != TW_STAMP:
                raise ValueError("/%s already exists and was not written by "
                                 "this GUI. Refusing to replace it." % name)
        # Which tables get the field, and which of them have it already.
        targets, have = [], set()
        for table, (_t, _tot, field) in TW_FIELDS.items():
            if table not in f or not f[table].shape[0]:
                continue
            owned = _owned_field(f[table], field)
            if table == "Clusters" or pixel_hits or owned:
                targets.append(table)
                if owned:
                    have.add(table)
        curve, used = measure_timewalk(f, det, ctot_cut_ns, max_hits, np)
        legacy = [n for n in TW_LEGACY if n in f]
    say("  timewalk curve from %s hits (ctot >= %g ns): %.1f ns at "
        "ToT %.0f ns, %.2f ns at ToT %.0f ns"
        % (format(used, ","), ctot_cut_ns, curve["delay_ns"][0],
           curve["tot_ns"][0], curve["delay_ns"][-1], curve["tot_ns"][-1]))

    attrs = {"written_by": TW_STAMP, "ctot_cut_ns": float(ctot_cut_ns),
             "hits_used": used, "detector": det.key,
             # ticks of toa / ctoa / toa_tw / ctoa_tw, so readers need no table
             "seconds_per_tick": det.toa_seconds,
             "method": "peak of toa - ctoa per ToT bin, clusters with "
                       "ctot >= ctot_cut_ns; 3-sigma truncated mean"}
    out = {}
    rewrite = any(t not in have for t in targets)
    if not rewrite:
        with h5py.File(path, "r+") as f:
            for table in targets:
                t_field, tot_field, field = TW_FIELDS[table]
                _update_field(f[table], field, t_field, tot_field, curve, det, np)
                out[table] = {"rows": f[table].shape[0], "field": field}
                say("  %s/%s updated in place (%s rows)"
                    % (table, field, format(f[table].shape[0], ",")))
            for name in legacy:
                del f[name]
            _write_curve(f, curve, attrs)
    else:
        size = path.stat().st_size
        free = shutil.disk_usage(path.parent).free
        if free < size * 1.1 + 64e6:
            raise ValueError(
                "Adding the timewalk field rewrites the file once, which needs "
                "%.1f GB free next to it; only %.1f GB are free."
                % (size * 1.1 / 1e9, free / 1e9))
        tmp = path.with_name(path.name + ".timewalk-tmp")
        say("  rewriting the file once to add %s"
            % ", ".join("%s/%s" % (t, TW_FIELDS[t][2]) for t in targets))
        try:
            with h5py.File(path, "r") as src, h5py.File(tmp, "w") as dst:
                for k, v in src.attrs.items():
                    dst.attrs[k] = v
                for name in src:
                    if name in legacy or name == TW_CURVE:
                        continue
                    if name in targets:
                        t_field, tot_field, field = TW_FIELDS[name]
                        if name in have:
                            src.copy(name, dst)
                            _update_field(dst[name], field, t_field, tot_field,
                                          curve, det, np)
                        else:
                            _copy_table_with_field(src[name], dst, field,
                                                   t_field, tot_field, curve,
                                                   det, np, h5py)
                        out[name] = {"rows": src[name].shape[0], "field": field}
                        say("  %s/%s: %s rows"
                            % (name, field, format(src[name].shape[0], ",")))
                    else:
                        # Raw chunk copy: filters, chunking and attributes
                        # kept, nothing decoded.
                        src.copy(name, dst)
                _write_curve(dst, curve, attrs)
            try:
                os.replace(tmp, path)
            except PermissionError as exc:
                raise ValueError(
                    "Could not replace %s: it is open in another program (a "
                    "notebook, HDFView, ...). Close it there and try again."
                    % path.name) from exc
        finally:
            if tmp.exists():
                tmp.unlink()
    out[TW_CURVE] = {"bins": len(curve), "hits_used": used,
                     "ctot_cut_ns": float(ctot_cut_ns), "detector": det.key,
                     "delay_ns_lowest_tot": float(curve["delay_ns"][0]),
                     "rewritten": rewrite}
    return out


def read_timewalk_curve(path):
    """The stored /TimewalkCurve as a DataFrame; its attrs carry the settings."""
    import h5py
    import pandas as pd

    with h5py.File(path, "r") as f:
        if TW_CURVE not in f:
            raise ValueError("No /%s in this file: run add_timewalk_columns() "
                             "first." % TW_CURVE)
        df = pd.DataFrame(f[TW_CURVE][:])
        df.attrs.update({k: (v.item() if hasattr(v, "item") else v)
                         for k, v in f[TW_CURVE].attrs.items()})
    return df


def read_with_timewalk(path, which="Clusters", limit=None):
    """One DataFrame of `which` with the corrected time and the correction.

    `ctoa_tw` / `toa_tw` come straight from the table when the field is there;
    otherwise (PixelHits written without the per-hit option) they are computed
    from /TimewalkCurve, to the same values. `timewalk_ns` (what was
    subtracted) is added either way.
    """
    import h5py
    import numpy as np
    import pandas as pd

    if which not in TW_FIELDS:
        raise ValueError("Expected one of %s, got %r"
                         % (", ".join(TW_FIELDS), which))
    t_field, tot_field, field = TW_FIELDS[which]
    with h5py.File(path, "r") as f:
        if TW_CURVE not in f:
            raise ValueError("No /%s in this file: run add_timewalk_columns() "
                             "first." % TW_CURVE)
        if which not in f or not f[which].shape[0]:
            raise ValueError("This file has no /%s rows." % which)
        det = detect_from_file(f)
        if det is None:
            raise ValueError("Cannot tell Timepix3 from Timepix4 in this file.")
        total = f[which].shape[0]
        n = total if limit is None else min(int(limit), total)
        df = pd.DataFrame(f[which][:n])
        curve = f[TW_CURVE][:]
    stored = field in df.columns
    df["timewalk_ns"] = timewalk_delay_ns(
        df[tot_field].to_numpy() * (det.tot_seconds * 1e9), curve, np)
    if not stored:
        df[field] = _corrected(df, t_field, tot_field, curve, det, np)
    df.attrs["timewalk_from_file"] = bool(stored)
    return df
