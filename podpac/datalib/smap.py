"""Specialized PODPAC nodes use to access SMAP data via OpenDAP from nsidc.

Attributes
----------
SMAP_BASE_URL() : str
    Url to nsidc openDAP server
SMAP_INCOMPLETE_SOURCE_COORDINATES : list
    List of products whose source coordinates are incomplete. This means any shared coordinates cannot be extracted
SMAP_PRODUCT_DICT: dict
    Mapping of important keys into the openDAP dataset that deals with inconsistencies across SMAP products. Used to add
    new SMAP products.
SMAP_PRODUCT_MAP : xr.DataArray
    Same as SMAP_PRODUCT_DICT, but stored as a more convenient DataArray object
"""

from __future__ import division, unicode_literals, print_function, absolute_import

import os
import re
import copy
import logging

import requests
from six import string_types
import numpy as np
import xarray as xr
import traitlets as tl

# Set up logging
_logger = logging.getLogger(__name__)

# Helper utility for optional imports
from lazy_import import lazy_module, lazy_class

# Optional dependencies
bs4 = lazy_module("bs4")
BeautifulSoup = lazy_class("bs4.BeautifulSoup")
boto3 = lazy_module("boto3")

# fixing problem with older versions of numpy
if not hasattr(np, "isnat"):

    def isnat(a):
        return a.astype(str) == "None"

    np.isnat = isnat

# Internal dependencies
import podpac
from podpac import NodeException
from podpac import authentication
from podpac.coordinates import Coordinates, merge_dims
from podpac.data import PyDAP
from podpac.utils import cached_property, DiskCacheMixin
from podpac.compositor import OrderedCompositor
from podpac.core.data.datasource import COMMON_DATA_DOC
from podpac.core.utils import common_doc, _get_from_url

from podpac.datalib import nasaCMR

COMMON_DOC = COMMON_DATA_DOC.copy()
COMMON_DOC.update(
    {
        "smap_date": "str\n        SMAP date string",
        "np_date": "np.datetime64\n        Numpy date object",
        "base_url": "str\n        Url to nsidc openDAP server",
        "layer_key": (
            "str\n        Key used to retrieve data from OpenDAP dataset. This specifies the key used to retrieve "
            "the data"
        ),
        "product": "SMAP product name",
        "version": "Version number for the SMAP product",
        "source_coordinates": "Coordinates that uniquely describe each source",
        "keys": """Available layers that are in the OpenDAP dataset

        Returns
        -------
        List
            The list of available keys from the OpenDAP dataset. Any of these keys can be set as self.data_key.

        Notes
        -----
        This function assumes that all of the keys in the available dataset are the same for every file.
        """,
    }
)


@common_doc(COMMON_DOC)
def smap2np_date(date):
    """Convert dates using the format in SMAP to numpy datetime64

    Parameters
    ----------
    date : {smap_date}

    Returns
    -------
    {np_date}
    """
    if isinstance(date, string_types):
        ymd = "-".join([date[:4], date[4:6], date[6:8]])
        if len(date) == 15:
            HMS = " " + ":".join([date[9:11], date[11:13], date[13:15]])
        else:
            HMS = ""
        date = np.array([ymd + HMS], dtype="datetime64")
    return date


@common_doc(COMMON_DOC)
def np2smap_date(date):
    """Convert dates using the numpy format to SMAP strings

    Parameters
    ----------
    date : {np_date}

    Returns
    -------
    {smap_date}
    """
    if isinstance(date, np.datetime64):
        date = str(date).replace("-", ".")
    return date


def _infer_SMAP_product_version(product, base_url, session):
    """Helper function to automatically infer the version number of SMAP 
    products in case user did not specify a version, or the version changed
    
    Parameters
    ------------
    product: str
        Name of the SMAP product (e.g. one of SMAP_PRODUCT_DICT.keys())
    base_url: str
        URL to base SMAP product page
    session: :class:`requests.Session`
        Authenticated EDS session. Generally returned from :class:`SMAPSessionMixin`.
    """

    r = _get_from_url(base_url, session=session)
    if r:
        m = re.search(product, r.text)
        return int(r.text[m.end() + 1 : m.end() + 4])
    return int(SMAP_PRODUCT_MAP.sel(product=product, attr="default_version").item())


# NOTE: {rdk} will be substituted for the entry's 'root_data_key'
SMAP_PRODUCT_DICT = {
    #'<Product>.ver': ['lat_key',               'lon_key',                     'root_data_key',                       'layer_key'              'default_verison'
    "SPL4SMAU": ["cell_lat", "cell_lon", "Analysis_Data_", "{rdk}sm_surface_analysis", 4],
    "SPL4SMGP": ["cell_lat", "cell_lon", "Geophysical_Data_", "{rdk}sm_surface", 4],
    "SPL3SMA": ["{rdk}latitude", "{rdk}longitude", "Soil_Moisture_Retrieval_Data_", "{rdk}soil_moisture", 3],
    "SPL3SMAP": ["{rdk}latitude", "{rdk}longitude", "Soil_Moisture_Retrieval_Data_", "{rdk}soil_moisture", 3],
    "SPL3SMP": ["{rdk}AM_latitude", "{rdk}AM_longitude", "Soil_Moisture_Retrieval_Data_", "{rdk}_soil_moisture", 5],
    "SPL3SMP_E": ["{rdk}AM_latitude", "{rdk}AM_longitude", "Soil_Moisture_Retrieval_Data_", "{rdk}_soil_moisture", 5],
    "SPL4SMLM": ["cell_lat", "cell_lon", "Land_Model_Constants_Data_", "", 4],
    "SPL2SMAP_S": [
        "{rdk}latitude_1km",
        "{rdk}longitude_1km",
        "Soil_Moisture_Retrieval_Data_1km_",
        "{rdk}soil_moisture_1km",
        2,
    ],
}

