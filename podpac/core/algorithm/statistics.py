from __future__ import division, unicode_literals, print_function, absolute_import

import warnings
from operator import mul

import xarray as xr
import numpy as np
import traitlets as tl

from podpac.core.coordinate import Coordinate
from podpac.core.node import Node
from algorithm import Algorithm

class Reduce(Algorithm):
    input_coordinates = tl.Instance(Coordinate)
    input_node = tl.Instance(Node)

    @property
    def dims(self):
        """
        Validates and translates requested reduction dimensions.
        """

        input_dims = self.input_coordinates.dims

        if self.params is None or 'dims' not in self.params:
            return input_dims

        valid_dims = []
        if 'time' in input_dims:
            valid_dims.append('time')
        if 'lat_lon' in input_dims:
            valid_dims.append('lat_lon')
        if 'lat' in input_dims and 'lon' in input_dims:
            valid_dims.append('lat_lon')
        if 'alt' in input_dims:
            valid_dims.append('alt')

        params_dims = self.params['dims']
        if not isinstance(params_dims, (list, tuple)):
            params_dims = [params_dims]

        dims = []
        for dim in params_dims:
            if dim not in valid_dims:
                raise ValueError("Invalid Reduce dimension: %s" % dim)    
            elif dim in input_dims:
                dims.append(dim)
            elif dim == 'lat_lon':
                dims.append('lat')
                dims.append('lon')
        
        return dims

    def get_reduced_coordinates(self, coordinates):
        dims = self.dims
        kwargs = {}
        order = []
        for dim in coordinates.dims:
            if dim in self.dims:
                continue
            
            kwargs[dim] = coordinates[dim]
            order.append(dim)
        
        if order:
            kwargs['order'] = order

        return Coordinate(**kwargs)

    @property
    def chunk_size(self):
        if 'chunk_size' not in self.params:
            # return self.input_coordinates.shape
            return None

        if self.params['chunk_size'] == 'auto':
            return 1024**2 # TODO

        return self.params['chunk_size']

    @property
    def chunk_shape(self):
        if self.chunk_size is None:
            # return self.input_coordinates.shape
            return None

        chunk_size = self.chunk_size
        coords = self.input_coordinates
        
        d = {k:coords[k].size for k in coords.dims if k not in self.dims}
        s = reduce(mul, d.values(), 1)
        for dim in self.dims:
            n = chunk_size // s
            if n == 0:
                d[dim] = 1
            elif n < coords[dim].size:
                d[dim] = n
            else:
                d[dim] = coords[dim].size
            s *= d[dim]

        return [d[dim] for dim in coords.dims]

    def iteroutputs(self):
        for chunk in self.input_coordinates.iterchunks(self.chunk_shape):
            yield self.input_node.execute(chunk, self.params)

    def execute(self, coordinates, params=None, output=None):
        self.input_coordinates = coordinates
        self.params = params
        self.output = output

        self.evaluated_coordinates = self.get_reduced_coordinates(coordinates)

        if self.output is None:
            self.output = self.initialize_output_array()
            
        if self.chunk_size and self.chunk_size < reduce(mul, coordinates.shape, 1):
            result = self.reduce_chunked(self.iteroutputs())
        else:
            if self.implicit_pipeline_evaluation:
                self.input_node.execute(coordinates, params)
            result = self.reduce(self.input_node.output)

        if self.output.shape is (): # or self.evaluated_coordinates is None
            self.output.data = result
        else:
            self.output[:] = result #.transpose(*self.output.dims) # is this necessary?
        
        self.evaluated = True

        return self.output

    def reduce(self, x):
        """
        Reduce a full array, e.g. x.mean(self.dims).

        Must be defined in each child.
        """

        raise NotImplementedError

    def reduce_chunked(self, xs):
        """
        Reduce a list of xs with a memory-effecient iterative algorithm.

        Optionally defined in each child.
        """

        warnings.warn("No reduce_chunked method defined, using one-step reduce")
        x = self.input_node.execute(self.input_coordinates, self.params)
        return self.reduce(x)

    @property
    def evaluated_hash(self):
        if self.input_coordinates is None:
            raise Exception("node not evaluated")
            
        return self.get_hash(self.input_coordinates, self.params)

    @property
    def latlon_bounds_str(self):
        return self.input_coordinates.latlon_bounds_str

class Mean(Reduce):
    def reduce(self, x):
        return x.mean(dim=self.dims)

    def reduce_chunked(self, xs):
        s = xr.zeros_like(self.output) # alt: s = np.zeros(self.shape)
        n = xr.zeros_like(self.output)
        for x in xs:
            # TODO efficency
            s += x.sum(dim=self.dims)
            n += np.isfinite(x).sum(dim=self.dims)
        output = s / n
        return output

class Sum(Reduce):
    def reduce(self, x):
        return x.sum(dim=self.dims)

    def reduce_chunked(self, xs):
        s = xr.zeros_like(self.output)
        for x in xs:
            s += x.sum(dim=self.dims)
        return s

class Count(Reduce):
    def reduce(self, x):
        return np.isfinite(x).sum(dim=self.dims)

    def reduce_chunked(self, xs):
        n = xr.zeros_like(self.output)
        for x in xs:
            n += np.isfinite(x).sum(dim=self.dims)
        return n

class Median(Reduce):
    pass

class Mode(Reduce):
    pass

class Min(Reduce):
    def reduce(Reduce):
        pass

class Max(Reduce):
    pass

class Std(Reduce):
    pass

if __name__ == '__main__':
    from podpac.datalib.smap import SMAP

    smap = SMAP(product='SPL4SMAU.003')
    coords = smap.native_coordinates
    
    coords = Coordinate(
        time=coords.coords['time'][:5],
        lat=[45., 66., 50], lon=[-80., -70., 20],
        order=['time', 'lat', 'lon'])

    smap_mean = Mean(input_node=SMAP(product='SPL4SMAU.003'))
    
    print("lat_lon means")
    mll = smap_mean.execute(coords, {'dims':'lat_lon'})
    mll2 = smap_mean.execute(coords, {'dims':'lat_lon', 'chunk_size':'auto'})
    mll3 = smap_mean.execute(coords, {'dims':'lat_lon', 'chunk_size': 2000})
    mll4 = smap_mean.execute(coords, {'dims':'lat_lon', 'chunk_size': 6000})
    
    print("time means")
    mt = smap_mean.execute(coords, {'dims':'time'})
    mt2 = smap_mean.execute(coords, {'dims':'time', 'chunk_size':'auto'})
    mt3 = smap_mean.execute(coords, {'dims':'time', 'chunk_size': 2000})

    print ("full means")
    mllt = smap_mean.execute(coords, {'dims':['lat_lon', 'time']})
    mllt2 = smap_mean.execute(coords, {'dims': ['lat_lon', 'time'], 'chunk_size': 1000})
    mllt3 = smap_mean.execute(coords, {})

    print("lat_lon counts")
    smap_count = Count(input_node=SMAP(product='SPL4SMAU.003'))
    cll = smap_count.execute(coords, {'dims':'lat_lon'})
    cll2 = smap_count.execute(coords, {'dims':'lat_lon', 'chunk_size':'auto'})
    cll3 = smap_count.execute(coords, {'dims':'lat_lon', 'chunk_size': 2000})
    cll4 = smap_count.execute(coords, {'dims':'lat_lon', 'chunk_size': 6000})

    print ("Done")