"""
Type Summary

Attributes
----------
WCS_DEFAULT_CRS : str
    Description
WCS_DEFAULT_VERSION : str
    Description
"""

from __future__ import division, unicode_literals, print_function, absolute_import

import os
import re
from io import BytesIO
from collections import OrderedDict, defaultdict

import bs4
import numpy as np
import xarray as xp
import traitlets as tl
from podpac.core.units import ureg

# Optional dependencies
try:
    import pydap.client
except:
    pydap = None

try:
    import rasterio
except:
    rasterio = None
    try:
        from arcpy import RasterToNumPyArray
    except:
        RasterToNumPyArray = None
    
try:
    import boto3
except:
    boto3 = None
    
try:
    import requests
except:
    requests = None
    try:
        import urllib3
    except:
        urllib3 = None
        
    try:
        import certifi
    except:
        certifi = None

# Not used directly, but used indirectly by bs4 so want to check if it's available
try:
    import lxml
except:
    lxml = None

# Internal dependencies
import podpac
from podpac.core import authentication
from podpac.core.utils import cached_property, clear_cache, common_doc
from podpac.core.data.data import COMMON_DATA_DOC
from podpac.core.node import COMMON_NODE_DOC 

COMMON_DOC = COMMON_NODE_DOC.copy()
COMMON_DOC.update(COMMON_DATA_DOC)      # inherit and overwrite with COMMON_DATA_DOC

class NumpyArray(podpac.DataSource):
    """Create a DataSource from a numpy array
    
    Attributes
    ----------
    source : np.ndarray
        Numpy array containing the source data
        
    Notes
    ------
    `native_coordinates` need to supplied by the user when instantiating this node. 
    """
    
    source = tl.Instance(np.ndarray)
    
    @common_doc(COMMON_DOC)
    def get_data(self, coordinates, coordinates_index):
        """{get_data}
        """
        s = coordinates_index
        d = self.initialize_coord_array(coordinates, 'data',
                                        fillval=self.source[s])
        return d

@common_doc(COMMON_DATA_DOC)
class PyDAP(podpac.DataSource):
    """Create a DataSource from an OpenDAP server feed.
    
    Attributes
    ----------
    auth_class : podpac.core.authentication.SessionWithHeaderRedirection
        A request.Session-derived class that has header redirection. This is used to authenticate using an EarthData 
        login. When username and password are provided, an auth_session is created using this class. 
    auth_session : podpac.core.authentication.SessionWithHeaderRedirection
        Instance of the auth_class. This is created if username and password is supplied, but this object can also be 
        supplied directly
    datakey : str
        Pydap 'key' for the data to be retrieved from the server. Datasource may have multiple keys, so this key
        determines which variable is returned from the source. 
    dataset : pydap.model.DatasetType
        The open pydap dataset. This is provided for troubleshooting. 
    native_coordinates : podpac.Coordinate
        {ds_native_coordinates}
    password : str, optional 
        Password used for authenticating against OpenDAP server. WARNING: this is stored as plain-text, provide
        auth_session instead if you have security concerns. 
    source : str
        URL of the OpenDAP server. 
    username : str, optional
        Username used for authenticating against OpenDAP server. WARNING: this is stored as plain-text, provide
        auth_session instead if you have security concerns. 
    """
    
    auth_session = tl.Instance(authentication.SessionWithHeaderRedirection,
                               allow_none=True)
    auth_class = tl.Type(authentication.SessionWithHeaderRedirection)
    username = tl.Unicode(None, allow_none=True)
    password = tl.Unicode(None, allow_none=True)

    @tl.default('auth_session')
    def _auth_session_default(self):
        if not self.username or not self.password:
            return None
        session = self.auth_class(username=self.username, password=self.password)

        # check url
        try:
            session.get(self.source + '.dds')
        except:
            return None
        return session
   
    dataset = tl.Instance('pydap.model.DatasetType', allow_none=True)

    @tl.default('dataset')
    def _open_dataset(self, source=None):
        """Summary
        
        Parameters
        ----------
        source : None, optional
            Description
        
        Returns
        -------
        TYPE
            Description
        """
        if source is None:
            source = self.source
        else:
            self.source = source
        
        try:
            dataset = pydap.client.open_url(source, session=self.auth_session)
        except:
            #Check Url (probably inefficient...)
            self.auth_session.get(self.source + '.dds')
            dataset = pydap.client.open_url(source, session=self.auth_session)
        
        return dataset
        

    @tl.observe('source')
    def _update_dataset(self, change):
        if change['old'] == None:
            return
        if self.dataset is not None:
            self.dataset = self._open_dataset(change['new'])
        if self.native_coordinates is not None:
            self.native_coordinates = self.get_native_coordinates()

    datakey = tl.Unicode(allow_none=False)
  
    @common_doc(COMMON_DOC)
    def get_native_coordinates(self):
        """{get_native_coordinates}
        
        Raises
        ------
        NotImplementedError
            DAP has no mechanism for creating coordinates automatically, so this is left up to child classes.
        """
        raise NotImplementedError("DAP has no mechanism for creating coordinates"
                                  ", so this is left up to child class "
                                  "implementations.")

    @common_doc(COMMON_DOC)
    def get_data(self, coordinates, coordinates_slice):
        """{get_data}
        """
        data = self.dataset[self.datakey][tuple(coordinates_slice)]
        d = self.initialize_coord_array(coordinates, 'data',
                                        fillval=data.reshape(coordinates.shape))
        return d
    
    @property
    def keys(self):
        """The list of available keys from the OpenDAP dataset.
        
        Returns
        -------
        List
            The list of available keys from the OpenDAP dataset. Any of these keys can be set as self.datakey
        """
        return self.dataset.keys()