SMAP_PRODUCT_MAP = xr.DataArray(
    list(SMAP_PRODUCT_DICT.values()),
    dims=["product", "attr"],
    coords={
        "product": list(SMAP_PRODUCT_DICT.keys()),
        "attr": ["lat_key", "lon_key", "root_data_key", "layer_key", "default_version"],
    },
)

SMAP_INCOMPLETE_SOURCE_COORDINATES = ["SPL2SMAP_S"]
SMAP_IRREGULAR_COORDINATES = ["SPL2SMAP_S"]

# Discover SMAP OpenDAP url from podpac s3 server
SMAP_BASE_URL_FILE = os.path.join(os.path.dirname(__file__), "nsidc_smap_opendap_url.txt")
_SMAP_BASE_URL = None


def SMAP_BASE_URL():
    global _SMAP_BASE_URL
    if _SMAP_BASE_URL is not None:
        return _SMAP_BASE_URL
    BASE_URL = "https://n5eil01u.ecs.nsidc.org/opendap/SMAP"
    try:
        with open(SMAP_BASE_URL_FILE, "r") as fid:
            rf = fid.read()
        if "https://" in rf and "nsidc.org" in rf:
            BASE_URL = rf
    except Exception as e:
        _logger.warning("Could not retrieve SMAP url from %s: " % (SMAP_BASE_URL_FILE) + str(e))
        rf = None
    try:
        r = requests.get("https://s3.amazonaws.com/podpac-s3/settings/nsidc_smap_opendap_url.txt").text
        if "https://" in r and "nsidc.org" in r:
            if rf != r:
                _logger.warning("Updating SMAP url from PODPAC S3 Server.")
                BASE_URL = r
                try:
                    with open(SMAP_BASE_URL_FILE, "w") as fid:
                        fid.write(r)
                except Exception as e:
                    _logger.warning("Could not overwrite SMAP url update on disk:" + str(e))
    except Exception as e:
        _logger.warning("Could not retrieve SMAP url from PODPAC S3 Server. Using default." + str(e))
    _SMAP_BASE_URL = BASE_URL
    return BASE_URL


class SMAPSessionMixin(authentication.RequestsSessionMixin):
    """SMAP requests authentication session.
    Implements :class:`authentication.RequestsSessionMixin` with hostname specific to SMAP authentication.
    Overrides the :meth:`requests.Session.rebuild_auth` method to handle authorization redirect from the Earthdata portal
    """

    hostname = "urs.earthdata.nasa.gov"
    auth_required = True
    product_url = SMAP_BASE_URL()

    @cached_property
    def session(self):
        """Requests Session object for making calls to remote `self.hostname`
        See https://2.python-requests.org/en/master/api/#sessionapi
        
        Returns
        -------
        :class:requests.Session
            Requests Session class with `auth` attribute defined
        """

        s = self._create_session()

        # override `rebuild_auth` method
        s.rebuild_auth = self._rebuild_auth

        return s

    def _rebuild_auth(self, prepared_request, response):
        """
        Overrides from the library to keep headers when redirected to or from
        the NASA auth host.
        See https://2.python-requests.org/en/master/api/#requests.Session.rebuild_auth
        
        Parameters
        ----------
        prepared_request : :class:`requests.Request`
            See https://2.python-requests.org/en/master/api/#requests.Session.rebuild_auth
        response : :class:`requests.Response`
            See https://2.python-requests.org/en/master/api/#requests.Session.rebuild_auth
        
        Returns
        -------
        None
        """
        headers = prepared_request.headers
        url = prepared_request.url

        if "Authorization" in headers:
            original_parsed = requests.utils.urlparse(response.request.url)
            redirect_parsed = requests.utils.urlparse(url)

            # delete Authorization headers if original and redirect do not match
            # is not in product_url_regex
            if (
                (original_parsed.hostname != redirect_parsed.hostname)
                and redirect_parsed.hostname != self.hostname
                and original_parsed.hostname != self.hostname
            ):

                # parse product_url for hostname
                product_url_hostname = requests.utils.urlparse(self.product_url).hostname

                # make all numbers in product_url_hostname wildcards
                product_url_regex = (
                    re.compile(re.sub(r"\d", r"\\d", product_url_hostname))
                    if product_url_hostname is not None
                    else None
                )

                # if redirect matches product_url_regex, then allow the headers to stay
                if product_url_regex is not None and product_url_regex.match(redirect_parsed.hostname):
                    pass
                else:
                    del headers["Authorization"]

        return


