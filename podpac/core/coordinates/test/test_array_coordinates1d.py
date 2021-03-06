from datetime import datetime
import json

import pytest
import traitlets as tl
import numpy as np
import xarray as xr
from numpy.testing import assert_equal

import podpac
from podpac.core.coordinates.utils import make_coord_array
from podpac.core.coordinates.array_coordinates1d import ArrayCoordinates1d
from podpac.core.coordinates.uniform_coordinates1d import UniformCoordinates1d
from podpac.core.coordinates.stacked_coordinates import StackedCoordinates
from podpac.core.coordinates.coordinates import Coordinates


class TestArrayCoordinatesInit(object):
    def test_empty(self):
        c = ArrayCoordinates1d([])
        a = np.array([], dtype=float)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [np.nan, np.nan])
        assert c.size == 0
        assert c.shape == (0,)
        assert c.dtype is None
        assert c.is_monotonic is None
        assert c.is_descending is None
        assert c.is_uniform is None
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

    def test_numerical_singleton(self):
        a = np.array([10], dtype=float)
        c = ArrayCoordinates1d(10)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [10.0, 10.0])
        assert c.size == 1
        assert c.shape == (1,)
        assert c.dtype == float
        assert c.is_monotonic == True
        assert c.is_descending is None
        assert c.is_uniform is None
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

    def test_numerical_array(self):
        # unsorted
        values = [1, 6, 0, 4.0]
        a = np.array(values, dtype=float)
        c = ArrayCoordinates1d(a)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [0.0, 6.0])
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == float
        assert c.is_monotonic == False
        assert c.is_descending is False
        assert c.is_uniform == False
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

        # sorted ascending
        values = [0, 1, 4, 6]
        a = np.array(values, dtype=float)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [0.0, 6.0])
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == float
        assert c.is_monotonic == True
        assert c.is_descending == False
        assert c.is_uniform == False
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

        # sorted descending
        values = [6, 4, 1, 0]
        a = np.array(values, dtype=float)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [0.0, 6.0])
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == float
        assert c.is_monotonic == True
        assert c.is_descending == True
        assert c.is_uniform == False
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

        # uniform ascending
        values = [0, 2, 4, 6]
        a = np.array(values, dtype=float)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [0.0, 6.0])
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == float
        assert c.is_monotonic == True
        assert c.is_descending == False
        assert c.is_uniform == True
        assert c.start == 0.0
        assert c.stop == 6.0
        assert c.step == 2
        repr(c)

        # uniform descending
        values = [6, 4, 2, 0]
        a = np.array(values, dtype=float)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, [0.0, 6.0])
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == float
        assert c.is_monotonic == True
        assert c.is_descending == True
        assert c.is_uniform == True
        assert c.start == 6.0
        assert c.stop == 0.0
        assert c.step == -2
        repr(c)

    def test_datetime_singleton(self):
        a = np.array("2018-01-01").astype(np.datetime64)
        c = ArrayCoordinates1d("2018-01-01")
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, np.array(["2018-01-01", "2018-01-01"]).astype(np.datetime64))
        assert c.size == 1
        assert c.shape == (1,)
        assert c.dtype == np.datetime64
        assert c.is_monotonic == True
        assert c.is_descending is None
        assert c.is_uniform is None
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

    def test_datetime_array(self):
        # unsorted
        values = ["2018-01-01", "2019-01-01", "2017-01-01", "2018-01-02"]
        a = np.array(values).astype(np.datetime64)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, np.array(["2017-01-01", "2019-01-01"]).astype(np.datetime64))
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == np.datetime64
        assert c.is_monotonic == False
        assert c.is_descending == False
        assert c.is_uniform == False
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

        # sorted ascending
        values = ["2017-01-01", "2018-01-01", "2018-01-02", "2019-01-01"]
        a = np.array(values).astype(np.datetime64)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, np.array(["2017-01-01", "2019-01-01"]).astype(np.datetime64))
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == np.datetime64
        assert c.is_monotonic == True
        assert c.is_descending == False
        assert c.is_uniform == False
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

        # sorted descending
        values = ["2019-01-01", "2018-01-02", "2018-01-01", "2017-01-01"]
        a = np.array(values).astype(np.datetime64)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, np.array(["2017-01-01", "2019-01-01"]).astype(np.datetime64))
        assert c.size == 4
        assert c.shape == (4,)
        assert c.dtype == np.datetime64
        assert c.is_monotonic == True
        assert c.is_descending == True
        assert c.is_uniform == False
        assert c.start is None
        assert c.stop is None
        assert c.step is None
        repr(c)

        # uniform ascending
        values = ["2017-01-01", "2018-01-01", "2019-01-01"]
        a = np.array(values).astype(np.datetime64)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, np.array(["2017-01-01", "2019-01-01"]).astype(np.datetime64))
        assert c.size == 3
        assert c.shape == (3,)
        assert c.dtype == np.datetime64
        assert c.is_monotonic == True
        assert c.is_descending == False
        assert c.is_uniform == True
        assert c.start == np.datetime64("2017-01-01")
        assert c.stop == np.datetime64("2019-01-01")
        assert c.step == np.timedelta64(365, "D")
        repr(c)

        # uniform descending
        values = ["2019-01-01", "2018-01-01", "2017-01-01"]
        a = np.array(values).astype(np.datetime64)
        c = ArrayCoordinates1d(values)
        assert_equal(c.coordinates, a)
        assert_equal(c.bounds, np.array(["2017-01-01", "2019-01-01"]).astype(np.datetime64))
        assert c.size == 3
        assert c.shape == (3,)
        assert c.dtype == np.datetime64
        assert c.is_monotonic == True
        assert c.is_descending == True
        assert c.is_uniform == True
        assert c.start == np.datetime64("2019-01-01")
        assert c.stop == np.datetime64("2017-01-01")
        assert c.step == np.timedelta64(-365, "D")
        repr(c)

    def test_invalid_coords(self):
        with pytest.raises(ValueError, match="Invalid coordinate values"):
            ArrayCoordinates1d([1, 2, "2018-01"])

        with pytest.raises(ValueError, match="Invalid coordinate values"):
            ArrayCoordinates1d([[1.0, 2.0], [3.0, 4.0]])

    def test_from_xarray(self):
        # numerical
        x = xr.DataArray([0, 1, 2], name="lat")
        c = ArrayCoordinates1d.from_xarray(x)
        assert c.name == "lat"
        assert_equal(c.coordinates, x.data)

        # datetime
        x = xr.DataArray([np.datetime64("2018-01-01"), np.datetime64("2018-01-02")], name="time")
        c = ArrayCoordinates1d.from_xarray(x)
        assert c.name == "time"
        assert_equal(c.coordinates, x.data)

        # unnamed
        x = xr.DataArray([0, 1, 2])
        c = ArrayCoordinates1d.from_xarray(x)
        assert c.name is None

    def test_copy(self):
        c = ArrayCoordinates1d([1, 2, 3], name="lat")
        c2 = c.copy()
        assert c is not c2
        assert c == c2

    def test_name(self):
        ArrayCoordinates1d([])
        ArrayCoordinates1d([], name="lat")
        ArrayCoordinates1d([], name="lon")
        ArrayCoordinates1d([], name="alt")
        ArrayCoordinates1d([], name="time")

        with pytest.raises(tl.TraitError):
            ArrayCoordinates1d([], name="depth")

        repr(ArrayCoordinates1d([], name="lat"))

    def test_set_name(self):
        # set if not already set
        c = ArrayCoordinates1d([])
        c._set_name("lat")
        assert c.name == "lat"

        # check if set already
        c = ArrayCoordinates1d([], name="lat")
        c._set_name("lat")
        assert c.name == "lat"

        with pytest.raises(ValueError, match="Dimension mismatch"):
            c._set_name("lon")

        # invalid name
        c = ArrayCoordinates1d([])
        with pytest.raises(tl.TraitError):
            c._set_name("depth")