@common_doc(COMMON_DOC)
class RasterioSource(podpac.DataSource):
    """Create a DataSource using Rasterio.
    
    Attributes
    ----------
    band : int
        The 'band' or index for the variable being accessed in files such as GeoTIFFs
    dataset : Any
        A reference to the datasource opened by rasterio
    native_coordinates : podpac.Coordinates
        {ds_native_coordinates}
    source : str
        Path to the data source
    """
    
    source = tl.Unicode(allow_none=False)
    dataset = tl.Any(allow_none=True)
    band = tl.CInt(1).tag(attr=True)
    
    @tl.default('dataset')
    def open_dataset(self, source=None):
        """Opens the data source
        
        Parameters
        ----------
        source : str, optional
            Uses self.source by default. Path to the data source.
        
        Returns
        -------
        Any
            raster.open(source)
        """
        if source is None:
            source = self.source
        else:
            self.source = source
        return rasterio.open(source)
    
    def close_dataset(self):
        """Closes the file for the datasource
        """
        self.dataset.close()

    @tl.observe('source')
    def _update_dataset(self, change):
        if self.dataset is not None:
            self.dataset = self.open_dataset(change['new'])
        self.native_coordinates = self.get_native_coordinates()
        
    @common_doc(COMMON_DOC)
    def get_native_coordinates(self):
        """{get_native_coordinates}
        
        The default implementation tries to find the lat/lon coordinates based on dataset.affine or dataset.transform
        (depending on the version of rasterio). It cannot determine the alt or time dimensions, so child classes may 
        have to overload this method. 
        """
        dlon = self.dataset.width
        dlat = self.dataset.height
        if hasattr(self.dataset, 'affine'):
            affine = self.dataset.affine
        else:
            affine = self.dataset.transform
        left, bottom, right, top = self.dataset.bounds
        if affine[1] != 0.0 or\
           affine[3] != 0.0:
            raise NotImplementedError("Have not implemented rotated coords")

        return podpac.Coordinate(lat=(top, bottom, dlat),
                                 lon=(left, right, dlon),
                                 order=['lat', 'lon'])

    @common_doc(COMMON_DOC)
    def get_data(self, coordinates, coordinates_index):
        """{get_data}
        """
        data = self.initialize_coord_array(coordinates)
        slc = coordinates_index
        data.data.ravel()[:] = self.dataset.read(
            self.band, window=((slc[0].start, slc[0].stop),
                               (slc[1].start, slc[1].stop)),
            out_shape=tuple(coordinates.shape)
            ).ravel()
            
        return data
    
    @cached_property
    def band_count(self):
        """The number of bands
        
        Returns
        -------
        int
            The number of bands in the dataset
        """
        return self.dataset.count
    
    @cached_property
    def band_descriptions(self):
        """A description of each band contained in dataset.tags
        
        Returns
        -------
        OrderedDict
            Dictionary of band_number: band_description pairs. The band_description values are a dictionary, each 
            containing a number of keys -- depending on the metadata
        """
        bands = OrderedDict()
        for i in range(self.dataset.count):
            bands[i] = self.dataset.tags(i + 1)
        return bands

    @cached_property
    def band_keys(self):
        """An alternative view of band_descriptions based on the keys present in the metadata
        
        Returns
        -------
        dict
            Dictionary of metadata keys, where the values are the value of the key for each band. 
            For example, band_keys['TIME'] = ['2015', '2016', '2017'] for a dataset with three bands.
        """
        keys = {}
        for i in range(self.band_count):
            for k in self.band_descriptions[i].keys():
                keys[k] = None
        keys = keys.keys()
        band_keys = defaultdict(lambda: [])
        for k in keys:
            for i in range(self.band_count):
                band_keys[k].append(self.band_descriptions[i].get(k, None))
        return band_keys
    
    @tl.observe('source')
    def _clear_band_description(self, change):
        clear_cache(self, change, ['band_descriptions', 'band_count',
                                   'band_keys'])

    def get_band_numbers(self, key, value):
        """Return the bands that have a key equal to a specified value.
        
        Parameters
        ----------
        key : str
            Key present in the metadata of the band.
        value : str
            Value of the key that should be returned
        
        Returns
        -------
        np.ndarray
            An array of band numbers that match the criteria
        """
        if not hasattr(key, '__iter__') and not hasattr(value, '__iter__'):
            key = [key]
            value = [value]

        match = np.ones(self.band_count, bool)
        for k, v in zip(key, value):
            match = match & (np.array(self.band_keys[k]) == v)
        matches = np.where(match)[0] + 1

        return matches


