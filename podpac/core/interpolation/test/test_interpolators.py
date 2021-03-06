"""
Test interpolation methods


"""
# pylint: disable=C0111,W0212,R0903

import pytest
import traitlets as tl
import numpy as np

from podpac.core.utils import ArrayTrait
from podpac.core.units import UnitsDataArray
from podpac.core.coordinates import Coordinates, clinspace
from podpac.core.data.rasterio_source import rasterio
from podpac.core.data.datasource import DataSource
from podpac.core.interpolation.interpolation import Interpolation, InterpolationException
from podpac.core.interpolation.interpolators import NearestNeighbor, NearestPreview, Rasterio, ScipyGrid, ScipyPoint


class MockArrayDataSource(DataSource):
    data = ArrayTrait().tag(attr=True)
    coordinates = tl.Instance(Coordinates).tag(attr=True)

    def get_data(self, coordinates, coordinates_index):
        return self.create_output_array(coordinates, data=self.data[coordinates_index])


class TestNearest(object):
    def test_nearest_preview_select(self):

        # test straight ahead functionality
        reqcoords = Coordinates([[-0.5, 1.5, 3.5], [0.5, 2.5, 4.5]], dims=["lat", "lon"])
        srccoords = Coordinates([[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]], dims=["lat", "lon"])

        interp = Interpolation("nearest_preview")

        srccoords, srccoords_index = srccoords.intersect(reqcoords, outer=True, return_indices=True)
        coords, cidx = interp.select_coordinates(srccoords, srccoords_index, reqcoords)

        assert len(coords) == len(srccoords) == len(cidx)
        assert len(coords["lat"]) == len(reqcoords["lat"])
        assert len(coords["lon"]) == len(reqcoords["lon"])
        assert np.all(coords["lat"].coordinates == np.array([0, 2, 4]))

        # test when selection is applied serially
        # this is equivalent to above
        reqcoords = Coordinates([[-0.5, 1.5, 3.5], [0.5, 2.5, 4.5]], dims=["lat", "lon"])
        srccoords = Coordinates([[0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5]], dims=["lat", "lon"])

        interp = Interpolation(
            [{"method": "nearest_preview", "dims": ["lat"]}, {"method": "nearest_preview", "dims": ["lon"]}]
        )

        srccoords, srccoords_index = srccoords.intersect(reqcoords, outer=True, return_indices=True)
        coords, cidx = interp.select_coordinates(srccoords, srccoords_index, reqcoords)

        assert len(coords) == len(srccoords) == len(cidx)
        assert len(coords["lat"]) == len(reqcoords["lat"])
        assert len(coords["lon"]) == len(reqcoords["lon"])
        assert np.all(coords["lat"].coordinates == np.array([0, 2, 4]))

        # test when coordinates are stacked and unstacked
        # TODO: how to handle stacked/unstacked coordinate asynchrony?
        # reqcoords = Coordinates([[-.5, 1.5, 3.5], [.5, 2.5, 4.5]], dims=['lat', 'lon'])
        # srccoords = Coordinates([([0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5])], dims=['lat_lon'])

        # interp = Interpolation('nearest_preview')

        # srccoords, srccoords_index = srccoords.intersect(reqcoords, outer=True, return_indices=True)
        # coords, cidx = interp.select_coordinates(reqcoords, srccoords, srccoords_index)

        # assert len(coords) == len(srcoords) == len(cidx)
        # assert len(coords['lat']) == len(reqcoords['lat'])
        # assert len(coords['lon']) == len(reqcoords['lon'])
        # assert np.all(coords['lat'].coordinates == np.array([0, 2, 4]))

    def test_interpolation(self):

        for interpolation in ["nearest", "nearest_preview"]:

            # unstacked 1D
            source = np.random.rand(5)
            coords_src = Coordinates([np.linspace(0, 10, 5)], dims=["lat"])
            node = MockArrayDataSource(data=source, coordinates=coords_src, interpolation=interpolation)

            coords_dst = Coordinates([[1, 1.2, 1.5, 5, 9]], dims=["lat"])
            output = node.eval(coords_dst)

            assert isinstance(output, UnitsDataArray)
            assert np.all(output.lat.values == coords_dst.coords["lat"])
            assert output.values[0] == source[0] and output.values[1] == source[0] and output.values[2] == source[1]

            # unstacked N-D
            source = np.random.rand(5, 5)
            coords_src = Coordinates([clinspace(0, 10, 5), clinspace(0, 10, 5)], dims=["lat", "lon"])
            coords_dst = Coordinates([clinspace(2, 12, 5), clinspace(2, 12, 5)], dims=["lat", "lon"])

            node = MockArrayDataSource(data=source, coordinates=coords_src, interpolation=interpolation)
            output = node.eval(coords_dst)

            assert isinstance(output, UnitsDataArray)
            assert np.all(output.lat.values == coords_dst.coords["lat"])
            assert output.values[0, 0] == source[1, 1]

            # stacked
            # TODO: implement stacked handling
            source = np.random.rand(5)
            coords_src = Coordinates([(np.linspace(0, 10, 5), np.linspace(0, 10, 5))], dims=["lat_lon"])
            node = MockArrayDataSource(
                data=source,
                coordinates=coords_src,
                interpolation={"method": "nearest", "interpolators": [NearestNeighbor]},
            )
            coords_dst = Coordinates([(np.linspace(1, 9, 3), np.linspace(1, 9, 3))], dims=["lat_lon"])

            with pytest.raises(InterpolationException):
                output = node.eval(coords_dst)

            # TODO: implement stacked handling
            # source = stacked, dest = unstacked
            source = np.random.rand(5)
            coords_src = Coordinates([(np.linspace(0, 10, 5), np.linspace(0, 10, 5))], dims=["lat_lon"])
            node = MockArrayDataSource(
                data=source,
                coordinates=coords_src,
                interpolation={"method": "nearest", "interpolators": [NearestNeighbor]},
            )
            coords_dst = Coordinates([np.linspace(1, 9, 3), np.linspace(1, 9, 3)], dims=["lat", "lon"])

            with pytest.raises(InterpolationException):
                output = node.eval(coords_dst)

            # TODO: implement stacked handling
            # source = unstacked, dest = stacked
            source = np.random.rand(5, 5)
            coords_src = Coordinates([np.linspace(0, 10, 5), np.linspace(0, 10, 5)], dims=["lat", "lon"])
            node = MockArrayDataSource(
                data=source,
                coordinates=coords_src,
                interpolation={"method": "nearest", "interpolators": [NearestNeighbor]},
            )
            coords_dst = Coordinates([(np.linspace(1, 9, 3), np.linspace(1, 9, 3))], dims=["lat_lon"])

            with pytest.raises(InterpolationException):
                output = node.eval(coords_dst)

    def test_spatial_tolerance(self):

        # unstacked 1D
        source = np.random.rand(5)
        coords_src = Coordinates([np.linspace(0, 10, 5)], dims=["lat"])
        node = MockArrayDataSource(
            data=source,
            coordinates=coords_src,
            interpolation={"method": "nearest", "params": {"spatial_tolerance": 1.1}},
        )

        coords_dst = Coordinates([[1, 1.2, 1.5, 5, 9]], dims=["lat"])
        output = node.eval(coords_dst)

        print(output)
        print(source)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert output.values[0] == source[0] and np.isnan(output.values[1]) and output.values[2] == source[1]

    def test_time_tolerance(self):

        # unstacked 1D
        source = np.random.rand(5, 5)
        coords_src = Coordinates(
            [np.linspace(0, 10, 5), clinspace("2018-01-01", "2018-01-09", 5)], dims=["lat", "time"]
        )
        node = MockArrayDataSource(
            data=source,
            coordinates=coords_src,
            interpolation={
                "method": "nearest",
                "params": {"spatial_tolerance": 1.1, "time_tolerance": np.timedelta64(1, "D")},
            },
        )

        coords_dst = Coordinates([[1, 1.2, 1.5, 5, 9], clinspace("2018-01-01", "2018-01-09", 3)], dims=["lat", "time"])
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert (
            output.values[0, 0] == source[0, 0]
            and output.values[0, 1] == source[0, 2]
            and np.isnan(output.values[1, 0])
            and np.isnan(output.values[1, 1])
            and output.values[2, 0] == source[1, 0]
            and output.values[2, 1] == source[1, 2]
        )


