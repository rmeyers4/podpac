"""
Datalib Public API

This module gets imported in the root __init__.py
and exposed its contents to podpac.datalib
"""

import sys

from podpac.datalib import smap
from podpac.datalib.smap import (
    SMAP,
    SMAPBestAvailable,
    SMAPSource,
    SMAPPorosity,
    SMAPProperties,
    SMAPWilt,
    SMAP_PRODUCT_MAP,
)
from podpac.datalib.terraintiles import TerrainTiles
from podpac.datalib.gfs import GFS, GFSLatest
from podpac.datalib.egi import EGI
from podpac.datalib import smap_egi
from podpac.datalib import drought_monitor

# intake requires python >= 3.6
if sys.version >= "3.6":
    from podpac.datalib.intake_catalog import IntakeCatalog