WCS_DEFAULT_VERSION = u'1.0.0'
WCS_DEFAULT_CRS = 'EPSG:4326'

class WCS(podpac.DataSource):
    """Create a DataSource from an OGC-complient WCS service
    
    Attributes
    ----------
    crs : 'str'
        Default is EPSG:4326 (WGS84 Geodic) EPSG number for the coordinate reference system that the data should
        be returned in.
    layer_name : str
        Name of the WCS layer that should be fetched from the server
    source : str
        URL of the WCS server endpoint
    version : str
        Default is 1.0.0. WCS version string.
    wcs_coordinates : podpac.Coordinates
        The coordinates of the WCS source
    """
    
    source = tl.Unicode()
    layer_name = tl.Unicode().tag(attr=True)
    version = tl.Unicode(WCS_DEFAULT_VERSION).tag(attr=True)
    crs = tl.Unicode(WCS_DEFAULT_CRS).tag(attr=True)
    _get_capabilities_qs = tl.Unicode('SERVICE=WCS&REQUEST=DescribeCoverage&'
                                     'VERSION={version}&COVERAGE={layer}')
    _get_data_qs = tl.Unicode('SERVICE=WCS&VERSION={version}&REQUEST=GetCoverage&'
                             'FORMAT=GeoTIFF&COVERAGE={layer}&'
                             'BBOX={w},{s},{e},{n}&CRS={crs}&RESPONSE_CRS={crs}&'
                             'WIDTH={width}&HEIGHT={height}&TIME={time}')

    @property
    def get_capabilities_url(self):
        """Constructs the url that requests the WCS capabilities
        
        Returns
        -------
        str
            The url that requests the WCS capabilities
        """
        return self.source + '?' + self._get_capabilities_qs.format(
            version=self.version, layer=self.layer_name)

    wcs_coordinates = tl.Instance(podpac.Coordinate)
    @tl.default('wcs_coordinates')
    def get_wcs_coordinates(self):
        """Retrieves the native coordinates reported by the WCS service.
        
        Returns
        -------
        podpac.Coordinates
            The native coordinates reported by the WCS service.
        
        Notes
        -------
        This assumes a `time`, `lat`, `lon` order for the coordinates, and currently doesn't handle `alt` coordinates
        
        Raises
        ------
        Exception
            Raises this if the required dependencies are not installed.
        """
        if requests is not None:
            capabilities = requests.get(self.get_capabilities_url)
            if capabilities.status_code != 200:
                raise Exception("Could not get capabilities from WCS server")
            capabilities = capabilities.text
        elif urllib3 is not None:
            if certifi is not None:
                http = urllib3.PoolManager(ca_certs=certifi.where())
            else:
                http = urllib3.PoolManager()

            r = http.request('GET', self.get_capabilities_url)
            capabilities = r.data
            if r.status != 200:
                raise Exception("Could not get capabilities from WCS server")
        else:
            raise Exception("Do not have a URL request library to get WCS data.")

        if lxml is not None: # could skip using lxml and always use html.parser instead, which seems to work but lxml might be faster
            capabilities = bs4.BeautifulSoup(capabilities, 'lxml')
        else:
            capabilities = bs4.BeautifulSoup(capabilities, 'html.parser')

        domain = capabilities.find('wcs:spatialdomain')
        pos = domain.find('gml:envelope').get_text().split()
        lonlat = np.array(pos, float).reshape(2, 2)
        grid_env = domain.find('gml:gridenvelope')
        low = np.array(grid_env.find('gml:low').text.split(), int)
        high = np.array(grid_env.find('gml:high').text.split(), int)
        size = high - low
        dlondlat = (lonlat[1, :] - lonlat[0, :]) / size
        bottom = lonlat[:, 1].min() + dlondlat[1] / 2
        top = lonlat[:, 1].max() - dlondlat[1] / 2
        left = lonlat[:, 1].min() + dlondlat[0] / 2
        right = lonlat[:, 1].max() - dlondlat[0] / 2

        timedomain = capabilities.find("wcs:temporaldomain")
        if timedomain is None:
            return podpac.Coordinate(lat=(top, bottom, size[1]),
                                         lon=(left, right, size[0]), order=['lat', 'lon'])
        
        date_re = re.compile('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}')
        times = str(timedomain).replace('<gml:timeposition>', '').replace('</gml:timeposition>', '').split('\n')
        times = np.array([t for t in times if date_re.match(t)], np.datetime64)
        
        return podpac.Coordinate(time=times,
                                 lat=(top, bottom, size[1]),
                                 lon=(left, right, size[0]),                        
                                 order=['time', 'lat', 'lon'])
        

    @property
    @common_doc(COMMON_DOC)
    def native_coordinates(self):
        """{native_coordinates}
        
        Returns
        -------
        podpac.Coordinates
            {native_coordinates}
            
        Notes
        ------
        This is a little tricky and doesn't fit into the usual PODPAC method, as the service is actually doing the 
        data wrangling for us...
        """
        if self.evaluated_coordinates:
            ev = self.evaluated_coordinates
            wcs_c = self.wcs_coordinates
            cs = OrderedDict()
            for c in wcs_c.dims:
                if c in ev.dims and ev[c].size == 1:
                    cs[c] = ev[c].coords
                elif c in ev.dims and not isinstance(ev[c], podpac.UniformCoord):
                    # This is rough, we have to use a regular grid for WCS calls,
                    # Otherwise we have to do multiple WCS calls...
                    # TODO: generalize/fix this
                    cs[c] = (min(ev[c].coords),
                             max(ev[c].coords), abs(ev[c].delta))
                elif c in ev.dims and isinstance(ev[c], podpac.UniformCoord):
                    cs[c] = (min(ev[c].coords[:2]),
                             max(ev[c].coords[:2]), abs(ev[c].delta))
                else:
                    cs.append(wcs_c[c])
            c = podpac.Coordinate(cs)
            return c
        else:
            return self.wcs_coordinates

    def get_data(self, coordinates, coordinates_index):
        """{get_data}
        
        Raises
        ------
        Exception
            Raises this if there is a network error or required dependencies are not installed.
        """
        output = self.initialize_coord_array(coordinates)
        dotime = 'time' in self.wcs_coordinates.dims

        if 'time' in coordinates.dims and dotime:
            sd = np.timedelta64(0, 's')
            times = [str(t+sd) for t in coordinates['time'].coordinates]
        else:
            times = ['']
            
        if len(times) > 1:
            for i, time in enumerate(times):
                url = self.source + '?' + self._get_data_qs.format(
                    version=self.version, layer=self.layer_name,
                    w=min(coordinates['lon'].area_bounds),
                    e=max(coordinates['lon'].area_bounds),
                    s=min(coordinates['lat'].area_bounds),
                    n=max(coordinates['lat'].area_bounds),
                    width=coordinates['lon'].size,
                    height=coordinates['lat'].size,
                    time=time,
                    crs=self.crs
                )

                if not dotime:
                    url = url.replace('&TIME=', '')

                if requests is not None:
                    data = requests.get(url)
                    if data.status_code != 200:
                        raise Exception("Could not get data from WCS server")
                    io = BytesIO(bytearray(data.content))
                    content = data.content
                elif urllib3 is not None:
                    if certifi is not None:
                        http = urllib3.PoolManager(ca_certs=certifi.where())
                    else:
                        http = urllib3.PoolManager()
                    r = http.request('GET', url)
                    if r.status != 200:
                        raise Exception("Could not get capabilities from WCS server")
                    content = r.data
                    io = BytesIO(bytearray(r.data))
                else:
                    raise Exception("Do not have a URL request library to get WCS data.")
                
                if rasterio is not None:
                    try: # This works with rasterio v1.0a8 or greater, but not on python 2
                        with rasterio.open(io) as dataset:
                            output.data[i, ...] = dataset.read()
                    except Exception as e: # Probably python 2
                        print(e)
                        tmppath = os.path.join(self.cache_dir, 'wcs_temp.tiff')
                        
                        if not os.path.exists(os.path.split(tmppath)[0]):
                            os.makedirs(os.path.split(tmppath)[0])
                        
                        # TODO: close tmppath? os does this on remove?
                        open(tmppath, 'wb').write(content)
                        
                        with rasterio.open(tmppath) as dataset:
                            output.data[i, ...] = dataset.read()

                        os.remove(tmppath) # Clean up

                elif RasterToNumPyArray is not None:
                    # Writing the data to a temporary tiff and reading it from there is hacky
                    # However reading directly from r.data or io doesn't work
                    # Should improve in the future
                    open('temp.tiff', 'wb').write(r.data)
                    output.data[i, ...] = RasterToNumPyArray('temp.tiff')
        else:
            time = times[0]
            
            url = self.source + '?' + self._get_data_qs.format(
                version=self.version, layer=self.layer_name,
                w=min(coordinates['lon'].area_bounds),
                e=max(coordinates['lon'].area_bounds),
                s=min(coordinates['lat'].area_bounds),
                n=max(coordinates['lat'].area_bounds),
                width=coordinates['lon'].size,
                height=coordinates['lat'].size,
                time=time,
                crs=self.crs
            )
            if not dotime:
                url = url.replace('&TIME=', '')
            if requests is not None:
                data = requests.get(url)
                if data.status_code != 200:
                    raise Exception("Could not get data from WCS server")
                io = BytesIO(bytearray(data.content))
                content = data.content
            elif urllib3 is not None:
                if certifi is not None:
                    http = urllib3.PoolManager(ca_certs=certifi.where())
                else:
                    http = urllib3.PoolManager()
                r = http.request('GET', url)
                if r.status != 200:
                    raise Exception("Could not get capabilities from WCS server")
                content = r.data
                io = BytesIO(bytearray(r.data))
            else:
                raise Exception("Do not have a URL request library to get WCS data.")
            
            if rasterio is not None:
                try: # This works with rasterio v1.0a8 or greater, but not on python 2
                    with rasterio.open(io) as dataset:
                        if dotime:
                            output.data[0, ...] = dataset.read()
                        else:
                            output.data[:] = dataset.read()
                except Exception as e: # Probably python 2
                    print(e)
                    tmppath = os.path.join(
                        self.cache_dir, 'wcs_temp.tiff')
                    if not os.path.exists(os.path.split(tmppath)[0]):
                        os.makedirs(os.path.split(tmppath)[0])
                    open(tmppath, 'wb').write(content)
                    with rasterio.open(tmppath) as dataset:
                        output.data[:] = dataset.read()
                    os.remove(tmppath) # Clean up
            elif RasterToNumPyArray is not None:
                # Writing the data to a temporary tiff and reading it from there is hacky
                # However reading directly from r.data or io doesn't work
                # Should improve in the future
                open('temp.tiff', 'wb').write(r.data)
                output.data[:] = RasterToNumPyArray('temp.tiff')
            else:
                raise Exception('Rasterio or Arcpy not available to read WCS feed.')
        if not coordinates['lat'].is_descending:
            if dotime:
                output.data[:] = output.data[:, ::-1, :]
            else:
                output.data[:] = output.data[::-1, :]

        return output

    @property
    def base_ref(self):
        """Summary
        
        Returns
        -------
        TYPE
            Description
        """
        return self.layer_name.rsplit('.', 1)[1]