class SMAPCompositor(OrderedCompositor):
    """

    Attributes
    ----------
    sources : list
        Source nodes, in order of preference. Later sources are only used where earlier sources do not provide data.
    source_coordinates : :class:`podpac.Coordinates`
        Coordinates that make each source unique. Must the same size as ``sources`` and single-dimensional.
    shared_coordinates : :class:`podpac.Coordinates`.
        Coordinates that are shared amongst all of the composited sources.
    is_source_coordinates_complete : Bool
        This flag is used to automatically construct coordinates as on optimization. Default is False.
        For example, if the source coordinates could include the year-month-day of the source, but the actual source
        also has hour-minute-second information, the source_coordinates is incomplete.
    """

    is_source_coordinates_complete = tl.Bool(False)
    shared_coordinates = tl.Instance(Coordinates, allow_none=True, default_value=None)

    def select_sources(self, coordinates):
        """Select sources based on requested coordinates, including setting coordinates, if possible.
        
        Parameters
        ----------
        coordinates : :class:`podpac.Coordinates`
            Coordinates to evaluate at compositor sources
        
        Returns
        -------
        sources : :class:`np.ndarray`
            Array of sources

        Notes
        -----
         * If :attr:`source_coordinates` is defined, only sources that intersect the requested coordinates are selected.
         * Sets sources :attr:`interpolation`.
         * If source coordinates complete, sets sources :attr:`coordinates` as an optimization.
        """

        """ Optimization: . """

        src_subset = super(SMAPCompositor, self).select_sources(coordinates)

        if self.is_source_coordinates_complete:
            coords_subset = list(self.source_coordinates.intersect(coordinates, outer=True).coords.values())[0]
            coords_dim = list(self.source_coordinates.dims)[0]
            crs = self.source_coordinates.crs
            for s, c in zip(src_subset, coords_subset):
                nc = merge_dims(
                    [
                        Coordinates(np.atleast_1d(c), dims=[coords_dim], crs=crs, validate_crs=False),
                        self.shared_coordinates,
                    ]
                )
                s.set_coordinates(nc)

        return src_subset


@common_doc(COMMON_DOC)
class SMAPSource(SMAPSessionMixin, DiskCacheMixin, PyDAP):
    """Accesses SMAP data given a specific openDAP URL. This is the base class giving access to SMAP data, and knows how
    to extract the correct coordinates and data keys for the soil moisture data.

    Attributes
    ----------
    date_file_url_re : SRE_Pattern
        Regular expression used to retrieve date from self.source (OpenDAP Url)
    date_time_file_url_re : SRE_Pattern
        Regular expression used to retrieve date and time from self.source (OpenDAP Url)
    layer_key : str
        Key used to retrieve data from OpenDAP dataset. This specifies the key used to retrieve the data
    nan_vals : list
        List of values that should be treated as no-data (these are replaced by np.nan)
    root_data_key : str
        String the prepends every or most keys for data in the OpenDAP dataset
    """

    layer_key = tl.Unicode().tag(attr=True)
    root_data_key = tl.Unicode().tag(attr=True)
    nan_vals = [-9999.0]
    cache_coordinates = tl.Bool(True)

    # date_url_re = re.compile('[0-9]{4}\.[0-9]{2}\.[0-9]{2}')
    date_time_file_url_re = re.compile("[0-9]{8}T[0-9]{6}")
    date_file_url_re = re.compile("[0-9]{8}")

    @tl.default("root_data_key")
    def _rootdatakey_default(self):
        return SMAP_PRODUCT_MAP.sel(product=self.product, attr="root_data_key").item()

    @tl.default("layer_key")
    def _layerkey_default(self):
        return SMAP_PRODUCT_MAP.sel(product=self.product, attr="layer_key").item()

    @property
    def product(self):
        """SMAP product from the OpenDAP URL"""

        src = self.source.split("/")
        return src[src.index("SMAP") + 1].split(".")[0]

    @property
    def version(self):
        """SMAP product version from the OpenDAP URL
        """
        src = self.source.split("/")
        return int(src[src.index("SMAP") + 1].split(".")[1])

    @property
    def data_key(self):
        """PyDAP data_key, constructed from the layer_key and root_data_key"""

        return self.layer_key.format(rdk=self.root_data_key)

    @property
    def lat_key(self):
        """OpenDap dataset key for latitude. """

        return SMAP_PRODUCT_MAP.sel(product=self.product, attr="lat_key").item().format(rdk=self.root_data_key)

    @property
    def lon_key(self):
        """OpenDap dataset key for longitude. """

        return SMAP_PRODUCT_MAP.sel(product=self.product, attr="lon_key").item().format(rdk=self.root_data_key)

    @cached_property
    def available_times(self):
        """Retrieve the available times from the SMAP file.

        This is primarily based on the filename, but some products have multiple times stored in a single file.

        Returns
        -------
        np.ndarray(dtype=np.datetime64)
            Available times in the SMAP source
        """

        m = self.date_time_file_url_re.search(self.source)
        if not m:
            m = self.date_file_url_re.search(self.source)
        times = m.group()
        times = smap2np_date(times)
        if "SM_P_" in self.source:
            times = times + np.array([6, 18], "timedelta64[h]")
        return times

    @common_doc(COMMON_DOC)
    def get_coordinates(self):
        """{get_coordinates}
        """
        lons = np.array(self.dataset[self.lon_key][:, :])
        lats = np.array(self.dataset[self.lat_key][:, :])
        lons[lons == self.nan_vals[0]] = np.nan
        lats[lats == self.nan_vals[0]] = np.nan
        lons = np.nanmean(lons, axis=0)
        lats = np.nanmean(lats, axis=1)
        coords = Coordinates([self.available_times, lats, lons], dims=["time", "lat", "lon"])
        return coords

    @common_doc(COMMON_DOC)
    def get_data(self, coordinates, coordinates_index):
        """{get_data}
        """
        # We actually ignore the time slice
        s = tuple([slc for d, slc in zip(coordinates.dims, coordinates_index) if "time" not in d])
        if "SM_P_" in self.source:
            d = self.create_output_array(coordinates)
            am_key = self.layer_key.format(rdk=self.root_data_key + "AM")
            pm_key = self.layer_key.format(rdk=self.root_data_key + "PM") + "_pm"

            try:
                t = self.coordinates.coords["time"][0]
                d.loc[dict(time=t)] = np.array(self.dataset[am_key][s])
            except:
                pass

            try:
                t = self.coordinates.coords["time"][1]
                d.loc[dict(time=t)] = np.array(self.dataset[pm_key][s])
            except:
                pass

        else:
            data = np.array(self.dataset[self.data_key][s])
            d = self.create_output_array(coordinates, data=data.reshape(coordinates.shape))

        return d


