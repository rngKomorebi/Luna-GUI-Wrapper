# Dark count rate

The **DCR** page sits beside **Summary** at the bottom of the Inspect HDF5
tab. Open a file and press **Compute DCR**. One pass over every pixel hit and
every cluster counts them per pixel and per frame. That takes about 4 s for a
1.7 GB file and 17 s for a 6 GB one, with progress shown on the page. After
that, the time base and the noisy cut can be changed and the report redraws
at once, without reading the file again.

## Time base

The only real choice in a rate is what the counts are divided by. All four
time bases are computed and listed in the report; the one picked in **Time
base** is used.

| Time base | From | Notes |
|---|---|---|
| **Frames, live time from ToA** (default) | the hits | First to last hit, minus the dead gaps between frames. Needs no metadata. |
| **Frames x exposure** | `measurement_metadata.json` | `NumberOfFrames` x `ExposureTime` |
| **ToA span** | the hits | First to last hit. Counts the gaps between frames as live. |
| **Wall clock** | `measurement_metadata.json` | `StartDateTime` to `StopDateTime`. Includes start-up and readout: an upper bound. |

For a 100-frame dark run with 0.495 s frames every 0.5 s these come out as
49.4995 s, 49.5 s, 49.995 s and 51.02 s.

**How the live time is found.** Luna writes `PixelHits` sorted by ToA, so with
N frames the N-1 widest gaps between consecutive hits are the dead time
between frames. N is the number of entries in `ExposureTimeBoundaries`, or
`NumberOfFrames` from the metadata. The live time is the first-to-last span
minus those gaps. The frame breaks are trusted only when the narrowest of them
is at least 10x the next widest gap, so they stand clear of every pause
inside a frame. In a 3.7 MHz dark run the frame gaps are 18,400x the mean hit
spacing, while the widest pause inside a frame is 154x. With too few hits to
tell a frame gap from an ordinary pause, this base is reported as
unavailable.

`ExposureTimeBoundaries` holds no times. It has one cumulative row index per
frame, and these indices do not always match `PixelHits`. In one reference
file with TDC data, the last boundary is 1,881,013 rows past the end of the
table, exactly the number of `TDCEvents` rows, so the boundaries seem to count
TDC packets as well. So only their count is used.

The metadata is looked for in the folder of the `.hdf5` and the three above
it. That finds it for an output written beside its raw file
(`Measurement_.../raw/`), but usually not for one written to a separate
output folder. When the chosen base is unavailable, the next available one
is used and the report says why.

## What is reported

**Pixels** (`PixelHits`):

- total rate, mean and median per pixel, and per area (Hz/mm2 and Hz/cm2,
  55 um pixels, whole chip)
- **silent** pixels, with no hit at all: masked or dead pixels, or Poisson
  zeros when the median is only a few hits (the report warns below 10)
- **noisy** pixels, with more than k x the median hit count of the pixels that
  counted (k = 10 by default), and their share of all hits
- the hottest pixel
- **clean** rate: the noisy pixels' hits left out, and noisy and silent
  pixels left out of the area

**Clusters** (`Clusters`):

- total rate and rate per area
- clean rate, leaving out clusters whose centroid is on a noisy pixel
- mean hits per cluster and the share of single-pixel clusters

**Per frame**: the range and relative spread of the pixel and cluster rates
across frames, each frame divided by its own live time.

## Plots and export

| Button | Shows |
|---|---|
| **DCR map, pixels** | Hz per pixel; runaway pixels kept off the colour scale, as for the hitmaps |
| **DCR map, clusters** | clusters per second, by centroid pixel |
| **Per-pixel DCR histogram** | log-log, pixels that counted; median and noisy cut marked |
| **Rate vs time** | the median pixel's DCR in Hz per frame (or in 100 time bins for a single-frame file), hits and clusters in two panels |

**The median per frame.** The median is taken over the pixels that counted
at least once in the whole run, so the same pixels are used in every frame.
A pixel holds only a few tens of counts per frame (about 30 for 60 Hz in
0.495 s), so a plain median moves in whole counts. That is a staircase of
about 3 %, which would hide a drift of a few tenths of a percent. The
plotted median is instead interpolated within the middle count: each
integer v is treated as the interval [v - 0.5, v + 0.5), as for grouped
data, and the result equals v when every count is v.

The per-frame maps are built in the same pass as everything else. A new map
starts at every ToA gap wider than 1000x the running mean hit spacing, and
the pieces are merged into frames once the frame gaps are known. Above 32 M
map cells (about 490 Timepix3 frames) they are skipped. When the medians
are unavailable, the plot shows the mean per pixel and says why.

**Export CSV...** writes one row per pixel: `x, y, hits, hit_rate_hz,
clusters, cluster_rate_hz, noisy, silent`, with the time base and the noisy
cut in the header.

## From Python

The calculation is Qt-free:

```python
import h5py
from luna_gui_wrapper.functions import dcr
from luna_gui_wrapper.functions.detectors import detect_from_file

path = "run.hdf5"
with h5py.File(path, "r") as f:
    counts = dcr.measure_dcr(f, detect_from_file(f),
                             dcr.find_measurement_metadata(path))
lines, maps = dcr.dcr_report(counts, "frames_toa", noisy_k=10)
print("\n".join(lines))
```
