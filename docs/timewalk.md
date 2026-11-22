# Timewalk correction

A small signal crosses the discriminator threshold later than a large one, so
a pixel's ToA depends on its own ToT. On a Timepix3Cam the faintest hits
(ToT 25 ns) arrive about 100 ns late, and the delay falls below 1 ns only
above ToT ~2 µs. For photon timing this is the largest error by far.

The GUI corrects it without a TDC or test pulses, from the clusters in the
file itself. Timepix3 and Timepix4 both work.

## How it works

All pixels of one cluster fired at the same moment, so the spread of their
ToA is timewalk plus jitter. The pixel with the largest ToT walks least.
`tpx3dump`/`tpx4dump` already report it as `ctot`, with its ToA as `ctoa`, so
it serves as the cluster's clock.

1. For every hit of a cluster with `ctot` ≥ the **ctot cut**, take
   `toa − ctoa`. The reference pixel itself is left out. This is computed
   from `toa` and `ctoa`, not read from `dtoa`: `tpx4dump` stores `dtoa` as a
   32-bit count of 1e-16 s ticks, which wraps beyond ±214 ns.
2. Per 25 ns ToT bin, the peak of that delay is found with an iterated
   3-sigma truncated mean, started at the mode. It rejects the flat
   background of hits merged into a cluster by pile-up. Unlike a median, it is
   not stuck to the 1.5625 ns ToA grid. The peak positions are the **curve**,
   delay(ToT), and the peak widths are the jitter. Bins with fewer than 200
   hits are dropped.
3. Every time is corrected by that curve, interpolated linearly between bins
   and held at both ends:

   ```
   ctoa_tw = ctoa − delay(ctot)
   toa_tw  = toa  − delay(tot)
   ```

Because each pixel is corrected on its own, the reference pixel's walk drops
out of any time difference. The curve is relative to the high-ToT limit. The
constant offset to the true arrival time needs an external reference, and it
does not matter for time differences between photons.

The first 50 M pixel hits build the curve. That takes about 10 s, and the
per-bin statistics are then in the 10⁴–10⁶ range.

## What is written

The corrected times become the **last column** of the tables Luna wrote,
so they load together with everything else:

| Where | What |
|---|---|
| `Clusters/ctoa_tw` | `ctoa` − delay(`ctot`), in `ctoa`'s ticks |
| `PixelHits/toa_tw` | `toa` − delay(`tot`), in `toa`'s ticks (only with **also every pixel hit**) |
| `/TimewalkCurve` | one row per ToT bin: `tot_ns`, `delay_ns`, `sigma_ns`, `n` |

```python
import h5py
with h5py.File("run.hdf5") as f:
    ctoa_tw = f["Clusters"]["ctoa_tw"]
    curve = f["TimewalkCurve"][:]
```

The curve's attributes record the ctot cut, the hits used, the detector, the
tick length (`seconds_per_tick`) and the method.

An HDF5 table has a fixed set of columns, so the first correction of a file
rewrites it once. It goes into a temporary file beside the original
(`NAME.hdf5.timewalk-tmp`), which replaces the original only when complete.
That needs free space for one more copy of the file, and the GUI checks for it
first. Luna's columns, chunking, compression and attributes are kept as they
were. Later runs update the column in place. If a column was added earlier,
a rerun always updates it as well, even without the per-hit option, so it
never goes stale. The GUI refuses to touch a `ctoa_tw`/`toa_tw` column it did
not add.

On the 36 M-hit laser file, the first run took 8 s and added 35 MB
(`ctoa_tw`). Adding `toa_tw` as well took 15 s and added 290 MB, 8 bytes per
hit. Without the per-hit column, `read_with_timewalk(path, "PixelHits")`
computes `toa_tw` from the stored curve, to the same values.

Files from the first version of this feature carry separate
`/ClustersTimewalk` and `/PixelHitsTimewalk` datasets instead. Correcting such
a file again converts it and drops them.

## Using it

- **Every output of a batch:** **Advanced** → **Wrapper options** → tick
  **Timewalk-correct each output .hdf5**. The row's note then ends with, for
  example, `timewalk (97 ns max)`.
- **One file:** **Inspect HDF5** → open it → **Add timewalk columns to this
  file**.
- **Trying a cut first:** **Inspect HDF5** → **Timewalk curve** plots delay
  and jitter against ToT. If the file holds a curve built with the same cut,
  the plot shows it. Otherwise the plot measures one from the first 8 M hits
  and writes nothing.

From Python, without Qt:

```python
import luna_gui_wrapper as g

g.add_timewalk_columns("run.hdf5", ctot_cut_ns=1000)   # pixel_hits=True for toa_tw
df = g.read_with_timewalk("run.hdf5", "Clusters")      # + ctoa_tw, timewalk_ns
curve = g.read_timewalk_curve("run.hdf5")
```

## Choosing the ctot cut

The reference pixel walks too, by delay(ctot). The default, 1000 ns, keeps
that below ~5 ns on a Timepix3Cam while keeping most clusters. Lower it for a
file with few bright clusters. If the curve cannot be measured, the error
says how many hits passed the cut. This setting is separate from Luna's own
`--ctot-cut`, which only affects Luna's timewalk statistics.

## What to expect

Measured on Timepix3Cam data:

| Hit ToT | Delay | Jitter (σ) |
|---|---|---|
| 25 ns | ~100 ns | ~27 ns |
| 200 ns | ~50–60 ns | ~16–21 ns |
| 1 µs | ~5 ns | ~3 ns |
| 2 µs | ~1 ns | ~1.5 ns |

Inside a cluster, correction shrinks the hit-to-reference spread from an
interquartile range of 28 ns to 7 ns. Faint hits keep their large jitter,
because the correction moves a hit's mean, not its width.

A focused spot is not needed. A dark-count run, with clusters spread over the
whole sensor, builds the curve just as well, as long as most clusters have more
than one pixel. The curve depends on the threshold and the other detector
settings, and in one dark run it differed by up to ~14 ns at mid ToT
between quarters of the chip. So it is measured per file, and one curve covers
the whole sensor.

## Luna's own timewalk tools

Luna (Timepix3 only) has `process --calculate-timewalk-statistics`, which
stores `/TimewalkMatrix` and `/TimewalkLut`, and an `apply-timewalk-correction`
subcommand. It uses the same reference-pixel idea, but takes the plain mean
delay per bin, which background tails pull. It also rewrites `toa` in place,
unless `-o` writes a second copy of the file. The two can be used side by
side: the GUI's datasets have different names.