class SMAPProperties(SMAPSource):
    """Accesses properties related to the generation of SMAP products. 

    Attributes
    ----------
    property : str
        A SMAP property, which includes: 
                        'clsm_dzsf', 'mwrtm_bh', 'clsm_cdcr2', 'mwrtm_poros',
                        'clsm_dzgt3', 'clsm_dzgt2', 'mwrtm_rghhmax',
                        'mwrtm_rghpolmix', 'clsm_dzgt1', 'clsm_wp', 'mwrtm_lewt',
                        'clsm_dzgt4', 'clsm_cdcr1', 'cell_elevation',
                        'mwrtm_rghwmin', 'clsm_dzrz', 'mwrtm_vegcls', 'mwrtm_bv',
                        'mwrtm_rghwmax', 'mwrtm_rghnrh', 'clsm_dztsurf',
                        'mwrtm_rghhmin', 'mwrtm_wangwp', 'mwrtm_wangwt',
                        'clsm_dzgt5', 'clsm_dzpr', 'clsm_poros',
                        'cell_land_fraction', 'mwrtm_omega', 'mwrtm_soilcls',
                        'clsm_dzgt6', 'mwrtm_rghnrv', 'mwrtm_clay', 'mwrtm_sand'
    source : str, optional
         Source OpenDAP url for SMAP properties. Default is (SMAP_BASE_URL() + 
                                                             'SPL4SMLM{latest_version}/2015.03.31/'
                                                             'SMAP_L4_SM_lmc_00000000T000000_Vv{latest_version}.h5')
    """

    source = tl.Unicode().tag(attr=True)
    file_url_re = re.compile(r"SMAP.*_[0-9]{8}T[0-9]{6}_.*\.h5")

    @tl.default("source")
    def _property_source_default(self):
        v = _infer_SMAP_product_version("SPL4SMLM", SMAP_BASE_URL(), self.session)
        url = SMAP_BASE_URL() + "/SPL4SMLM.%03d/2015.03.31/" % (v)
        r = _get_from_url(url, session=self.session)
        if not r:
            return "None"
        n = self.file_url_re.search(r.text).group()
        return url + n

    property = tl.Enum(
        [
            "clsm_dzsf",
            "mwrtm_bh",
            "clsm_cdcr2",
            "mwrtm_poros",
            "clsm_dzgt3",
            "clsm_dzgt2",
            "mwrtm_rghhmax",
            "mwrtm_rghpolmix",
            "clsm_dzgt1",
            "clsm_wp",
            "mwrtm_lewt",
            "clsm_dzgt4",
            "clsm_cdcr1",
            "cell_elevation",
            "mwrtm_rghwmin",
            "clsm_dzrz",
            "mwrtm_vegcls",
            "mwrtm_bv",
            "mwrtm_rghwmax",
            "mwrtm_rghnrh",
            "clsm_dztsurf",
            "mwrtm_rghhmin",
            "mwrtm_wangwp",
            "mwrtm_wangwt",
            "clsm_dzgt5",
            "clsm_dzpr",
            "clsm_poros",
            "cell_land_fraction",
            "mwrtm_omega",
            "mwrtm_soilcls",
            "clsm_dzgt6",
            "mwrtm_rghnrv",
            "mwrtm_clay",
            "mwrtm_sand",
        ]
    ).tag(attr=True)

    @tl.default("layer_key")
    def _layerkey_default(self):
        return "{rdk}" + self.property

    @common_doc(COMMON_DOC)
    def get_coordinates(self):
        """{get_coordinates}
        """
        lons = np.array(self.dataset[self.lon_key][:, :])
        lats = np.array(self.dataset[self.lat_key][:, :])
        lons[lons == self.nan_vals[0]] = np.nan
        lats[lats == self.nan_vals[0]] = np.nan
        lons = np.nanmean(lons, axis=0)
        lats = np.nanmean(lats, axis=1)
        coords = Coordinates([lats, lons], dims=["lat", "lon"])
        return coords


class SMAPPorosity(SMAPProperties):
    """Retrieve the specific SMAP property: Porosity

    Attributes
    ----------
    property : str, Optional
        Uses 'clsm_poros'
    """

    property = tl.Unicode("clsm_poros")


class SMAPWilt(SMAPProperties):
    """Retrieve the specific SMAP property: Wilting Point

    Attributes
    ----------
    property : str, Optional
        Uses 'clsm_wp'
    """

    property = tl.Unicode("clsm_wp")


