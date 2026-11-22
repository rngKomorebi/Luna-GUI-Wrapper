# TDC

Timepix3 only: Luna's `tpx4dump` (v0.4.4) writes no `/TDCEvents`, so on Timepix4 the TDC columns option is hidden and the TDC plot
does not apply (see [Why no TDC on Timepix4?](intro.md#timepix3-and-timepix4)).

`tpx3dump` records every TDC edge it saw in `/TDCEvents`:

| Field | |
|---|---|
| `tdc_type` | `1` `TDC1Rising`, `2` `TDC1Falling`, `3` `TDC2Rising`, `4` `TDC2Falling` |
| `trigger_count` | the trigger counter that came with the edge |
| `timestamp` | 100 fs ticks, the **same clock** as `PixelHits/toa` and `Clusters/ctoa` |

Two things about that dataset are easy to get wrong, so the GUI handles both.

**Every chip repeats the packet.** A quad carries each physical edge four times
and an octal eight, so a 40-row `/TDCEvents` in a quad file describes ten
triggers, not forty. Everything here deduplicates on `(tdc_type, timestamp)`
first, the same thing ASI's `read_tdcs.py` does. The Inspect summary reports
both numbers so the difference is never a surprise:

```
TDC            10 edge(s) (40 raw records; every chip repeats the packet)
   5 TDC1Rising, 5 TDC1Falling
   TDC1Rising   5 edges, period 100.410 us (+- 0.0 ns)
   TDC1Falling  5 edges, period 100.410 us (+- 0.3 ns)
   span         0.453 ms
```

**The timestamps share the hit clock**, which is what makes "which trigger does
this cluster belong to" a subtraction rather than a guess.

## The tdc column

**Inspect HDF5 → TDC → Add TDC columns to this file** tags every pixel hit and every
cluster with the TDC edge it follows, and writes the result back into the same
`.hdf5`. On the Advanced tab, **Add TDC columns to each output .hdf5** does it
automatically for every file the batch produces.

The columns land in two new datasets, `/PixelHitsTDC` and `/ClustersTDC`, each
row-aligned 1:1 with the dataset it describes:

| Column | |
|---|---|
| `tdc` | timestamp of the reference edge this row follows, in 100 fs ticks |
| `tdc_dt` | `toa` (or `ctoa`) − `tdc`, same ticks |
| `tdc_index` | row in the deduplicated TDC table |
| `tdc_trigger` | that edge's `trigger_count` |
| `tdc_type` | `1`–`4` as above |

Rows that arrive **before the first reference edge** have nothing to measure
from and carry `-1`, which is the sentinel `tpx3dump` itself uses in
`PixelHits/tof`.

`PixelHits`, `Clusters` and `TDCEvents` are never rewritten. An HDF5 compound
dataset has a fixed dtype, so a genuine extra field would mean recreating the
whole thing, and these files are the only copy of the measurement. Writing
beside them is additive and reversible; the GUI also stamps what it wrote and
refuses to replace a `/ClustersTDC` it did not write itself.

Cost is small: the columns are chunked and gzipped, and since `tdc` and
`tdc_trigger` are constant across a whole trigger's worth of rows they
compress well. On the ASI example file the stored columns come to 3.5 bytes
per pixel hit and 4.0 per cluster, against 23 uncompressed.

## Reading it back

**Preview frame** shows the first 40 rows of what you get. From Python, the
package is importable and the three functions take no Qt (importing
`luna_gui_wrapper` does not load PySide6 at all):

```python
import luna_gui_wrapper as g

g.read_tdcs("run.hdf5")                    # the edges, deduplicated
g.add_tdc_columns("run.hdf5", "TDC1Rising")
df = g.read_with_tdc("run.hdf5", "Clusters")
```

`read_with_tdc` returns one DataFrame: the cluster (or hit) fields plus the
TDC columns, with `tdc_type` decoded to its name and `tdc_dt_s` added in
seconds:

```
      id  size        ctoa  sum_tot  ctot   cx   cy         tdc  tdc_dt  tdc_index  tdc_trigger    tdc_type      tdc_dt_s
397  397     1  5200125000     1000  1000  147  238  5199888020  236980          0           11  TDC1Rising  2.369800e-08
398  398     1  5200218750      950   950  224  280  5199888020  330730          0           11  TDC1Rising  3.307300e-08
```

It uses the stored dataset when one is there and computes the tagging on the
fly when it is not, so it works on a file straight out of `tpx3dump`. Passing
`reference=` forces the on-the-fly path, which is how you look at a different
edge without rewriting the file.

## Reference edge

The **TDC reference** setting (the same control on both tabs) picks which
edge starts the clock, with `Any edge` tagging from the most recent edge of any
type. It is independent of `tpx3dump`'s own `--tof-tdc-reference`: that flag
makes `tpx3dump` fill `PixelHits/tof` during processing, whereas these columns
are computed afterwards and can be recomputed against a different edge whenever
you like, without reprocessing the `.tpx3`.

Where the two overlap they agree exactly. On the ASI example file, with
`--tof-tdc-reference TDC1Rising` passed and `TDC1Rising` chosen here,
`tdc_dt == tof` for all 25 762 tagged hits, and both mark the same 667 rows
unset.