class TestArrayCoordinatesEq(object):
    def test_eq_type(self):
        c1 = ArrayCoordinates1d([0, 1, 3])
        assert c1 != [0, 1, 3]

    def test_eq_coordinates(self):
        c1 = ArrayCoordinates1d([0, 1, 3])
        c2 = ArrayCoordinates1d([0, 1, 3])
        c3 = ArrayCoordinates1d([0, 1, 3, 4])
        c4 = ArrayCoordinates1d([0, 1, 4])
        c5 = ArrayCoordinates1d([0, 3, 1])

        assert c1 == c2
        assert not c1 == c3
        assert not c1 == c4
        assert not c1 == c5

        c1 = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-04"])
        c2 = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-04"])
        c3 = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-04", "2018-01-05"])
        c4 = ArrayCoordinates1d(["2018-01-01", "2018-01-04", "2018-01-02"])

        assert c1 == c2
        assert not c1 == c3
        assert not c1 == c4

    def test_ne(self):
        # this matters in python 2
        c1 = ArrayCoordinates1d([0, 1, 3])
        c2 = ArrayCoordinates1d([0, 1, 3])
        c3 = ArrayCoordinates1d([0, 1, 3, 4])
        c4 = ArrayCoordinates1d([0, 1, 4])
        c5 = ArrayCoordinates1d([0, 3, 1])

        assert not c1 != c2
        assert c1 != c3
        assert c1 != c4
        assert c1 != c5

        c1 = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-04"])
        c2 = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-04"])
        c3 = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-04", "2018-01-05"])
        c4 = ArrayCoordinates1d(["2018-01-01", "2018-01-04", "2018-01-02"])

        assert not c1 != c2
        assert c1 != c3
        assert c1 != c4

    def test_eq_name(self):
        c1 = ArrayCoordinates1d([0, 1, 3], name="lat")
        c2 = ArrayCoordinates1d([0, 1, 3], name="lat")
        c3 = ArrayCoordinates1d([0, 1, 3], name="lon")
        c4 = ArrayCoordinates1d([0, 1, 3])

        assert c1 == c2
        assert c1 != c3
        assert c1 != c4

        c4.name = "lat"
        assert c1 == c4