# We mark this as an algorithm node for the sake of the pipeline, although
# the "algorithm" portion is not being used / is overwritten by the DataSource
# In particular, this is required for providing coordinates_source
# We should be able to to remove this requirement of attributes in the pipeline 
# can have nodes specified... 
class ReprojectedSource(podpac.DataSource, podpac.Algorithm):
    """Create a DataSource with a different resolution from another Node. This can be used to bilinearly interpolated a
    dataset after averaging over a larger area.
    
    Attributes
    ----------
    coordinates_source : podpac.Node
        Node which is used as the source
    reprojected_coordinates : podpac.Coordinate
        Coordinates where the source node should be evaluated. 
    source : podpac.Node
        The source node
    source_interpolation : str
        Type of interpolation method to use for the source node
    """
    
    source_interpolation = tl.Unicode('nearest_preview').tag(param=True)
    source = tl.Instance(podpac.Node)
    # Specify either one of the next two
    coordinates_source = tl.Instance(podpac.Node, allow_none=True).tag(attr=True)
    reprojected_coordinates = tl.Instance(podpac.Coordinate).tag(attr=True)

    @tl.default('reprojected_coordinates')
    def get_reprojected_coordinates(self):
        """Retrieves the reprojected coordinates in case coordinates_source is specified
        
        Returns
        -------
        podpac.Coordinate
            Coordinates where the source node should be evaluated. 
        
        Raises
        ------
        Exception
            If neither coordinates_source or reproject_coordinates are specified
        """
        try:
            return self.coordinates_source.native_coordinates
        except AttributeError:
            raise Exception("Either reprojected_coordinates or coordinates"
                            "_source must be specified")

    @common_doc(COMMON_DOC)
    def get_native_coordinates(self):
        """{get_native_coordinates}
        """
        coords = OrderedDict()
        if isinstance(self.source, podpac.DataSource):
            sc = self.source.native_coordinates
        else: # Otherwise we cannot guarantee that native_coordinates exist
            sc = self.reprojected_coordinates
        rc = self.reprojected_coordinates
        for d in sc.dims:
            if d in rc.dims:
                coords[d] = rc.stack_dict()[d]
            else:
                coords[d] = sc.stack_dict()[d]
        return podpac.Coordinate(coords)

    @common_doc(COMMON_DOC)
    def get_data(self, coordinates, coordinates_slice):
        """{get_data}
        """
        self.source.interpolation = self.source_interpolation
        data = self.source.execute(coordinates, self._params)
        
        # The following is needed in case the source is an algorithm
        # or compositor node that doesn't have all the dimensions of
        # the reprojected coordinates
        # TODO: What if data has coordinates that reprojected_coordinates
        #       doesn't have
        keep_dims = list(data.coords.keys())
        drop_dims = [d for d in coordinates.dims if d not in keep_dims]
        coordinates.drop_dims(*drop_dims)
        return data

    @property
    def base_ref(self):
        """Summary
        
        Returns
        -------
        TYPE
            Description
        """
        return '{}_reprojected'.format(self.source.base_ref)

    @property
    def definition(self):
        """ Pipeline node definition. 
        
        Returns
        -------
        OrderedDict
            Pipeline node definition. 
        
        Raises
        ------
        NotImplementedError
            If coordinates_source is None, this raises an error because serialization of reprojected_coordinates 
            is not implemented
        """
        
        d = podpac.Algorithm.definition.fget(self)
        d['attrs'] = OrderedDict()
        if self.interpolation:
            d['attrs']['interpolation'] = self.interpolation
        if self.coordinates_source is None:
            # TODO serialize reprojected_coordinates
            raise NotImplementedError
        return d

