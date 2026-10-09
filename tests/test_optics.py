import math

import pytest

from frame import optics


def test_field_of_view():
    assert optics.hfov(50) == pytest.approx(27.9, abs=0.1)
    assert optics.hfov(24) > optics.hfov(85)


@pytest.mark.parametrize("distance, lens, size", [(1.5, 50, "MCU"), (1.0, 50, "CU"), (4.0, 32, "FS"), (8, 24, "LS")])
def test_size_from_distance_and_lens(distance, lens, size):
    assert optics.size_for(distance, lens) == size


def test_distance_for_size_round_trips():
    d = optics.distance_for("MS", 35)
    assert optics.size_for(d, 35) == "MS"


def test_aliases():
    assert optics.normalise_size("ws") == "LS"
    assert optics.normalise_size("M.C.U.") == "MCU"
    assert optics.normalise_size("giant") is None


def test_projection_centre_edges_and_behind():
    cam = optics.Camera((0, 0, 1.5), (0, 10, 1.5), 50)
    assert cam.project((0, 5, 1.5)) == pytest.approx((0, 0), abs=1e-9)
    half = math.tan(math.radians(optics.hfov(50) / 2))
    assert cam.project((5 * half, 5, 1.5))[0] == pytest.approx(1.0)
    assert cam.project((0, -1, 1.5)) is None


def test_side_of_line():
    assert optics.side_of_line((0, 0), (1, 0), (0, 1)) > 0
    assert optics.side_of_line((0, 0), (1, 0), (0, -1)) < 0
