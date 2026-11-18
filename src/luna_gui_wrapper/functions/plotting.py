"""Plot constants and matplotlib styling for the Inspect tab.

Qt-free. matplotlib and komorebi_mpl are optional and imported lazily, inside
plot_style_context(), so importing this module costs nothing.
"""

from __future__ import annotations

import contextlib

# ToT is quantised -- 25 ns steps on Timepix3 (the 40 MHz reference), 0.195 ns
# on Timepix4 (see detectors.py) -- so histogram bin widths must be whole
# multiples of the step or the bins beat against the level spacing.

# Peak-pixel ToT gets one bin per step while that stays under this many bins:
# Timepix3's 10-bit ToT is at most 1023 steps, so it always does. Timepix4's
# fine step would need thousands, so it gets a whole number of steps instead.
TOT_MAX_BINS = 2000

# Clusters/sum_tot reaches ~227 us, so the native 25 ns tick would be ~9000
# bins. Snap to a whole number of ticks aiming for at most this many instead.
STOT_TARGET_BINS = 300


def tot_bin_edges(hi, lsb, max_bins, np):
    """Histogram edges for ToT values in 0..hi, all in the same unit.

    The bin width is the smallest whole number of ToT steps (`lsb`) that keeps
    the count at or below max_bins. Edges run to hi + one step, so the
    largest value lands inside the last bin instead of falling off the end.
    -> (edges, bin width)
    """
    k = max(1, int(np.ceil(hi / lsb / max_bins))) if hi > 0 else 1
    step = k * lsb
    return np.arange(0.0, hi + step, step), step

# Hitmaps: when the hottest pixel holds more than HITMAP_CLIP_FACTOR times the
# HITMAP_CLIP_PERCENTILE-th percentile of the pixels that were hit, the colour
# scale stops at that percentile, so one hot or reference pixel cannot paint
# the rest of the chip as zero. A hitmap without such outliers is unaffected.
HITMAP_CLIP_PERCENTILE = 99.9
HITMAP_CLIP_FACTOR = 5.0

# Cluster size histogram: one bin per pixel over 0..40, which is where the
# distribution lives -- anything above is counted and reported in the title
# rather than dropped without saying so.
CSIZE_MAX = 40
CSIZE_BINS = 40

# Plot styles from komorebi_mpl, one per app theme. Importing the package
# registers them with matplotlib; if it is not installed the plots fall back to
# colouring themselves from the app palette (see plot_style_context).
KOMOREBI_STYLES = {"dark": "night_wave", "light": "sci_pure"}

# Window titles for the Inspect tab's plots, so several open at once stay
# tellable apart from the taskbar.
PLOT_TITLES = {
    "hitmap": "Hitmap, pixels",
    "cmap": "Hitmap, clusters",
    "tot": "ToT, peak pixel",
    "stot": "ToT, cluster total",
    "csize": "Cluster size histogram",
    "tdc": "Time since TDC edge",
    "timewalk": "Timewalk curve",
}

# The komorebi styles are authored for a 16x10 in export figure: 30 pt text and
# 10 pt tick marks. Dropped unscaled onto the ~6.6 in on-screen canvas that is
# roughly 2.4x too large, so the point sizes get scaled by the figure-width
# ratio. Colours, cyclers and colormaps are left exactly as the style set them.
PLOT_FIGSIZE = (6.6, 5.4)
_SCALED_RC = ("font.size", "axes.titlesize", "axes.labelsize", "xtick.labelsize",
              "ytick.labelsize", "legend.fontsize", "legend.title_fontsize",
              "figure.titlesize", "figure.labelsize",
              "xtick.major.size", "ytick.major.size",
              "xtick.minor.size", "ytick.minor.size", "axes.titlepad",
              "axes.labelpad", "xtick.major.pad", "ytick.major.pad")
_MIN_PT = 4.0

# figure.frameon=False is right for an export onto a white page -- it leaves the
# figure patch undrawn so the paper shows through. On screen the canvas behind
# it is white, so a dark style renders dark text on white and is unreadable.
# The colour is already correct; it just has to actually be painted.
# axes.grid is off deliberately: these are dense hitmaps and long-tailed
# histograms, where a grid competes with the data rather than helping read it.
_ONSCREEN_FIXED = {"figure.figsize": PLOT_FIGSIZE, "figure.frameon": True,
                   "axes.grid": False}


def onscreen_overrides(style_rc):
    """Point sizes from a big-figure style, rescaled for the on-screen figure."""
    try:
        base_w = float(style_rc["figure.figsize"][0])
    except Exception:
        return {}
    if base_w <= 0:
        return {}
    k = PLOT_FIGSIZE[0] / base_w
    if 0.95 <= k <= 1.05:                  # already sized for the screen
        return dict(_ONSCREEN_FIXED)
    out = dict(_ONSCREEN_FIXED)
    for key in _SCALED_RC:
        v = style_rc.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = max(_MIN_PT, float(v) * k)
    return out


def plot_style_context(theme_name):
    """A matplotlib style context for the current app theme.

    Returns (context_manager, styled). When komorebi_mpl is missing -- it is an
    optional dependency -- this hands back a null context and False, and the
    caller paints the figure from the app palette instead, exactly as before.
    """
    name = KOMOREBI_STYLES.get(theme_name)
    if name:
        try:
            import komorebi_mpl                      # noqa: F401  registers them
            import matplotlib.pyplot as plt
            if name in plt.style.available:
                overrides = onscreen_overrides(plt.style.library[name])
                return plt.style.context([name, overrides]), True
        except Exception:
            pass
    return contextlib.nullcontext(), False
