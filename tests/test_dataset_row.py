"""The Inspect tab's Datasets table rows: rows, field names, chunks."""

import pytest

from luna_gui_wrapper.functions.common import dataset_row

np = pytest.importorskip("numpy")


class Stand:
    """What dataset_row reads off an h5py Dataset."""

    def __init__(self, shape, dtype, chunks):
        self.shape, self.dtype, self.chunks = shape, np.dtype(dtype), chunks


def test_a_table_shows_its_length_and_field_names():
    row = dataset_row("Clusters", Stand((3931291,), [("id", "<i8"), ("ctoa", "<u8")],
                                        (15000,)))
    assert [t for t, _tip in row] == ["Clusters", "3,931,291", "id, ctoa", "15,000"]
    assert "ctoa" in row[2][1] and "<u8" in row[2][1]     # full dtype as tooltip


def test_a_plain_array_shows_its_dtype_and_no_chunks():
    row = dataset_row("ExposureTimeBoundaries", Stand((10,), "uint64", None))
    assert [t for t, _tip in row] == ["ExposureTimeBoundaries", "10", "uint64", "-"]


def test_two_d_and_scalar_shapes():
    assert dataset_row("img", Stand((256, 256), "<f8", (64, 64)))[1][0] == "256 x 256"
    assert dataset_row("img", Stand((256, 256), "<f8", (64, 64)))[3][0] == "64 x 64"
    assert dataset_row("v", Stand((), "<f8", None))[1][0] == "scalar"