@common_doc(COMMON_DOC)
class SMAPDateFolder(SMAPSessionMixin, DiskCacheMixin, SMAPCompositor):
    """Compositor of all the SMAP source urls present in a particular folder which is defined for a particular date

    Attributes
    ----------
    base_url : {base_url}
    date_time_url_re : SRE_Pattern
        Regular expression used to retrieve the date and time from the filename if file_url_re matches
    date_url_re : SRE_Pattern
        Regular expression used to retrieve the date from the filename if file_url_re2 matches
    file_url_re : SRE_Pattern
        Regular expression used to find files in a folder that match the expected format of a SMAP source file
    file_url_re2 : SRE_Pattern
        Same as file_url_re, but for variation of SMAP files that do not contain time in the filename
    folder_date : str
        The name of the folder. This is used to construct the OpenDAP URL from the base_url
    latlon_delta : float, optional
        Default is 1.5 degrees. For SMAP files that contain LAT-LON data (i.e. SMAP-Sentinel), how many degrees does the
        tile cover?
    latlon_url_re : SRE_Pattern
        Regular expression used to find the lat-lon coordinates associated with the file from the file name
    layer_key : {layer_key}
    product : str
        {product}
    version : int
        {version}
    """

    base_url = tl.Unicode().tag(attr=True)
    product = tl.Enum(SMAP_PRODUCT_MAP.coords["product"].data.tolist()).tag(attr=True)
    version = tl.Int(allow_none=True).tag(attr=True)
    folder_date = tl.Unicode("").tag(attr=True)
    layer_key = tl.Unicode().tag(attr=True)
    latlon_delta = tl.Float(default_value=1.5).tag(attr=True)

    file_url_re = re.compile(r".*_[0-9]{8}T[0-9]{6}_.*\.h5")
    file_url_re2 = re.compile(r".*_[0-9]{8}_.*\.h5")
    date_time_url_re = re.compile(r"[0-9]{8}T[0-9]{6}")
    date_url_re = re.compile(r"[0-9]{8}")
    latlon_url_re = re.compile(r"[0-9]{3}[E,W][0-9]{2}[N,S]")

    # list of attribute names, used by __repr__ and __str__ to display minimal info about the node
    _repr_keys = ["product", "folder_date"]

    @tl.default("base_url")
    def _base_url_default(self):
        return SMAP_BASE_URL()

    @tl.default("version")
    def _detect_product_version(self):
        return _infer_SMAP_product_version(self.product, self.base_url, self.session)

    @tl.default("layer_key")
    def _layerkey_default(self):
        return SMAP_PRODUCT_MAP.sel(product=self.product, attr="layer_key").item()

    @tl.default("shared_coordinates")
    def _default_shared_coordinates(self):
        """Coordinates that are shared by all files in the folder."""

        if self.product in SMAP_INCOMPLETE_SOURCE_COORDINATES:
            return None
        coords = copy.deepcopy(self.sources[0].coordinates)
        return coords.drop("time")

    @cached_property
    def folder_url(self):
        """URL to OpenDAP dataset folder

        Returns
        -------
        str
            URL to OpenDAP dataset folder
        """
        return "/".join([self.base_url, "%s.%03d" % (self.product, self.version), self.folder_date])

    @cached_property
    def sources(self):
        """SMAPSource objects pointing to URLs of specific SMAP files in the folder"""

        # Swapped the try and except blocks. SMAP filenames may change version numbers, which causes cached source to
        # break. Hence, try to get the new source everytime, unless data is offline, in which case rely on the cache.
        try:
            _, _, sources = self.available_coords_sources
        except:  # No internet or authentication error
            try:
                sources = self.get_cache("sources")
            except NodeException as e:
                raise NodeException(
                    "Connection or Authentication error, and no disk cache to fall back on for determining sources."
                )

        else:
            self.put_cache(sources, "sources", overwrite=True)

        time_crds = self.source_coordinates["time"]
        if time_crds.is_monotonic and time_crds.is_uniform and time_crds.size > 1:
            tol = time_crds.coordinates[1] - time_crds.coordinates[0]
        else:
            tol = self.source_coordinates["time"].coordinates[0]
            tol = tol - tol
            tol = np.timedelta64(1, dtype=(tol.dtype))

        kwargs = {"layer_key": self.layer_key, "interpolation": {"method": "nearest", "time_tolerance": tol}}
        return [SMAPSource(source="%s/%s" % (self.folder_url, s), **kwargs) for s in sources]

    @property
    def is_source_coordinates_complete(self):
        """Flag use to optimize creation of coordinates. If the source_coordinates are complete,
        coordinates can easily be reconstructed, and same with shared coordinates. 

        Returns
        -------
        bool
            Flag indicating whether the source coordinates completely describe the source's coordinates for that dimension
        """
        return self.product not in SMAP_INCOMPLETE_SOURCE_COORDINATES

    @cached_property
    def source_coordinates(self):
        """{source_coordinates}"""

        try:
            times, latlon, _ = self.available_coords_sources
        except:
            try:
                return self.get_cache("source.coordinates")
            except NodeException as e:
                raise NodeException(
                    "Connection or Authentication error, and no disk cache to fall back on for determining sources."
                )
        else:
            if latlon is not None and latlon.size > 0:
                crds = Coordinates([[times, latlon[:, 0], latlon[:, 1]]], dims=["time_lat_lon"])
            else:
                crds = Coordinates([times], dims=["time"])
            self.put_cache(crds, "source.coordinates", overwrite=True)
            return crds

    # TODO just return the elements, then return each actual thing separately
    @cached_property
    def available_coords_sources(self):
        """Read NSIDC site for available coordinate sources

        Returns
        -------
        np.ndarray
            Available times of sources in the folder
        np.ndarray
            Available lat lon coordinates of sources in the folder, None if empty
        np.ndarray
            The url's of the sources

        Raises
        ------
        RuntimeError
            If the NSIDC website cannot be accessed 
        """
        r = _get_from_url(self.folder_url, self.session)
        if r is None:
            _logger.warning("Could not contact {} to retrieve source coordinates".format(self.folder_url))
            return np.array([]), None, np.array([])
        soup = BeautifulSoup(r.text, "lxml")
        a = soup.find_all("a")
        file_regex = self.file_url_re
        file_regex2 = self.file_url_re2
        date_time_regex = self.date_time_url_re
        date_regex = self.date_url_re
        latlon_regex = self.latlon_url_re
        times = []
        latlons = []
        sources = []
        for aa in a:
            t = aa.get_text().strip("\n")
            if "h5.iso.xml" in t:
                continue
            m = file_regex.match(t)
            m2 = file_regex2.match(t)

            lonlat = None
            if m:
                date_time = date_time_regex.search(m.group()).group()
                times.append(smap2np_date(date_time))

            elif m2:
                m = m2
                date = date_regex.search(m.group()).group()
                times.append(smap2np_date(date))
            if m:
                sources.append(m.group())
                lonlat = latlon_regex.search(m.group())
            if lonlat:
                lonlat = lonlat.group()
                latlons.append(
                    (
                        float(lonlat[4:6]) * (1 - 2 * (lonlat[6] == "S")),
                        float(lonlat[:3]) * (1 - 2 * (lonlat[3] == "W")),
                    )
                )

        times = np.atleast_1d(np.array(times).squeeze())
        latlons = np.array(latlons)
        sources = np.array(sources)
        I = np.argsort(times)
        if latlons.shape[0] == times.size:
            return times[I], latlons[I], sources[I]
        return times[I], None, sources[I]

    @property
    @common_doc(COMMON_DOC)
    def keys(self):
        """{keys}
        """
        return self.sources[0].keys