class TestArrayCoordinatesSerialization(object):
    def test_definition(self):
        # numerical
        c = ArrayCoordinates1d([0, 1, 2], name="lat")
        d = c.definition
        assert isinstance(d, dict)
        assert set(d.keys()) == {"values", "name"}
        json.dumps(d, cls=podpac.core.utils.JSONEncoder)  # test serializable
        c2 = ArrayCoordinates1d.from_definition(d)  # test from_definition
        assert c2 == c

        # datetimes
        c = ArrayCoordinates1d(["2018-01-01", "2018-01-02"])
        d = c.definition
        assert isinstance(d, dict)
        assert set(d.keys()) == {"values"}
        json.dumps(d, cls=podpac.core.utils.JSONEncoder)  # test serializable
        c2 = ArrayCoordinates1d.from_definition(d)  # test from_definition
        assert c2 == c


class TestArrayCoordinatesProperties(object):
    def test_dims(self):
        c = ArrayCoordinates1d([], name="lat")
        assert c.dims == ("lat",)
        assert c.udims == ("lat",)
        assert c.idims == ("lat",)

        c = ArrayCoordinates1d([])
        with pytest.raises(TypeError, match="cannot access dims property of unnamed Coordinates1d"):
            c.dims

        with pytest.raises(TypeError, match="cannot access dims property of unnamed Coordinates1d"):
            c.udims

        with pytest.raises(TypeError, match="cannot access dims property of unnamed Coordinates1d"):
            c.idims

    def test_properties(self):
        c = ArrayCoordinates1d([])
        assert isinstance(c.properties, dict)
        assert set(c.properties) == set()

        c = ArrayCoordinates1d([], name="lat")
        assert isinstance(c.properties, dict)
        assert set(c.properties) == {"name"}

    def test_coords(self):
        c = ArrayCoordinates1d([1, 2], name="lat")
        coords = c.coords
        assert isinstance(coords, dict)
        assert set(coords) == {"lat"}
        assert_equal(coords["lat"], c.coordinates)