class S3Source(podpac.DataSource):
    """Create a DataSource from a file on an S3 Bucket. 
    
    Attributes
    ----------
    node : podpac.Node, optional
        The DataSource node used to interpret the S3 file
    node_class : podpac.DataSource, optional
        The class type of self.node. This is used to create self.node if self.node is not specified
    node_kwargs : dict, optional
        Keyword arguments passed to `node_class` when automatically creating `node`
    return_type : str, optional
        Either: 'file_handle' (for files downloaded to RAM); or 
        the default option 'path' (for files downloaded to disk)
    s3_bucket : str, optional
        Name of the S3 bucket. Uses settings.S3_BUCKET_NAME by default. 
    s3_data : file/str
        If return_type == 'file_handle' returns a file pointer object
        If return_type == 'path' returns a string to the data
    source : str
        Path to the file residing in the S3 bucket that will be loaded
    """
    
    source = tl.Unicode()
    node = tl.Instance(podpac.Node)
    node_class = tl.Type(podpac.DataSource)  # A class
    node_kwargs = tl.Dict(default_value={})
    s3_bucket = tl.Unicode()
    s3_data = tl.Any()
    _temp_file_cleanup = tl.List()
    return_type = tl.Enum(['file_handle', 'path'], default_value='path')
    
    @tl.default('node')
    def node_default(self):
        """Creates the default node using the node_class and node_kwargs
        
        Returns
        -------
        self.node_class
            Instance of self.node_class
        
        Raises
        ------
        Exception
            This function sets the source in the node, so 'source' cannot be present in node_kwargs
        """
        if 'source' in self.node_kwargs:
            raise Exception("'source' present in node_kwargs for S3Source")
        return self.node_class(source=self.s3_data, **self.node_kwargs)

    @tl.default('s3_bucket')
    def s3_bucket_default(self):
        """Retrieves defaul S3 Bucket from settings
        
        Returns
        -------
        Str
            Name of the S3 bucket
        """
        return podpac.settings.S3_BUCKET_NAME

    @tl.default('s3_data')
    def s3_data_default(self):
        """Returns the file handle or path to the S3 bucket
        
        Returns
        -------
        str/file
            Either a string to the downloaded file path, or a file handle
        """
        s3 = boto3.resource('s3').Bucket(self.s3_bucket)
        if self.return_type == 'file_handle':
            # download into memory
            io = BytesIO()
            s3.download_fileobj(self.source, io)
            io.seek(0)
            return io
        elif self.return_type == 'path':
            # Download the file to cache directory
            #tmppath = os.path.join(tempfile.gettempdir(),
                                   #self.source.replace('\\', '').replace(':','')\
                                   #.replace('/', ''))
            tmppath = os.path.join(
                self.cache_dir,
                self.source.replace('\\', '').replace(':', '').replace('/', ''))
            
            rootpath = os.path.split(tmppath)[0]
            if not os.path.exists(rootpath):
                os.makedirs(rootpath)
            #i = 0
            #while os.path.exists(tmppath):
                #tmppath = os.path.join(tempfile.gettempdir(),
                                       #self.source + '.%d' % i)
            if not os.path.exists(tmppath):
                s3.download_file(self.source, tmppath)
            #self._temp_file_cleanup.append(tmppath)
            return tmppath

    @common_doc(COMMON_DOC)
    def get_data(self, coordinates, coordinates_slice):
        """{get_data}
        """
        self.no_data_vals = getattr(self.node, 'no_data_vals', [])
        return self.node.get_data(coordinates, coordinates_slice)

    @property
    @common_doc(COMMON_DOC)
    def native_coordinates(self):
        """{native_coordinates}
        """
        return self.node.native_coordinates

    def __del__(self):
        if hasattr(super(S3Source), '__del__'):
            super(S3Source).__del__(self)
        for f in self._temp_file_cleanup:
            os.remove(f)