@common_doc(COMMON_DOC)
class SMAP(SMAPSessionMixin, DiskCacheMixin, SMAPCompositor):
    """Compositor of all the SMAPDateFolder's for every available SMAP date. Essentially a compositor of all SMAP data
    for a particular product.

    Attributes
    ----------
    base_url : {base_url}
    date_url_re : SRE_Pattern
        Regular expression used to extract all folder dates (or folder names) for the particular SMAP product.
    layer_key : {layer_key}
    product : str
        {product}
    """

    base_url = tl.Unicode().tag(attr=True)
    product = tl.Enum(SMAP_PRODUCT_MAP.coords["product"].data.tolist(), default_value="SPL4SMAU").tag(attr=True)
    version = tl.Int(allow_none=True).tag(attr=True)
    layer_key = tl.Unicode().tag(attr=True)

    date_url_re = re.compile(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}")

    _repr_keys = ["product"]

    @tl.default("base_url")
    def _base_url_default(self):
        return SMAP_BASE_URL()

    @tl.default("version")
    def _detect_product_version(self):
        return _infer_SMAP_product_version(self.product, self.base_url, self.session)

    @tl.default("layer_key")
    def _layerkey_default(self):
        return SMAP_PRODUCT_MAP.sel(product=self.product, attr="layer_key").item()

    @tl.default("shared_coordinates")
    def _default_shared_coordinates(self):
        """Coordinates that are shared by all files in the SMAP product family. 

        Notes
        ------
        For example, the gridded SMAP data have the same lat-lon coordinates in every file (global at some resolution), 
        and the only difference between files is the time coordinate. 
        This is not true for the SMAP-Sentinel product, in which case this function returns None
        """
        if self.product in SMAP_INCOMPLETE_SOURCE_COORDINATES:
            return None

        sample_source = SMAPDateFolder(product=self.product, version=self.version, folder_date=self.available_dates[0])
        return sample_source.shared_coordinates

    @cached_property
    def available_dates(self):
        """ Available dates in SMAP date format, sorted."""
        url = "/".join([self.base_url, "%s.%03d" % (self.product, self.version)])
        r = _get_from_url(url, self.session)
        if r is None:
            _logger.warning("Could not contact {} to retrieve source coordinates".format(url))
            return []
        soup = BeautifulSoup(r.text, "lxml")
        matches = [self.date_url_re.match(a.get_text()) for a in soup.find_all("a")]
        dates = [m.group() for m in matches if m]
        return dates

    @cached_property
    def sources(self):
        """Array of SMAPDateFolder objects pointing to specific SMAP folders"""

        kwargs = {
            "product": self.product,
            "version": self.version,
            "layer_key": self.layer_key,
            "shared_coordinates": self.shared_coordinates,  # this is an optimization
        }
        return [SMAPDateFolder(folder_date=date, **kwargs) for date in self.available_dates]

    @common_doc(COMMON_DOC)
    @cached_property
    def source_coordinates(self):
        """{source_coordinates}
        """
        available_times = [np.datetime64(date.replace(".", "-")) for date in self.available_dates]
        return Coordinates([available_times], dims=["time"])

    @property
    def base_ref(self):
        """Summary

        Returns
        -------
        TYPE
            Description
        """
        return "{0}_{1}".format(self.__class__.__name__, self.product)

    @property
    @common_doc(COMMON_DOC)
    def keys(self):
        """{keys}
        """
        return self.sources[0].keys

    @common_doc(COMMON_DOC)
    def find_coordinates(self):
        """
        {coordinates}
        
        Notes
        -----
        These coordinates are computed, assuming dataset is regular.
        """
        if self.product in SMAP_IRREGULAR_COORDINATES:
            raise Exception("Native coordinates too large. Try using get_filename_coordinates_sources().")

        partial_sources = self.source_coordinates["time"].coordinates
        complete_source_0 = self.sources[0].source_coordinates["time"].coordinates
        offset = complete_source_0 - partial_sources[0]
        full_times = (partial_sources[:, None] + offset[None, :]).ravel()
        return [podpac.coordinates.merge_dims([Coordinates([full_times], ["time"]), self.shared_coordinates])]

    def get_filename_coordinates_sources(self, bounds=None, update_cache=False):
        """Returns coordinates solely based on the filenames of the sources. This function was motivated by the 
        SMAP-Sentinel product, which does not have regularly stored tiles (in space and time). 

        Parameters
        -----------
        bounds: :class:`podpac.Coordinates`, Optional
            Default is None. Return the coordinates based on filenames of the source only within the specified bounds. 
            When not None, the result is not cached.
            
        update_cache: bool, optional
            Default is False. The results of this call are automatically cached to disk. This function will try to 
            update the cache if new data arrives. Only set this flag to True to rebuild_auth the entire index locally (which
            may be needed when version numbers in the filenames change).

        Returns
        -------
        :class:`podpac.Coordinates` 
            Coordinates of all the sources in the product family
        Container
            Container that will generate an array of the SMAPSources pointing to unique OpenDAP urls corresponding to
            the returned coordinates
        

        Notes
        ------
        The outputs of this function can be used to find source that overlap spatially or temporally with a subset 
        region specified by the user.

        If 'bounds' is not specified, the result is cached for faster future access after the first invocation.
        
        This call uses NASA's Common Metadata Repository (CMR) and requires an internet connection.
        """

        def cmr_query(kwargs=None, bounds=None):
            """ Helper function for making and parsing cmr queries. This is used for building the initial index
            and for updating the cached index with new data.
            """
            if not kwargs:
                kwargs = {}

            # Set up regular expressions and maps to convert filenames to coordinates
            date_re = self.sources[0].date_url_re
            date_time_re = self.sources[0].date_time_url_re
            latlon_re = self.sources[0].latlon_url_re

            def datemap(x):
                m = date_time_re.search(x)
                if not m:
                    m = date_re.search(x)
                return smap2np_date(m.group())

            def latlonmap(x):
                m = latlon_re.search(x)
                if not m:
                    return ()
                lonlat = m.group()
                return (
                    float(lonlat[4:6]) * (1 - 2 * (lonlat[6] == "S")),
                    float(lonlat[:3]) * (1 - 2 * (lonlat[3] == "W")),
                )

            # Restrict the query to any specified bounds
            if bounds:
                kwargs["temporal"] = ",".join([str(b.astype("datetime64[s]")) for b in bounds["time"].bounds])

            # Get CMR data
            filenames = nasaCMR.search_granule_json(
                session=self.session, entry_map=lambda x: x["producer_granule_id"], short_name=self.product, **kwargs
            )
            if not filenames:
                return Coordinates([]), [], []

            # Extract coordinate information from filenames
            # filenames.sort()  # Assume it comes sorted...
            dims = ["time"]
            dates = [d for d in np.array(list(map(datemap, filenames))).squeeze()]
            coords = [dates]
            if latlonmap(filenames[0]):
                latlons = list(map(latlonmap, filenames))
                lats = np.array([l[0] for l in latlons])
                lons = np.array([l[1] for l in latlons])
                dims = ["time_lat_lon"]
                coords = [[dates, lats, lons]]

            # Create PODPAC Coordinates object, and return relevant data structures
            crds = Coordinates(coords, dims)
            return crds, filenames, dates

        # Create kwargs for making a SMAP source
        create_kwargs = {"layer_key": self.layer_key}
        if self.interpolation:
            create_kwargs["interpolation"] = self.interpolation

        try:  # Try retrieving index from cache
            if update_cache:
                raise NodeException
            crds, sources = (self.get_cache("filename.coordinates"), self.get_cache("filename.sources"))
            try:  # update the cache
                # Specify the bounds based on the last entry in the cached coordinates
                # Add a minute to the bounds to make sure we get unique coordinates
                kwargs = {
                    "temporal": str(crds["time"].bounds[-1].astype("datetime64[s]") + np.timedelta64(5, "m")) + "/"
                }
                crds_new, filenames_new, dates_new = cmr_query(kwargs)

                # Update the cached coordinates
                if len(filenames_new) > 1:
                    # Append the new coordinates to the relevant data structures
                    crdsfull = podpac.coordinates.concat([crds, crds_new])
                    sources.filenames.extend(filenames_new)
                    sources.dates.extend(dates_new)

                    # Make sure the coordinates are unique
                    # (we actually know SMAP-Sentinel is NOT unique, so we can't do this)
                    # crdsunique, inds = crdsfull.unique(return_indices=True)
                    # sources.filenames = np.array(sources.filenames)[inds[0]].tolist()
                    # sources.dates = np.array(sources.dates)[inds[0]].tolist()

                    # Update the cache
                    if filenames_new:
                        self.put_cache(crdsfull, "filename.coordinates", overwrite=True)
                        self.put_cache(sources, "filename.sources", overwrite=True)

            except Exception as e:  # likely a connection or authentication error
                _logger.warning("Failed to update cached filenames: ", str(e))

            if bounds:  # Restrict results to user-specified bounds
                crds, I = crds.intersect(bounds, outer=True, return_indices=True)
                sources = sources.intersect(I[0])

        except NodeException:  # Not in cache or forced update
            crds, filenames, dates = cmr_query(bounds=bounds)
            sources = GetSMAPSources(self.product, filenames, dates, create_kwargs)

            if bounds is None:
                self.put_cache(crds, "filename.coordinates", overwrite=update_cache)
                self.put_cache(sources, "filename.sources", overwrite=update_cache)

        # Updates interpolation and/or other keyword arguments in the sources class
        sources.create_kwargs = create_kwargs
        return crds, sources