class TestArrayCoordinatesIndexing(object):
    def test_len(self):
        c = ArrayCoordinates1d([])
        assert len(c) == 0

        c = ArrayCoordinates1d([0, 1, 2])
        assert len(c) == 3

    def test_index(self):
        c = ArrayCoordinates1d([20, 50, 60, 90, 40, 10], name="lat")

        # int
        c2 = c[2]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [60])

        c2 = c[-2]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [40])

        # slice
        c2 = c[:2]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [20, 50])

        c2 = c[::2]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [20, 60, 40])

        c2 = c[1:-1]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [50, 60, 90, 40])

        c2 = c[::-1]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [10, 40, 90, 60, 50, 20])

        # array
        c2 = c[[0, 3, 1]]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [20, 90, 50])

        # boolean array
        c2 = c[[True, True, True, False, True, False]]
        assert isinstance(c2, ArrayCoordinates1d)
        assert c2.name == c.name
        assert c2.properties == c.properties
        assert_equal(c2.coordinates, [20, 50, 60, 40])

        # invalid
        with pytest.raises(IndexError):
            c[0.3]

        with pytest.raises(IndexError):
            c[10]


class TestArrayCoordinatesAreaBounds(object):
    def test_get_area_bounds_numerical(self):
        values = np.array([0.0, 1.0, 4.0, 6.0])
        c = ArrayCoordinates1d(values)

        # point
        area_bounds = c.get_area_bounds(None)
        assert_equal(area_bounds, [0.0, 6.0])

        # uniform
        area_bounds = c.get_area_bounds(0.5)
        assert_equal(area_bounds, [-0.5, 6.5])

        # segment
        area_bounds = c.get_area_bounds([-0.2, 0.7])
        assert_equal(area_bounds, [-0.2, 6.7])

        # polygon (i.e. there would be corresponding offets for another dimension)
        area_bounds = c.get_area_bounds([-0.2, -0.5, 0.7, 0.5])
        assert_equal(area_bounds, [-0.5, 6.7])

        # boundaries
        area_bounds = c.get_area_bounds([[-0.4, 0.1], [-0.3, 0.2], [-0.2, 0.3], [-0.1, 0.4]])
        assert_equal(area_bounds, [-0.4, 6.4])

    def test_get_area_bounds_datetime(self):
        values = make_coord_array(["2017-01-02", "2017-01-01", "2019-01-01", "2018-01-01"])
        c = ArrayCoordinates1d(values)

        # point
        area_bounds = c.get_area_bounds(None)
        assert_equal(area_bounds, make_coord_array(["2017-01-01", "2019-01-01"]))

        # uniform
        area_bounds = c.get_area_bounds("1,D")
        assert_equal(area_bounds, make_coord_array(["2016-12-31", "2019-01-02"]))

        area_bounds = c.get_area_bounds("1,M")
        assert_equal(area_bounds, make_coord_array(["2016-12-01", "2019-02-01"]))

        area_bounds = c.get_area_bounds("1,Y")
        assert_equal(area_bounds, make_coord_array(["2016-01-01", "2020-01-01"]))

        # segment
        area_bounds = c.get_area_bounds(["0,h", "12,h"])
        assert_equal(area_bounds, make_coord_array(["2017-01-01 00:00", "2019-01-01 12:00"]))

    def test_get_area_bounds_empty(self):
        c = ArrayCoordinates1d([])
        area_bounds = c.get_area_bounds(1.0)
        assert np.all(np.isnan(area_bounds))

    @pytest.mark.xfail(reason="spec uncertain")
    def test_get_area_bounds_overlapping(self):
        values = np.array([0.0, 1.0, 4.0, 6.0])
        c = ArrayCoordinates1d(values)

        area_bounds = c.get_area_bounds([[-0.1, 0.1], [-10.0, 10.0], [-0.1, 0.1], [-0.1, 0.1]])
        assert_equal(area_bounds, [-11.0, 11.0])