class TestInterpolateRasterio(object):
    """test interpolation functions"""

    def test_interpolate_rasterio(self):
        """ regular interpolation using rasterio"""

        assert rasterio is not None

        source = np.arange(0, 15)
        source.resize((3, 5))

        coords_src = Coordinates([clinspace(0, 10, 3), clinspace(0, 10, 5)], dims=["lat", "lon"])
        coords_dst = Coordinates([clinspace(1, 11, 3), clinspace(1, 11, 5)], dims=["lat", "lon"])

        # try one specific rasterio case to measure output
        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "min", "interpolators": [Rasterio]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert output.data[0, 3] == 3.0
        assert output.data[0, 4] == 4.0

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "max", "interpolators": [Rasterio]}
        )
        output = node.eval(coords_dst)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert output.data[0, 3] == 9.0
        assert output.data[0, 4] == 9.0

        # TODO boundary should be able to use a default
        node = MockArrayDataSource(
            data=source,
            coordinates=coords_src,
            interpolation={"method": "bilinear", "interpolators": [Rasterio]},
            boundary={"lat": 2.5, "lon": 1.25},
        )
        output = node.eval(coords_dst)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        np.testing.assert_allclose(
            output, [[1.4, 2.4, 3.4, 4.4, 5.0], [6.4, 7.4, 8.4, 9.4, 10.0], [10.4, 11.4, 12.4, 13.4, 14.0]]
        )

    def test_interpolate_rasterio_descending(self):
        """should handle descending"""

        source = np.random.rand(5, 5)
        coords_src = Coordinates([clinspace(10, 0, 5), clinspace(0, 10, 5)], dims=["lat", "lon"])
        coords_dst = Coordinates([clinspace(2, 12, 5), clinspace(2, 12, 5)], dims=["lat", "lon"])

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [Rasterio]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert np.all(output.lon.values == coords_dst.coords["lon"])


