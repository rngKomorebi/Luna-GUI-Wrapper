"""Timepix3 and Timepix4: which Luna tool, which raw files, which units.

Luna ships one converter per detector -- tpx3dump for .tpx3, tpx4dump for
.tpx4 -- with the same `process -i ... -o ...` command line and the same
HDF5 layout (PixelHits, Clusters, ExposureTimeBoundaries, same fields). What
differs is the time base: per Luna's own "Read data, Unit Conversion"
example, ToA counts 1e-13 s on Timepix3 but 1e-16 s on Timepix4, and ToT is
whole nanoseconds (25 ns steps) on Timepix3 but the ToA tick on Timepix4.
Anything that reads times or ToT out of a file has to know which it is.

Qt-free.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Detector:
    key: str              # "tpx3" | "tpx4": settings keys, Flag.detectors
    name: str             # "Timepix3"
    exe: str              # the Luna converter's name
    suffix: str           # raw file extension
    toa_seconds: float    # one ToA / ctoa / timestamp unit, in seconds
    tot_seconds: float    # one ToT / ctot / sum_tot unit, in seconds
    tot_lsb_ns: float     # the ToT quantisation step, in ns


TPX3 = Detector("tpx3", "Timepix3", "tpx3dump", ".tpx3",
                toa_seconds=1e-13, tot_seconds=1e-9, tot_lsb_ns=25.0)
# The ToT step is what tpx4dump writes: every value in the example files is a
# multiple of 1 953 125 units of 1e-16 s.
TPX4 = Detector("tpx4", "Timepix4", "tpx4dump", ".tpx4",
                toa_seconds=1e-16, tot_seconds=1e-16, tot_lsb_ns=0.1953125)

DETECTORS = {d.key: d for d in (TPX3, TPX4)}


def field_units(det: Detector) -> dict:
    """Column -> what its numbers mean, for one detector's files."""
    if det is TPX3:
        return {
            "toa": "100 fs ticks (1e-13 s)",
            "ctoa": "100 fs ticks (1e-13 s)",
            "timestamp": "100 fs ticks (1e-13 s)",
            "tof": "100 fs ticks since the --tof-tdc-reference edge; -1 = unset",
            "tdc": "100 fs ticks, timestamp of the reference edge",
            "tdc_dt": "100 fs ticks since the reference edge; -1 = no edge yet",
            "tot": "ns, in steps of 25 ns",
            "ctot": "ns, the cluster's peak-pixel ToT",
            "sum_tot": "ns, the cluster's total ToT",
            "x": "pixel column", "y": "pixel row",
            "cx": "pixel column", "cy": "pixel row",
            "size": "pixels in the cluster",
            "tdc_type": "1 TDC1Rising, 2 TDC1Falling, 3 TDC2Rising, 4 TDC2Falling",
        }
    return {
        "toa": "100 as ticks (1e-16 s)",
        "ctoa": "100 as ticks (1e-16 s)",
        "tof": "-1: tpx4dump has no ToF option",
        "tot": "100 as ticks (1e-16 s), in steps of 0.195 ns",
        "ctot": "100 as ticks (1e-16 s), the cluster's peak-pixel ToT",
        "sum_tot": "100 as ticks (1e-16 s), the cluster's total ToT",
        "x": "pixel column, 0-447", "y": "pixel row, 0-511",
        "cx": "pixel column, 0-447", "cy": "pixel row, 0-511",
        "size": "pixels in the cluster",
    }


def detect_from_file(f, sample=100_000):
    """Which detector wrote this open h5py file? A Detector, or None.

    Decided from ToT, the one field whose scale separates the two: a Timepix3
    pixel ToT is at most 1023 x 25 ns = 25 575, while any non-zero Timepix4
    ToT is at least 1 953 125. None when the file holds no non-zero ToT to
    judge by (empty, or a --raw-only file whose ToT is all zero).
    """
    for name, field_name in (("PixelHits", "tot"), ("Clusters", "ctot")):
        if name not in f or not f[name].shape or not f[name].shape[0]:
            continue
        ds = f[name]
        if not ds.dtype.names or field_name not in ds.dtype.names:
            continue
        vals = ds[: min(sample, ds.shape[0])][field_name]
        nz = vals[vals > 0]
        if len(nz):
            return TPX4 if int(nz.max()) > 1_000_000 else TPX3
    return None