class TestArrayCoordinatesSelection(object):
    def test_select_empty_shortcut(self):
        c = ArrayCoordinates1d([])
        bounds = [0, 1]

        s = c.select(bounds)
        assert_equal(s.coordinates, [])

        s, I = c.select(bounds, return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

    def test_select_all_shortcut(self):
        c = ArrayCoordinates1d([20.0, 50.0, 60.0, 90.0, 40.0, 10.0])
        bounds = [0, 100]

        s = c.select(bounds)
        assert_equal(s.coordinates, c.coordinates)

        s, I = c.select(bounds, return_indices=True)
        assert_equal(s.coordinates, c.coordinates)
        assert_equal(c.coordinates[I], c.coordinates)

    def test_select_none_shortcut(self):
        c = ArrayCoordinates1d([20.0, 50.0, 60.0, 90.0, 40.0, 10.0])

        # above
        s = c.select([100, 200])
        assert_equal(s.coordinates, [])

        s, I = c.select([100, 200], return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

        # below
        s = c.select([0, 5])
        assert_equal(s.coordinates, [])

        s, I = c.select([0, 5], return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

    def test_select(self):
        c = ArrayCoordinates1d([20.0, 50.0, 60.0, 90.0, 40.0, 10.0])

        # inner
        s = c.select([30.0, 55.0])
        assert_equal(s.coordinates, [50.0, 40.0])

        s, I = c.select([30.0, 55.0], return_indices=True)
        assert_equal(s.coordinates, [50.0, 40.0])
        assert_equal(c.coordinates[I], [50.0, 40.0])

        # inner with aligned bounds
        s = c.select([40.0, 60.0])
        assert_equal(s.coordinates, [50.0, 60.0, 40.0])

        s, I = c.select([40.0, 60.0], return_indices=True)
        assert_equal(s.coordinates, [50.0, 60.0, 40.0])
        assert_equal(c.coordinates[I], [50.0, 60.0, 40.0])

        # above
        s = c.select([50, 100])
        assert_equal(s.coordinates, [50.0, 60.0, 90.0])

        s, I = c.select([50, 100], return_indices=True)
        assert_equal(s.coordinates, [50.0, 60.0, 90.0])
        assert_equal(c.coordinates[I], [50.0, 60.0, 90.0])

        # below
        s = c.select([0, 50])
        assert_equal(s.coordinates, [20.0, 50.0, 40.0, 10.0])

        s, I = c.select([0, 50], return_indices=True)
        assert_equal(s.coordinates, [20.0, 50.0, 40.0, 10.0])
        assert_equal(c.coordinates[I], [20.0, 50.0, 40.0, 10.0])

        # between coordinates
        s = c.select([52, 55])
        assert_equal(s.coordinates, [])

        s, I = c.select([52, 55], return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

        # backwards bounds
        s = c.select([70, 30])
        assert_equal(s.coordinates, [])

        s, I = c.select([70, 30], return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

    def test_select_outer_ascending(self):
        c = ArrayCoordinates1d([10.0, 20.0, 40.0, 50.0, 60.0, 90.0])

        # inner
        s = c.select([30.0, 55.0], outer=True)
        assert_equal(s.coordinates, [20, 40.0, 50.0, 60.0])

        s, I = c.select([30.0, 55.0], outer=True, return_indices=True)
        assert_equal(s.coordinates, [20, 40.0, 50.0, 60.0])
        assert_equal(c.coordinates[I], [20, 40.0, 50.0, 60.0])

        # inner with aligned bounds
        s = c.select([40.0, 60.0], outer=True)
        assert_equal(s.coordinates, [40.0, 50.0, 60.0])

        s, I = c.select([40.0, 60.0], outer=True, return_indices=True)
        assert_equal(s.coordinates, [40.0, 50.0, 60.0])
        assert_equal(c.coordinates[I], [40.0, 50.0, 60.0])

        # above
        s = c.select([50, 100], outer=True)
        assert_equal(s.coordinates, [50.0, 60.0, 90.0])

        s, I = c.select([50, 100], outer=True, return_indices=True)
        assert_equal(s.coordinates, [50.0, 60.0, 90.0])
        assert_equal(c.coordinates[I], [50.0, 60.0, 90.0])

        # below
        s = c.select([0, 50], outer=True)
        assert_equal(s.coordinates, [10.0, 20.0, 40.0, 50.0])

        s, I = c.select([0, 50], outer=True, return_indices=True)
        assert_equal(s.coordinates, [10.0, 20.0, 40.0, 50.0])
        assert_equal(c.coordinates[I], [10.0, 20.0, 40.0, 50.0])

        # between coordinates
        s = c.select([52, 55], outer=True)
        assert_equal(s.coordinates, [50, 60])

        s, I = c.select([52, 55], outer=True, return_indices=True)
        assert_equal(s.coordinates, [50, 60])
        assert_equal(c.coordinates[I], [50, 60])

        # backwards bounds
        s = c.select([70, 30], outer=True)
        assert_equal(s.coordinates, [])

        s, I = c.select([70, 30], outer=True, return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

    def test_select_outer_descending(self):
        c = ArrayCoordinates1d([90.0, 60.0, 50.0, 40.0, 20.0, 10.0])

        # inner
        s = c.select([30.0, 55.0], outer=True)
        assert_equal(s.coordinates, [60.0, 50.0, 40.0, 20.0])

        s, I = c.select([30.0, 55.0], outer=True, return_indices=True)
        assert_equal(s.coordinates, [60.0, 50.0, 40.0, 20.0])
        assert_equal(c.coordinates[I], [60.0, 50.0, 40.0, 20.0])

        # inner with aligned bounds
        s = c.select([40.0, 60.0], outer=True)
        assert_equal(s.coordinates, [60.0, 50.0, 40.0])

        s, I = c.select([40.0, 60.0], outer=True, return_indices=True)
        assert_equal(s.coordinates, [60.0, 50.0, 40.0])
        assert_equal(c.coordinates[I], [60.0, 50.0, 40.0])

        # above
        s = c.select([50, 100], outer=True)
        assert_equal(s.coordinates, [90.0, 60.0, 50.0])

        s, I = c.select([50, 100], outer=True, return_indices=True)
        assert_equal(s.coordinates, [90.0, 60.0, 50.0])
        assert_equal(c.coordinates[I], [90.0, 60.0, 50.0])

        # below
        s = c.select([0, 50], outer=True)
        assert_equal(s.coordinates, [50.0, 40.0, 20.0, 10.0])

        s, I = c.select([0, 50], outer=True, return_indices=True)
        assert_equal(s.coordinates, [50.0, 40.0, 20.0, 10.0])
        assert_equal(c.coordinates[I], [50.0, 40.0, 20.0, 10.0])

        # between coordinates
        s = c.select([52, 55], outer=True)
        assert_equal(s.coordinates, [60, 50])

        s, I = c.select([52, 55], outer=True, return_indices=True)
        assert_equal(s.coordinates, [60, 50])
        assert_equal(c.coordinates[I], [60, 50])

        # backwards bounds
        s = c.select([70, 30], outer=True)
        assert_equal(s.coordinates, [])

        s, I = c.select([70, 30], outer=True, return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

    def test_select_outer_nonmonotonic(self):
        c = ArrayCoordinates1d([20.0, 40.0, 60.0, 10.0, 90.0, 50.0])

        # inner
        s = c.select([30.0, 55.0], outer=True)
        assert_equal(s.coordinates, [20, 40.0, 60.0, 50.0])

        s, I = c.select([30.0, 55.0], outer=True, return_indices=True)
        assert_equal(s.coordinates, [20, 40.0, 60.0, 50.0])
        assert_equal(c.coordinates[I], [20, 40.0, 60.0, 50.0])

        # inner with aligned bounds
        s = c.select([40.0, 60.0], outer=True)
        assert_equal(s.coordinates, [40.0, 60.0, 50.0])

        s, I = c.select([40.0, 60.0], outer=True, return_indices=True)
        assert_equal(s.coordinates, [40.0, 60.0, 50.0])
        assert_equal(c.coordinates[I], [40.0, 60.0, 50.0])

        # above
        s = c.select([50, 100], outer=True)
        assert_equal(s.coordinates, [60.0, 90.0, 50.0])

        s, I = c.select([50, 100], outer=True, return_indices=True)
        assert_equal(s.coordinates, [60.0, 90.0, 50.0])
        assert_equal(c.coordinates[I], [60.0, 90.0, 50.0])

        # below
        s = c.select([0, 50], outer=True)
        assert_equal(s.coordinates, [20.0, 40.0, 10.0, 50.0])

        s, I = c.select([0, 50], outer=True, return_indices=True)
        assert_equal(s.coordinates, [20.0, 40.0, 10.0, 50.0])
        assert_equal(c.coordinates[I], [20.0, 40.0, 10.0, 50.0])

        # between coordinates
        s = c.select([52, 55], outer=True)
        assert_equal(s.coordinates, [60, 50])

        s, I = c.select([52, 55], outer=True, return_indices=True)
        assert_equal(s.coordinates, [60, 50])
        assert_equal(c.coordinates[I], [60, 50])

        # backwards bounds
        s = c.select([70, 30], outer=True)
        assert_equal(s.coordinates, [])

        s, I = c.select([70, 30], outer=True, return_indices=True)
        assert_equal(s.coordinates, [])
        assert_equal(c.coordinates[I], [])

    def test_select_dict(self):
        c = ArrayCoordinates1d([20.0, 40.0, 60.0, 10.0, 90.0, 50.0], name="lat")

        s = c.select({"lat": [30.0, 55.0]})
        assert_equal(s.coordinates, [40.0, 50.0])

        s = c.select({"lon": [30.0, 55]})
        assert s == c

    def test_select_time(self):
        c = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-03", "2018-01-04"], name="time")
        s = c.select({"time": [np.datetime64("2018-01-03"), "2018-02-06"]})
        assert_equal(s.coordinates, np.array(["2018-01-03", "2018-01-04"]).astype(np.datetime64))

    def test_select_time_variable_precision(self):
        c = ArrayCoordinates1d(["2012-05-19"], name="time")
        c2 = ArrayCoordinates1d(["2012-05-19T12:00:00"], name="time")
        s = c.select(c2.bounds, outer=True)
        s1 = c.select(c2.bounds, outer=False)
        s2 = c2.select(c.bounds)
        assert s.size == 1
        assert s1.size == 0
        assert s2.size == 1

    def test_select_dtype(self):
        c = ArrayCoordinates1d([20.0, 40.0, 60.0, 10.0, 90.0, 50.0], name="lat")
        with pytest.raises(TypeError):
            c.select({"lat": [np.datetime64("2018-01-01"), "2018-02-01"]})

        c = ArrayCoordinates1d(["2018-01-01", "2018-01-02", "2018-01-03", "2018-01-04"], name="time")
        with pytest.raises(TypeError):
            c.select({"time": [1, 10]})