if __name__ == '__main__':
    #from podpac.core.data.type import S3Source
    #import podpac

    source = r'SMAPSentinel/SMAP_L2_SM_SP_1AIWDV_20170801T000000_20170731T114719_094E21N_T15110_002.h5'
    s3 = S3Source(source=source)
    
    s3.s3_data
    
    #coord_src = podpac.Coordinate(lat=(45, 0, 16), lon=(-70., -65., 16), time=(0, 1, 2),
                                    #order=['lat', 'lon', 'time'])
    #coord_dst = podpac.Coordinate(lat=(50., 0., 50), lon=(-71., -66., 100),
                                    #order=['lat', 'lon'])
    #LON, LAT, TIME = np.meshgrid(coord_src['lon'].coordinates,
                                    #coord_src['lat'].coordinates,
                                    #coord_src['time'].coordinates)
    ##LAT, LON = np.mgrid[0:45+coord_src['lat'].delta/2:coord_src['lat'].delta,
                                ##-70:-65+coord_src['lon'].delta/2:coord_src['lon'].delta]    
    #source = LAT + 0*LON + 0*TIME
    #nas = NumpyArray(source=source.astype(float), 
                        #native_coordinates=coord_src, interpolation='bilinear')
    ##coord_pts = podpac.Coordinate(lat_lon=(coord_src.coords['lat'], coord_src.coords['lon']))
    ##o3 = nas.execute(coord_pts)
    #o = nas.execute(coord_dst)
    ##coord_pt = podpac.Coordinate(lat=10., lon=-67.)
    ##o2 = nas.execute(coord_pt)
    from podpac.datalib.smap import SMAPSentinelSource
    s3.node_class = SMAPSentinelSource

    #coordinates = podpac.Coordinate(lat=(45, 0, 16), lon=(-70., -65., 16),
                                    #order=['lat', 'lon'])
    coordinates = podpac.Coordinate(lat=(39.3, 39., 64), lon=(-77.0, -76.7, 64), time='2017-09-03T12:00:00', 
                                    order=['lat', 'lon', 'time'])    
    reprojected_coordinates = podpac.Coordinate(lat=(45, 0, 3), lon=(-70., -65., 3),
                                                order=['lat', 'lon']),
    #                                           'TopographicWetnessIndexComposited3090m'),
    #          )

    o = wcs.execute(coordinates)
    reprojected = ReprojectedSource(source=wcs,
                                    reprojected_coordinates=reprojected_coordinates,
                                    interpolation='bilinear')

    from podpac.datalib.smap import SMAP
    smap = SMAP(product='SPL4SMAU.003')
    reprojected = ReprojectedSource(source=wcs,
                                    coordinates_source=smap,
                                    interpolation='nearest')    
    o2 = reprojected.execute(coordinates)

    coordinates_zoom = podpac.Coordinate(lat=(24.8, 30.6, 64), lon=(-85.0, -77.5, 64), time='2017-08-08T12:00:00', 
                                         order=['lat', 'lon', 'time'])
    o3 = wcs.execute(coordinates_zoom)


    print ("Done")
    
    # Rename files in s3 bucket
    s3 = boto3.resource('s3').Bucket(self.s3_bucket)
    s3.Bucket(name='podpac-s3')
    obs = list(s3.objects.all())
    obs2 = [o for o in obs if 'SMAP_L2_SM_SP' in o.key]
    
    rootpath = obs2[0].key.split('/')[0] + '/'
    for o in obs2:
        newkey = rootpath + os.path.split(o.key)[1]
        s3.Object(newkey).copy_from(CopySource=self.s3_bucket + '/' + o.key)
        
    obs3 = list(s3.objects.all())
    obsD = [o for o in obs3 if 'ASOwusu' in o.key]
    for o in obsD:
        o.delete()    