class TestInterpolateScipyGrid(object):
    """test interpolation functions"""

    def test_interpolate_scipy_grid(self):

        source = np.arange(0, 25)
        source.resize((5, 5))

        coords_src = Coordinates([clinspace(0, 10, 5), clinspace(0, 10, 5)], dims=["lat", "lon"])
        coords_dst = Coordinates([clinspace(1, 11, 5), clinspace(1, 11, 5)], dims=["lat", "lon"])

        # try one specific rasterio case to measure output
        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        print(output)
        assert output.data[0, 0] == 0.0
        assert output.data[0, 3] == 3.0
        assert output.data[1, 3] == 8.0
        assert np.isnan(output.data[0, 4])  # TODO: how to handle outside bounds

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "cubic_spline", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert int(output.data[0, 0]) == 2
        assert int(output.data[2, 4]) == 16

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "bilinear", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert int(output.data[0, 0]) == 2
        assert int(output.data[3, 3]) == 20
        assert np.isnan(output.data[4, 4])  # TODO: how to handle outside bounds

    def test_interpolate_irregular_arbitrary_2dims(self):
        """ irregular interpolation """

        # try >2 dims
        source = np.random.rand(5, 5, 3)
        coords_src = Coordinates([clinspace(0, 10, 5), clinspace(0, 10, 5), [2, 3, 5]], dims=["lat", "lon", "time"])
        coords_dst = Coordinates([clinspace(1, 11, 5), clinspace(1, 11, 5), [2, 3, 5]], dims=["lat", "lon", "time"])

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert np.all(output.lon.values == coords_dst.coords["lon"])
        assert np.all(output.time.values == coords_dst.coords["time"])

        # assert output.data[0, 0] == source[]

    def test_interpolate_irregular_arbitrary_descending(self):
        """should handle descending"""

        source = np.random.rand(5, 5)
        coords_src = Coordinates([clinspace(0, 10, 5), clinspace(0, 10, 5)], dims=["lat", "lon"])
        coords_dst = Coordinates([clinspace(2, 12, 5), clinspace(2, 12, 5)], dims=["lat", "lon"])

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert np.all(output.lon.values == coords_dst.coords["lon"])

    def test_interpolate_irregular_arbitrary_swap(self):
        """should handle descending"""

        source = np.random.rand(5, 5)
        coords_src = Coordinates([clinspace(0, 10, 5), clinspace(0, 10, 5)], dims=["lat", "lon"])
        coords_dst = Coordinates([clinspace(2, 12, 5), clinspace(2, 12, 5)], dims=["lat", "lon"])

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert np.all(output.lon.values == coords_dst.coords["lon"])

    def test_interpolate_irregular_lat_lon(self):
        """ irregular interpolation """

        source = np.random.rand(5, 5)
        coords_src = Coordinates([clinspace(0, 10, 5), clinspace(0, 10, 5)], dims=["lat", "lon"])
        coords_dst = Coordinates([[[0, 2, 4, 6, 8, 10], [0, 2, 4, 5, 6, 10]]], dims=["lat_lon"])

        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [ScipyGrid]}
        )
        output = node.eval(coords_dst)

        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat_lon.values == coords_dst.coords["lat_lon"])
        assert output.values[0] == source[0, 0]
        assert output.values[1] == source[1, 1]
        assert output.values[-1] == source[-1, -1]


class TestInterpolateScipyPoint(object):
    def test_interpolate_scipy_point(self):
        """ interpolate point data to nearest neighbor with various coords_dst"""

        source = np.random.rand(6)
        coords_src = Coordinates([[[0, 2, 4, 6, 8, 10], [0, 2, 4, 5, 6, 10]]], dims=["lat_lon"])
        coords_dst = Coordinates([[[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]]], dims=["lat_lon"])
        node = MockArrayDataSource(
            data=source, coordinates=coords_src, interpolation={"method": "nearest", "interpolators": [ScipyPoint]}
        )

        output = node.eval(coords_dst)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat_lon.values == coords_dst.coords["lat_lon"])
        assert output.values[0] == source[0]
        assert output.values[-1] == source[3]

        coords_dst = Coordinates([[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]], dims=["lat", "lon"])
        output = node.eval(coords_dst)
        assert isinstance(output, UnitsDataArray)
        assert np.all(output.lat.values == coords_dst.coords["lat"])
        assert output.values[0, 0] == source[0]
        assert output.values[-1, -1] == source[3]
