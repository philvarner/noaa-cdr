import datetime
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from dateutil.tz import tzutc
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.raster import RasterExtension
from pystac.extensions.scientific import ScientificExtension

import stactools.noaa_cdr.stac
from stactools.noaa_cdr.ocean_heat_content import cog, stac

from .. import test_data


def test_create_collection() -> None:
    collection = stac.create_collection()
    assert collection.id == "noaa-cdr-ocean-heat-content"
    assert len(collection.assets) == 44
    for asset in collection.assets.values():
        assert asset.title is not None
        assert asset.description is not None
        assert asset.media_type == "application/netcdf"
        assert asset.roles
        assert set(asset.roles) == {"data", "source"}

    scientific = ScientificExtension.ext(collection)
    assert scientific.doi == "10.7289/v53f4mvp"
    assert scientific.citation

    collection.set_self_href("")
    collection.validate_all()


def test_create_items_one_netcdf(tmp_path: Path) -> None:
    path = test_data.get_external_data("heat_content_anomaly_0-2000_yearly.nc")
    items = stac.create_items([path], str(tmp_path))
    assert len(items) >= 17
    for item in items:
        assert len(item.assets) == 1
        assert item.datetime is None
        assert item.common_metadata.start_datetime
        year = item.common_metadata.start_datetime.year
        assert item.common_metadata.start_datetime == datetime.datetime(
            year, 1, 1, tzinfo=tzutc()
        )
        assert item.common_metadata.end_datetime == datetime.datetime(
            year, 12, 31, 23, 59, 59, tzinfo=tzutc()
        )
        assert item.common_metadata.updated is None

        assert item.properties["noaa_cdr:interval"] == "yearly"
        assert item.properties["noaa_cdr:max_depth"] == 2000

        proj = ProjectionExtension.ext(item)
        assert proj.epsg == 4326
        assert proj.shape == [180, 360]
        assert proj.transform == [1.0, 0, -180, 0, -1, 90]

        for asset in item.assets.values():
            raster = RasterExtension.ext(asset)
            assert raster.bands
            assert len(raster.bands) == 1
            band = raster.bands[0]
            assert band.nodata == "nan"
            assert band.data_type == "float32"
            assert band.unit == "10^18 joules"

        item.validate()


def test_create_items_one_netcdf_cog_hrefs(tmp_path: Path) -> None:
    path = test_data.get_external_data("heat_content_anomaly_0-2000_yearly.nc")
    items = stac.create_items([path], str(tmp_path))
    subdirectory = tmp_path / "subdirectory"
    subdirectory.mkdir()
    new_paths = list()
    for p in tmp_path.iterdir():
        if p.suffix == ".tif":
            new_path = subdirectory / p.name
            p.rename(new_path)
            new_paths.append(str(new_path))
    new_items = stac.create_items([path], str(tmp_path), cog_hrefs=new_paths)
    assert not any(p.suffix == ".tif" for p in tmp_path.iterdir())
    assert len(new_items) == len(items)


def test_create_items_two_netcdfs_same_items(tmp_path: Path) -> None:
    paths = [
        test_data.get_external_data("heat_content_anomaly_0-2000_yearly.nc"),
        test_data.get_external_data(
            "mean_halosteric_sea_level_anomaly_0-2000_yearly.nc"
        ),
    ]
    items = stac.create_items(paths, str(tmp_path))
    assert len(items) >= 17
    for item in items:
        assert len(item.assets) == 2
        item.validate()


def test_create_items_two_netcdfs_different_items() -> None:
    paths = [
        test_data.get_external_data("heat_content_anomaly_0-2000_yearly.nc"),
        test_data.get_external_data(
            "mean_halosteric_sea_level_anomaly_0-2000_pentad.nc"
        ),
    ]
    with TemporaryDirectory() as temporary_directory:
        items = stac.create_items(paths, temporary_directory)
    assert len(items) >= 80
    for item in items:
        assert len(item.assets) == 1
        item.validate()


def test_create_items_one_netcdf_latest_only(tmp_path: Path) -> None:
    path = test_data.get_external_data("heat_content_anomaly_0-2000_yearly.nc")
    items = stac.create_items([path], str(tmp_path), latest_only=True)
    assert len(items) == 1
    items[0].validate()