class SMAPBestAvailable(OrderedCompositor):
    """Compositor of SMAP-Sentinel and the Level 4 SMAP Analysis Update soil moisture
    """

    @cached_property
    def sources(self):
        """Orders the compositor of SPL2SMAP_S in front of SPL4SMAU. """

        return [
            SMAP(interpolation=self.interpolation, product="SPL2SMAP_S"),
            SMAP(interpolation=self.interpolation, product="SPL4SMAU"),
        ]


class GetSMAPSources(object):
    def __init__(self, product, filenames, dates, create_kwargs):
        self.product = product
        self.filenames = filenames
        self.dates = dates
        self.create_kwargs = create_kwargs
        self._base_url = None

    def __getitem__(self, slc):
        return_slice = slice(None)
        if not isinstance(slc, slice):
            if isinstance(slc, (np.integer, int)):
                slc = slice(slc, slc + 1)
                return_slice = 0
            else:
                raise ValueError("Invalid slice")
        base_url = self.base_url
        source_urls = [base_url + np2smap_date(d)[:10] + "/" + f for d, f in zip(self.dates[slc], self.filenames[slc])]
        return np.array([SMAPSource(source=s, **self.create_kwargs) for s in source_urls], object)[return_slice]

    @cached_property
    def base_url(self):
        return SMAPDateFolder(product=self.product, folder_date="00001122").folder_url[:-8]

    def __len__(self):
        return len(self.filenames)

    def intersect(self, I):
        return GetSMAPSources(
            product=self.product,
            filenames=[self.filenames[i] for i in I],
            dates=[self.dates[i] for i in I],
            create_kwargs=self.create_kwargs,
        )


