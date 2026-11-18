"""Dark count rate (DCR) of one HDF5 file, per pixel and per cluster.

One pass over PixelHits and one over Clusters counts hits and clusters per
pixel and per frame; the rates follow by dividing by a measurement time. That
time is the one real choice, so there are four, all computed and shown side
by side:

- frames_toa  -- live time from the hits themselves: ToA is sorted, so the
                 N-1 largest ToA gaps are the dead gaps between N frames
                 (N = entries in /ExposureTimeBoundaries). Live time is the
                 first-to-last span minus those gaps. Needs no metadata.
- frames_meta -- frames x ExposureTime from measurement_metadata.json.
- toa_span    -- first to last hit. Counts the dead gaps between frames as
                 live, so it runs ~1 % long for 0.495 s frames every 0.5 s.
- wall_clock  -- StartDateTime to StopDateTime from the metadata. Includes
                 start-up and readout overhead; an upper bound.

/ExposureTimeBoundaries holds no times: it is one cumulative row index per
frame. Those indices do not always match PixelHits (a file whose last
boundary lies past the end of the table exists), so only their count is
used; the frame edges come from the ToA gaps.

Noisy pixels are those with more than k x the median hit count of the
pixels that counted at all. Silent pixels counted nothing -- masked or dead
when the median is high, possibly just Poisson zeros when it is a few hits.
The "clean" rates leave both out: noisy pixels from the count, and both
from the area.

Qt-free. numpy is imported inside the functions that need it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# Timepix3 and Timepix4 both have 55 um square pixels.
PIXEL_PITCH_MM = 0.055
PIXEL_AREA_MM2 = PIXEL_PITCH_MM ** 2

# (rows, cols) of one chip; the maps grow if the data reach further.
SENSOR_SHAPE = {"tpx3": (256, 256), "tpx4": (512, 448)}

TIME_SOURCES = {
    "frames_toa": "Frames, live time from ToA",
    "frames_meta": "Frames x exposure (metadata)",
    "toa_span": "ToA span, first to last hit",
    "wall_clock": "Wall clock, Start to Stop (metadata)",
}
DCR_DEFAULT_TIME_SOURCE = "frames_toa"
DCR_DEFAULT_NOISY_K = 10.0

# Frame breaks are trusted only when the narrowest of the N-1 widest ToA gaps
# is this many times the next widest one, i.e. the frame gaps stand clear of
# every pause inside a frame. Hits come in bursts (a cluster is ~8 hits within
# ns), so the mean hit spacing is no yardstick: in a 3.7 MHz dark run 437 k
# gaps exceed 20x the mean, the widest pause inside a frame is 154x, and the
# frame gaps are 18 400x.
FRAME_SEPARATION = 10.0

# While reading, the per-frame maps are cut at every gap wider than this many
# times the running mean hit spacing -- far above any pause inside a frame
# (154x above) and far below a frame gap (18 400x).
FRAME_CUT_RATIO = 1000.0

# Equal-width time bins for the rate-vs-time plot of a single-frame file.
TIME_BINS = 100

# The rate-vs-time plot shows the median pixel per frame (or time bin), which
# needs one map per frame. They are built in the same pass: a new map starts
# at every ToA gap wider than FRAME_CUT_RATIO x the running mean spacing,
# and the pieces are merged into frames once the frame gaps are known. Above
# this many map cells (int32) per table the per-frame medians are skipped.
MAX_SLOT_CELLS = 32_000_000

READ_STEP = 2_000_000


# -- metadata -------------------------------------------------------------

def find_measurement_metadata(h5_path, levels=4):
    """measurement_metadata.json for an output .hdf5, as a dict, or None.

    ASI writes <Measurement_...>/raw/<file>.tpx3 with the JSON in the
    measurement folder; an .hdf5 written beside its .tpx3 finds it two levels
    up. One written to a separate output folder usually finds none.
    """
    p = Path(h5_path)
    for up in [p.parent] + list(p.parents)[1:levels]:
        m = up / "measurement_metadata.json"
        if m.is_file():
            try:
                meta = json.loads(m.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                return None
            meta["_path"] = str(m)
            return meta
    return None


def metadata_times(meta):
    """(frames, exposure_s, wall_clock_s) from a metadata dict; None where
    a value is missing."""
    if not meta:
        return None, None, None
    conf = (meta.get("Detector") or {}).get("Config") or {}
    frames = meta.get("NumberOfFrames") or conf.get("nTriggers")
    exposure = conf.get("ExposureTime")
    wall = None
    try:
        wall = (datetime.fromisoformat(str(meta["StopDateTime"]))
                - datetime.fromisoformat(str(meta["StartDateTime"]))
                ).total_seconds()
    except Exception:
        pass
    try:
        frames = int(frames) if frames is not None else None
    except (TypeError, ValueError):
        frames = None
    try:
        exposure = float(exposure) if exposure is not None else None
    except (TypeError, ValueError):
        exposure = None
    return frames, exposure, wall


# -- the pass over the file -----------------------------------------------

def _fields(ds, names, a, b):
    """Rows a:b of only these fields -- one compound read, no full copy."""
    try:
        return ds.fields(list(names))[a:b]
    except AttributeError:                       # h5py < 3
        return ds[a:b][list(names)]


def _grow(img, need_h, need_w, np):
    h, w = img.shape
    if need_h <= h and need_w <= w:
        return img
    out = np.zeros((max(h, need_h), max(w, need_w)), dtype=img.dtype)
    out[:h, :w] = img
    return out


def _add_xy(img, x, y, np):
    x = x.astype("int64")
    y = y.astype("int64")
    if not len(x):
        return img
    img = _grow(img, int(y.max()) + 1, int(x.max()) + 1, np)
    h, w = img.shape
    img += np.bincount(y * w + x, minlength=h * w).reshape(h, w)
    return img


def _add_slots(maps, slot, x, y, shape, np):
    """Add hits to one int32 map per slot (frame, map piece or time bin)."""
    if not len(slot):
        return
    if len(slot) > 1 and (np.diff(slot) < 0).any():
        o = np.argsort(slot, kind="stable")
        slot, x, y = slot[o], x[o], y[o]
    cuts = np.flatnonzero(np.diff(slot)) + 1
    for a, b in zip(np.r_[0, cuts], np.r_[cuts, len(slot)]):
        s = int(slot[a])
        mp = maps.get(s)
        if mp is None:
            mp = np.zeros(shape, dtype="int32")
        maps[s] = _add_xy(mp, x[a:b], y[a:b], np)


def interp_median(c, np):
    """Median of integer counts, interpolated within the middle value.

    Per frame a pixel holds a few tens of counts, so the plain median moves
    in whole counts -- a ~3 % staircase that hides a 0.3 % drift. Treating
    each integer v as the interval [v - 0.5, v + 0.5) and interpolating
    (the grouped-data median) gives a continuous estimate; it equals v when
    every count is v.
    """
    c = np.asarray(c)
    if not c.size:
        return float("nan")
    v = np.partition(c, c.size // 2)[c.size // 2]
    below = int(np.count_nonzero(c < v))
    at = int(np.count_nonzero(c == v))
    return float(v) - 0.5 + (c.size / 2 - below) / at


def _slot_medians(maps, n_slots, mask, np):
    """interp_median over the masked pixels, per slot; 0 for an empty slot."""
    out = np.zeros(n_slots)
    h, w = mask.shape
    for s, mp in maps.items():
        mp = _grow(mp, h, w, np)
        hh, ww = mp.shape
        m = _grow(mask, hh, ww, np)
        out[s] = interp_median(mp[m], np)
    return out


def _top_gaps(best, cand, k, np):
    """Keep the k largest gaps seen so far. best and cand are tuples of
    equal-length arrays, the gap sizes first."""
    if k <= 0 or not len(cand[0]):
        return best
    if len(cand[0]) > k:
        pick = np.argpartition(cand[0], len(cand[0]) - k)[-k:]
        cand = tuple(c[pick] for c in cand)
    merged = tuple(np.concatenate([b, c]) for b, c in zip(best, cand))
    if len(merged[0]) > k:
        pick = np.argpartition(merged[0], len(merged[0]) - k)[-k:]
        merged = tuple(m[pick] for m in merged)
    return merged


def measure_dcr(f, det, meta=None, progress=None, step=READ_STEP):
    """Count one open h5py file. Returns a dict for dcr_report().

    progress(fraction, text) is called between blocks; return True from it
    to cancel (a None result is returned).
    """
    import numpy as np

    ph = f["PixelHits"] if "PixelHits" in f else None
    cl = f["Clusters"] if "Clusters" in f else None
    n = int(ph.shape[0]) if ph is not None else 0
    nc = int(cl.shape[0]) if cl is not None else 0
    if not n and not nc:
        raise ValueError("This file has neither pixel hits nor clusters.")

    meta_frames, exposure, wall = metadata_times(meta)
    etb_n = (int(f["ExposureTimeBoundaries"].shape[0])
             if "ExposureTimeBoundaries" in f else 0)
    n_frames = etb_n or meta_frames or 1
    k = max(n_frames - 1, 0)

    shape = SENSOR_SHAPE.get(det.key, (256, 256))
    hit_map = np.zeros(shape, dtype="int64")
    cl_map = np.zeros(shape, dtype="int64")
    total = n + nc

    # ---- pixels: map, sortedness, the k largest ToA gaps ------------------
    t_first = t_last = None
    unsorted = 0
    # (size, row of the hit after it, ToA of that hit) of the widest gaps.
    gaps = tuple(np.zeros(0, dtype="int64") for _ in range(3))
    prev = None
    timed = ph if n else cl
    tfield = "toa" if n else "ctoa"
    tn = n if n else nc
    if tn:
        t_first = int(timed[0][tfield])
        t_last = int(timed[tn - 1][tfield])
    edges = (np.linspace(t_first, t_last, TIME_BINS + 1) if tn and t_last > t_first
             else None)
    hits_t = np.zeros(TIME_BINS, dtype="int64")
    clusters_t = np.zeros(TIME_BINS, dtype="int64")

    def binned(t):
        idx = np.searchsorted(edges, t, side="right") - 1
        return np.bincount(np.clip(idx, 0, TIME_BINS - 1), minlength=TIME_BINS)

    # Per-slot maps for the per-frame medians: map pieces cut at wide gaps
    # when there are frames, time bins when there is one.
    slot_cap = MAX_SLOT_CELLS // (shape[0] * shape[1])
    pix_slots, pix_on, med_why = {}, bool(n), ""
    if k == 0 and edges is None:
        pix_on, med_why = False, "too few hits to follow over time"
    seg_next, cut_rows = 0, []

    t_min = t_max = None
    for a in range(0, n, step):
        blk = _fields(ph, ("toa", "x", "y"), a, min(a + step, n))
        hit_map = _add_xy(hit_map, blk["x"], blk["y"], np)
        t = blk["toa"].astype("int64")
        lo, hi = int(t.min()), int(t.max())
        t_min = lo if t_min is None else min(t_min, lo)
        t_max = hi if t_max is None else max(t_max, hi)
        if edges is not None:
            hits_t += binned(t)
        d = np.diff(t if prev is None else np.concatenate([[prev], t]))
        unsorted += int((d < 0).sum())
        off = len(t) - len(d)
        after = t[off:]
        pos = np.arange(len(d), dtype="int64") + a + off
        # k frame gaps plus the runner-up, to check they stand clear.
        gaps = _top_gaps(gaps, (d, pos, after), k + 1 if k else 0, np)
        prev = int(t[-1])
        if pix_on:
            if k:
                spacing = (int(t[-1]) - t_first) / max(a + len(t) - 1, 1)
                cut = np.zeros(len(t), dtype=bool)
                cut[off:] = d > FRAME_CUT_RATIO * spacing
                slot = seg_next + np.cumsum(cut)
                cut_rows.append(a + np.flatnonzero(cut))
                seg_next = int(slot[-1])
            else:
                slot = np.clip(np.searchsorted(edges, t, side="right") - 1,
                               0, TIME_BINS - 1)
            _add_slots(pix_slots, slot, blk["x"], blk["y"], shape, np)
            if len(pix_slots) > slot_cap:
                pix_on, pix_slots = False, {}
                med_why = ("too many frames to keep a map of each "
                           f"(more than {slot_cap:,})")
        if progress and progress(min(a + step, n) / total,
                                 f"PixelHits {min(a + step, n):,} / {n:,}"):
            return None

    # ---- frames ------------------------------------------------------------
    frames_ok, frames_why = False, ""
    frame_start = frame_end = frame_hits = None
    if n:
        t_first, t_last = t_min, t_max
        if unsorted:
            frames_why = f"ToA is not sorted ({unsorted:,} steps back)"
        elif k and len(gaps[0]) >= k:
            wide = np.argsort(gaps[0])[::-1]
            runner = int(gaps[0][wide[k]]) if len(wide) > k else 0
            top = wide[:k]
            top = top[np.argsort(gaps[1][top])]          # in row order
            gsz, gpos, after = (g[top] for g in gaps)
            if runner > 0 and gsz.min() < FRAME_SEPARATION * runner:
                frames_why = (f"the {n_frames} frames do not separate: the "
                              f"narrowest of the {k} widest ToA gaps is only "
                              f"{gsz.min() / runner:.1f}x the next one")
            else:
                frames_ok = True
                frame_start = np.concatenate([[t_first], after])
                frame_end = np.concatenate([after - gsz, [t_last]])
                frame_hits = np.diff(np.concatenate([[0], gpos, [n]]))
        elif k:
            frames_why = "fewer hits than frames"
        else:
            frames_ok = True                       # one frame: its span
            frame_start = np.array([t_first])
            frame_end = np.array([t_last])
            frame_hits = np.array([n])

    # Slots of the rate-vs-time plot: frames when there are several, time
    # bins for one. Per-slot medians over the pixels that counted at all.
    by_frame = bool(k) and frames_ok
    n_slots = len(frame_start) if by_frame else TIME_BINS
    if k and not frames_ok:
        med_why = med_why or (frames_why or "no frames")
    counted = hit_map > 0
    med_hits = None
    if pix_on and n and (by_frame or not k):
        if by_frame:
            cuts = (np.concatenate(cut_rows) if cut_rows
                    else np.zeros(0, dtype="int64"))
            if np.isin(gpos, cuts).all():
                # Map piece i starts at row starts[i]; merge pieces by frame.
                starts = np.concatenate([[0], cuts])
                frame_of = np.searchsorted(gpos, starts, side="right")
                frames = {}
                for s, mp in pix_slots.items():
                    fr = int(frame_of[s])
                    if fr in frames:
                        a_, b_ = frames[fr], mp
                        hh = max(a_.shape[0], b_.shape[0])
                        ww = max(a_.shape[1], b_.shape[1])
                        frames[fr] = _grow(a_, hh, ww, np) + _grow(b_, hh, ww, np)
                    else:
                        frames[fr] = mp
                pix_slots = frames
            else:
                pix_slots = {}
                med_why = (f"a frame gap is under {FRAME_CUT_RATIO:g}x the "
                           "mean hit spacing")
        if pix_slots:
            med_hits = _slot_medians(pix_slots, n_slots, counted, np)
    elif n and not med_why:
        med_why = "no per-frame maps"
    pix_slots = None                               # free the maps

    # ---- clusters ----------------------------------------------------------
    frame_clusters = (np.zeros(len(frame_start), dtype="int64")
                      if frames_ok else None)
    cl_slots = {}
    cl_on = (med_hits is not None or not n) and (by_frame or not k) \
        and (by_frame or edges is not None)
    size1 = 0
    size_sum = 0
    for a in range(0, nc, step):
        blk = _fields(cl, ("ctoa", "cx", "cy", "size"), a, min(a + step, nc))
        cl_map = _add_xy(cl_map, blk["cx"], blk["cy"], np)
        s = blk["size"].astype("int64")
        size1 += int((s == 1).sum())
        size_sum += int(s.sum())
        t = blk["ctoa"].astype("int64")
        if not n:
            lo, hi = int(t.min()), int(t.max())
            t_min = lo if t_min is None else min(t_min, lo)
            t_max = hi if t_max is None else max(t_max, hi)
        if edges is not None:
            clusters_t += binned(t)
        if frame_clusters is not None:
            fi = np.searchsorted(frame_start, t, side="right") - 1
            frame_clusters += np.bincount(np.clip(fi, 0, len(frame_start) - 1),
                                          minlength=len(frame_start))
        if cl_on:
            ref = frame_start if by_frame else edges
            slot = np.clip(np.searchsorted(ref, t, side="right") - 1,
                           0, n_slots - 1)
            _add_slots(cl_slots, slot, blk["cx"], blk["cy"], shape, np)
            if len(cl_slots) > slot_cap:
                cl_on, cl_slots = False, {}
        if progress and progress((n + min(a + step, nc)) / total,
                                 f"Clusters {min(a + step, nc):,} / {nc:,}"):
            return None
    if not n:
        t_first, t_last = t_min, t_max
        frames_why = "no pixel hits to find the frames in"

    # Both maps on one shape.
    h = max(hit_map.shape[0], cl_map.shape[0])
    w = max(hit_map.shape[1], cl_map.shape[1])
    hit_map = _grow(hit_map, h, w, np)
    cl_map = _grow(cl_map, h, w, np)
    # Cluster medians over the same pixels as the hit medians: those that
    # counted hits, or -- in a clusters-only file -- clusters.
    med_clusters = (_slot_medians(cl_slots, n_slots,
                                  hit_map > 0 if n else cl_map > 0, np)
                    if cl_slots else None)
    cl_slots = None

    sec = det.toa_seconds
    span = (t_last - t_first) * sec if t_first is not None else None
    times = {
        "frames_toa": (float(np.sum(frame_end - frame_start)) * sec
                       if frames_ok else None),
        "frames_meta": (n_frames * exposure if exposure else None),
        "toa_span": span,
        "wall_clock": wall,
    }
    why = {
        "frames_toa": frames_why,
        "frames_meta": ("no measurement_metadata.json found" if meta is None
                        else "no ExposureTime in the metadata"),
        "toa_span": "no hits",
        "wall_clock": ("no measurement_metadata.json found" if meta is None
                       else "no Start/StopDateTime in the metadata"),
    }
    return {
        "detector": det.key,
        "n_hits": n, "n_clusters": nc,
        "hit_map": hit_map, "cluster_map": cl_map,
        "size1": size1, "size_sum": size_sum,
        "n_frames": n_frames, "etb_frames": etb_n, "meta_frames": meta_frames,
        "exposure_s": exposure,
        "times": times, "why": why,
        "frame_start_s": (frame_start - t_first) * sec if frames_ok else None,
        "frame_live_s": (frame_end - frame_start) * sec if frames_ok else None,
        "frame_hits": frame_hits, "frame_clusters": frame_clusters,
        "bin_edges_s": ((edges - t_first) * sec if edges is not None else None),
        "bin_hits": hits_t if edges is not None else None,
        "bin_clusters": clusters_t if edges is not None else None,
        # Median counts per pixel in each slot -- frames when by_frame, else
        # the time bins; None (with med_why) when not available.
        "med_by_frame": by_frame,
        "med_hits": med_hits, "med_clusters": med_clusters,
        "med_why": med_why,
        "meta_path": (meta or {}).get("_path"),
    }


# -- rates ----------------------------------------------------------------

def pick_time(counts, source):
    """(seconds, source used, note). Falls back through the list in order
    when the chosen time is unavailable, and says so."""
    t = counts["times"].get(source)
    if t:
        return t, source, ""
    for alt in TIME_SOURCES:
        if counts["times"].get(alt):
            return (counts["times"][alt], alt,
                    f"{TIME_SOURCES[source]} unavailable ({counts['why'][source]})")
    return None, source, "no measurement time available"


def dcr_maps(counts, seconds, noisy_k, np=None):
    """Per-pixel rates and the masks they imply."""
    if np is None:
        import numpy as np
    hits = counts["hit_map"]
    active = hits > 0
    median = float(np.median(hits[active])) if active.any() else 0.0
    cut = noisy_k * median
    noisy = hits > cut if median > 0 else np.zeros_like(active)
    return {
        "hit_rate": hits / seconds,
        "cluster_rate": counts["cluster_map"] / seconds,
        "silent": ~active, "noisy": noisy,
        "median_hits": median, "noisy_cut_hits": cut,
    }


def fmt_rate(hz):
    """3.716 MHz, 457.6 kHz, 56.7 Hz, 0.0123 Hz."""
    for scale, unit in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if abs(hz) >= scale:
            return f"{hz / scale:.4g} {unit}"
    return f"{hz:.4g} Hz"


def dcr_report(counts, source=DCR_DEFAULT_TIME_SOURCE,
               noisy_k=DCR_DEFAULT_NOISY_K):
    """(lines, maps): the text for the DCR page, and dcr_maps() for plots."""
    import numpy as np

    T, used, note = pick_time(counts, source)
    out = []
    if T is None:
        return ["DCR            no measurement time available -- "
                + "; ".join(f"{TIME_SOURCES[s]}: {counts['why'][s]}"
                            for s in TIME_SOURCES)], None

    nf = counts["n_frames"]
    out.append(f"time base      {TIME_SOURCES[used]} = {T:.6g} s"
               + (f"   ({nf} frames)" if nf > 1 else ""))
    if note:
        out.append("   !! " + note)
    others = []
    for s, label in TIME_SOURCES.items():
        if s == used:
            continue
        t = counts["times"].get(s)
        others.append(f"{label}: " + (f"{t:.6g} s" if t else "n/a"))
    out.append("   other bases: " + " | ".join(others))
    if counts["meta_path"]:
        out.append("   metadata: " + counts["meta_path"])
    if counts["etb_frames"] and counts["meta_frames"] \
            and counts["etb_frames"] != counts["meta_frames"]:
        out.append(f"   !! {counts['etb_frames']} frame boundaries in the file "
                   f"but NumberOfFrames = {counts['meta_frames']}")

    m = dcr_maps(counts, T, noisy_k, np)
    hits, clm = counts["hit_map"], counts["cluster_map"]
    n_px = hits.size
    silent, noisy = m["silent"], m["noisy"]
    clean = ~(silent | noisy)
    n_clean = int(clean.sum())
    area = n_px * PIXEL_AREA_MM2
    clean_area = n_clean * PIXEL_AREA_MM2

    def per_area(rate, a):
        return (f"{fmt_rate(rate / a)}/mm2  ({fmt_rate(rate / a * 100)}/cm2)"
                if a else "n/a")

    out.append("")
    if counts["n_hits"]:
        n = counts["n_hits"]
        rate = n / T
        px_rates = m["hit_rate"]
        out.append(f"pixels         {n:,} hits -> {fmt_rate(rate)} over "
                   f"{n_px:,} pixels ({hits.shape[1]} x {hits.shape[0]}, "
                   f"{area:.4g} mm2)")
        out.append(f"   per pixel    mean {fmt_rate(rate / n_px)}, median "
                   f"{fmt_rate(m['median_hits'] / T)} (of pixels that counted)")
        out.append(f"   per area     {per_area(rate, area)}")
        out.append(f"   silent       {int(silent.sum()):,} pixel(s) with no hit"
                   + ("   (median is only "
                      f"{m['median_hits']:.0f} hits: these may be Poisson zeros)"
                      if 0 < m["median_hits"] < 10 else ""))
        n_noisy = int(noisy.sum())
        noisy_hits = int(hits[noisy].sum())
        line = (f"   noisy        {n_noisy:,} pixel(s) above {noisy_k:g} x "
                f"median = {fmt_rate(m['noisy_cut_hits'] / T)}")
        if n_noisy:
            line += f", {100 * noisy_hits / n:.2f} % of all hits"
        out.append(line)
        if hits.max() > 0:
            y0, x0 = np.unravel_index(int(hits.argmax()), hits.shape)
            out.append(f"   hottest      ({x0}, {y0}): {int(hits.max()):,} hits"
                       f" = {fmt_rate(float(px_rates[y0, x0]))}")
        clean_rate = (n - noisy_hits) / T
        if n_clean:
            out.append(f"   clean        {fmt_rate(clean_rate / n_clean)}/pixel, "
                       f"{per_area(clean_rate, clean_area)}   "
                       f"({n_clean:,} pixels: no noisy, no silent)")
    else:
        out.append("pixels         none in this file "
                   "(processed with --discard-pixel-data?)")

    out.append("")
    if counts["n_clusters"]:
        nc = counts["n_clusters"]
        crate = nc / T
        out.append(f"clusters       {nc:,} -> {fmt_rate(crate)}, "
                   f"{per_area(crate, area)}")
        if counts["n_hits"]:
            on_noisy = int(clm[noisy].sum())
            if n_clean:
                out.append(f"   clean        {fmt_rate((nc - on_noisy) / T)}, "
                           f"{per_area((nc - on_noisy) / T, clean_area)}   "
                           f"({on_noisy:,} centred on a noisy pixel left out)")
        out.append(f"   hits/cluster {counts['size_sum'] / nc:.3g}; "
                   f"size 1: {100 * counts['size1'] / nc:.1f} %")
    else:
        out.append("clusters       none in this file "
                   "(processed with --disable-clustering?)")

    if counts["frame_live_s"] is not None and len(counts["frame_live_s"]) > 1:
        live = counts["frame_live_s"]
        out.append("")
        parts = []
        for key, label in (("frame_hits", "pixel"), ("frame_clusters", "cluster")):
            c = counts.get(key)
            if c is not None and c.sum():
                r = c / live
                parts.append(f"{label} rate {fmt_rate(r.min())} .. "
                             f"{fmt_rate(r.max())} (spread "
                             f"{100 * r.std() / r.mean():.2f} %)")
        out.append(f"per frame      {len(live)} frames of {live.mean():.4g} s"
                   + ("; " + "; ".join(parts) if parts else ""))
        if counts["med_by_frame"]:
            meds = []
            for key, label in (("med_hits", "hits"),
                               ("med_clusters", "clusters")):
                if counts.get(key) is not None:
                    r = counts[key] / live
                    meds.append(f"{label} {fmt_rate(r.min())} .. "
                                f"{fmt_rate(r.max())}")
            if meds:
                out.append("   median pixel " + "; ".join(meds))
        elif counts.get("med_why"):
            out.append("   median pixel per frame unavailable: "
                       + counts["med_why"])
    return out, m


# -- export ---------------------------------------------------------------

def write_dcr_csv(path, counts, source=DCR_DEFAULT_TIME_SOURCE,
                  noisy_k=DCR_DEFAULT_NOISY_K, h5_path=""):
    """One row per pixel: x, y, hits, rate, clusters, rate, flags."""
    import numpy as np

    T, used, _note = pick_time(counts, source)
    if T is None:
        raise ValueError("No measurement time available.")
    m = dcr_maps(counts, T, noisy_k, np)
    h, w = counts["hit_map"].shape
    yy, xx = np.mgrid[0:h, 0:w]
    rows = np.column_stack([
        xx.ravel(), yy.ravel(),
        counts["hit_map"].ravel(), m["hit_rate"].ravel(),
        counts["cluster_map"].ravel(), m["cluster_rate"].ravel(),
        m["noisy"].ravel().astype(int), m["silent"].ravel().astype(int)])
    header = "\n".join([
        f"DCR per pixel of {h5_path}",
        f"time base: {TIME_SOURCES[used]} = {T:.9g} s",
        f"noisy: hits > {noisy_k:g} x median ({m['median_hits']:g}) hits",
        "x,y,hits,hit_rate_hz,clusters,cluster_rate_hz,noisy,silent"])
    np.savetxt(path, rows, delimiter=",", header=header,
               fmt=["%d", "%d", "%d", "%.6g", "%d", "%.6g", "%d", "%d"])