@pytest.mark.parametrize(
    "infile,num_cogs",
    [
        ("heat_content_anomaly_0-700_yearly.nc", 67),
        ("heat_content_anomaly_0-2000_monthly.nc", 207),
        ("heat_content_anomaly_0-2000_pentad.nc", 63),
        ("heat_content_anomaly_0-2000_seasonal.nc", 69),
        ("heat_content_anomaly_0-2000_yearly.nc", 17),
        ("mean_halosteric_sea_level_anomaly_0-2000_yearly.nc", 17),
        ("mean_salinity_anomaly_0-2000_yearly.nc", 17),
        ("mean_temperature_anomaly_0-2000_yearly.nc", 17),
        ("mean_thermosteric_sea_level_anomaly_0-2000_yearly.nc", 17),
        ("mean_total_steric_sea_level_anomaly_0-2000_yearly.nc", 17),
    ],
)
def test_cogify(tmp_path: Path, infile: str, num_cogs: int) -> None:
    external_data_path = test_data.get_external_data(infile)
    cogs = cog.cogify(external_data_path, str(tmp_path))
    # Because these netcdfs grow in place, we can never be sure of how many
    # there should be.
    assert len(cogs) >= num_cogs
    for c in cogs:
        assert Path(c.asset().href).exists()


def test_cogify_href(tmp_path: Path) -> None:
    href = (
        "https://www.ncei.noaa.gov/data/oceans/ncei/archive/data"
        "/0164586/derived/heat_content_anomaly_0-2000_yearly.nc"
    )
    cogs = cog.cogify(href, str(tmp_path))
    # Because these netcdfs grow in place, we can never be sure of how many
    # there should be.
    assert len(cogs) >= 17
    for c in cogs:
        assert Path(c.asset().href).exists()


def test_cogify_href_no_output_directory() -> None:
    href = (
        "https://www.ncei.noaa.gov/data/oceans/ncei/archive/data"
        "/0164586/derived/heat_content_anomaly_0-2000_yearly.nc"
    )
    with pytest.raises(Exception):
        cog.cogify(href)


def test_unitless(tmp_path: Path) -> None:
    path = test_data.get_external_data("mean_salinity_anomaly_0-2000_yearly.nc")
    cogs = cog.cogify(path, str(tmp_path))
    assert "unit" not in cogs[0].asset().extra_fields["raster:bands"][0]


def test_cogify_cog_href(tmp_path: Path) -> None:
    path = test_data.get_external_data("heat_content_anomaly_0-2000_yearly.nc")
    cogs = cog.cogify(path, str(tmp_path))
    href = cogs[0].asset().href
    subdirectory = tmp_path / "subdirectory"
    subdirectory.mkdir()
    href = shutil.move(href, subdirectory)
    for p in tmp_path.iterdir():
        if p.suffix == ".tif":
            p.unlink()
    new_cogs = cog.cogify(path, str(tmp_path), cog_hrefs=[href])
    assert not (tmp_path / os.path.basename(href)).exists()
    assert (
        sum(1 for f in os.listdir(tmp_path) if os.path.splitext(f)[1] == ".tif")
        == len(new_cogs) - 1
    )
    assert os.path.exists(href)
    assert href in [new_cog.asset().href for new_cog in new_cogs]


@pytest.mark.parametrize(
    "infile,year,interval",
    [
        ("heat_content_anomaly_0-700_yearly.nc", 1955, "yearly"),
        ("heat_content_anomaly_0-2000_monthly.nc", 2005, "monthly"),
        ("heat_content_anomaly_0-2000_pentad.nc", 1955, "pentadal"),
        ("heat_content_anomaly_0-2000_seasonal.nc", 2005, "seasonal"),
    ],
)
def test_create_netcdf_item(infile: str, year: int, interval: str) -> None:
    path = test_data.get_external_data(infile)
    item = stactools.noaa_cdr.stac.create_item(path, decode_times=False)
    assert item.common_metadata.start_datetime == datetime.datetime(
        year, 1, 1, tzinfo=tzutc()
    )
    assert item.common_metadata.end_datetime
    assert item.common_metadata.end_datetime.year != year
    assert item.properties["noaa_cdr:interval"] == interval
    item.validate()
