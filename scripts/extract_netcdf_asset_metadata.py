#!/usr/bin/env python3

"""Extract NetCDF asset metadata from remote files.

These shouldn't change, so we do it once and save the data rather than reading
it on the fly.

Progress and status are printed to stderr, so you can redirect stdout to a file.

Usage:
    scripts/extract_netcdf_asset_metadata.py > src/stactools/noaa_cdr/collection-asset-metadata.json
"""

import json
import os.path
import sys
from typing import Dict

import fsspec
import xarray
from tqdm import tqdm

from stactools.noaa_cdr import Cdr

metadata: Dict[str, Dict[str, Dict[str, str]]] = {}
for cdr in Cdr.cdrs():
    print(f"Reading NetCDF files for {cdr.slug()}", file=sys.stderr)
    metadata[cdr.slug()] = {}
    for href in tqdm(cdr.hrefs()):
        key = os.path.splitext(os.path.basename(href))[0]
        with fsspec.open(href) as file:
            with xarray.open_dataset(file, decode_times=False) as dataset:
                metadata[cdr.slug()][key] = {
                    "title": dataset.title,
                    "description": dataset.summary,
                }

json.dump(metadata, sys.stdout)