if __name__ == "__main__":
    import getpass
    from matplotlib import pyplot
    import podpac

    logging.basicConfig()

    product = "SPL4SMAU"
    interpolation = {"method": "nearest", "params": {"time_tolerance": np.timedelta64(2, "h")}}

    sm = SMAP(product=product, interpolation=interpolation)

    # username = input("Username: ")
    # password = getpass.getpass("Password: ")
    # sm.set_credentials(username=username, password=password)

    # SMAP info
    print(sm)
    print("SMAP Definition:", sm.json_pretty)
    print(
        "SMAP available_dates:",
        "%s - %s (%d)" % (sm.available_dates[0], sm.available_dates[1], len(sm.available_dates)),
    )
    print("SMAP source_coordinates:", sm.source_coordinates)
    print("SMAP shared_coordinates:", sm.shared_coordinates)
    print("Sources:", sm.sources[:3], "... (%d)" % len(sm.sources))

    # sample SMAPDateFolder info
    sm_datefolder = sm.sources[0]
    print("Sample DateFolder:", sm_datefolder)
    print("Sample DateFolder Definition:", sm_datefolder.json_pretty)
    print("Sample DateFolder source_coordinates:", sm_datefolder.source_coordinates)
    print("Sample DateFolder Sources:", sm_datefolder.sources[:3], "... (%d)" % len(sm_datefolder.sources))

    # sample SMAPSource info
    sm_source = sm_datefolder.sources[0]
    print("Sample DAP Source:", sm_source)
    print("Sample DAP Source Definition:", sm_source.json_pretty)
    print("Sample DAP Native Coordinates:", sm_source.coordinates)

    print("Another Sample DAP Native Coordinates:", sm_datefolder.sources[1].coordinates)

    # eval whole world
    c_world = Coordinates(
        [podpac.crange(90, -90, -2.0), podpac.crange(-180, 180, 2.0), "2018-05-19T12:00:00"],
        dims=["lat", "lon", "time"],
    )
    o = sm.eval(c_world)
    o.plot(cmap="gist_earth_r")
    pyplot.axis("scaled")

    # eval points over time
    lat = [45.0, 45.0, 0.0, 45.0]
    lon = [-100.0, 20.0, 20.0, 100.0]
    c_pts = Coordinates([[lat, lon], podpac.crange("2018-05-15T00", "2018-05-19T00", "3,h")], dims=["lat_lon", "time"])

    o = sm.eval(c_pts)
    # sm.threaded = False
    pyplot.plot(ot.time, ot.data.T)

    pyplot.show()
    print("Done")
