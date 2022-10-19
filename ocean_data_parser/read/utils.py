import json
import logging
from datetime import datetime
from io import StringIO
import re
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def test_parsed_dataset(ds):
    # instrument_sn
    if "instrument_sn" not in ds and ds.attrs.get("instrument_sn") is None:
        logger.warning("Failed to retrieve instrument serial number")
    elif "instrument_sn" in ds and ds["instrument_sn"].isna().any():
        logger.warning("Some records aren't associated with instrument serial number")

    # time
    if "time" not in ds:
        logger.warning("Missing time variable")


def rename_variables_to_valid_netcdf(dataset):
    def _transform(variable_name):
        variable_name = re.sub(r"[\(\)\-\s]+", "_", variable_name.strip())
        return re.sub(r"^_|_$", "", variable_name)

    return dataset.rename({key: _transform(key) for key in dataset})


def get_history_handler():
    """Generate a history handler to be use to generate a CF History attribute"""
    nc_logger = StringIO()
    nc_handler = logging.StreamHandler(nc_logger)
    nc_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    nc_handler.setLevel(logging.INFO)
    return nc_logger, nc_handler


def standardize_dataset(ds):
    """Standardize dataset to be easily serializable to netcdf and compatible with ERDDAP"""

    # TODO Specify encoding for some variables (ex time variables)
    for var in ds:
        ds.encoding[var] = {}
        if "datetime" in ds[var].dtype.name:
            ds[var].encoding.update({"units": "seconds since 1970-01-01 00:00:00"})
            if "tz" in ds[var].dtype.name:
                ds[var].encoding["units"] += "Z"
        elif isinstance(
            ds[var].values[0], pd.Timestamp
        ):  # Timestamp variables or timezone aware
            logger.info("Convert Timestamp variable %s to datetime object", var)
            time_var = pd.to_datetime(ds[var])
            encoding = ds[var].encoding
            encoding.update({"units": "seconds since 1970-01-01 00:00:00"})
            if time_var.tz:
                logger.info("Convert %s to UTC timezone", var)
                time_var = time_var.tz_convert("UTC").tz_convert(None)
                encoding["units"] += "Z"
                ds[var].attrs["timezone"] = "UTC"
            attrs = ds[var].attrs
            ds[var] = (ds[var].dims, time_var)
            ds[var].attrs = attrs
            ds[var].encoding = encoding
        elif ds[var].dtype.name == "object":
            ds[var] = ds[var].astype(str)
            ds[var].encoding["dtype"] = "str"

    # Generate geospatial attributes
    # time
    standard_names = {
        ds[var].attrs.get("standard_name"): var
        for var in ds
        if "standard_name" in ds[var].attrs
    }
    time = standard_names.get("time")
    if time:
        t_min = pd.to_datetime(ds[time].min().values)
        t_max = pd.to_datetime(ds[time].max().values)
        dt = t_max - t_min
        ds.attrs.update(
            {
                "time_coverage_start": t_min.isoformat(),
                "time_coverage_end": t_max.isoformat(),
                "time_coverage_duration": dt.isoformat(),
            }
        )

    # lat/long
    lat = standard_names.get("latitude")
    lon = standard_names.get("longitude")
    if lat and lon:
        lat = standard_names["latitude"]
        ds.attrs.update(
            {
                "geospatial_lat_min": ds[lat].min().values,
                "geospatial_lat_max": ds[lat].max().values,
                "geospatial_lat_units": ds[lat].attrs.get("units"),
                "geospatial_lon_min": ds[lon].min().values,
                "geospatial_lon_max": ds[lon].max().values,
                "geospatial_lon_units": ds[lon].attrs.get("units"),
            }
        )

    # depth coverage
    depth = standard_names.get("depth")
    if depth:
        ds.attrs.update(
            {
                "geospatial_vertical_min": ds[depth].min().values,
                "geospatial_vertical_max": ds[depth].max().values,
                "geospatial_vertical_units": ds[depth].attrs.get("units"),
            }
        )

    # Globals
    for att in ds.attrs.keys():
        # Convert dictionaries attributes to json strings
        if isinstance(ds.attrs[att], dict):
            ds.attrs[att] = json.dumps(ds.attrs[att])
        elif type(ds.attrs[att]) in (datetime, pd.Timestamp):
            ds.attrs[att] = ds.attrs[att].isoformat()
        elif type(ds.attrs[att]) in (bool,):
            ds.attrs[att] = str(ds.attrs[att])

    def _consider_attribute(value):
        return type(value) in (dict, list) or (
            (pd.notnull(value) or value in (0, 0.0)) and value != ""
        )

    def _encode_attribute(value):
        if isinstance(value, dict):
            return json.dumps(value)
        elif type(value) in (datetime, pd.Timestamp):
            return value.isoformat().replace("+00:00", "Z")
        elif isinstance(value, bool):
            return str(value)
        else:
            return value

    ds = get_spatial_coverage_attributes(ds)
    ds = standardize_variable_attributes(ds)
    ds.attrs = standardize_global_attributes(ds.attrs)

    # Encode global attributes and drop empty values
    ds.attrs = {
        att: _encode_attribute(value)
        for att, value in ds.attrs.items()
        if _consider_attribute(value)
    }

    # Drop empty variable attributes
    for var in ds:
        ds[var].attrs = {
            attr: _encode_attribute(value)
            for attr, value in ds[var].attrs.items()
            if _consider_attribute(value)
        }

    # Specify encoding for some variables (ex time variables)
    for var in ds:
        ds.encoding[var] = {}
        if "datetime" in ds[var].dtype.name:
            ds[var].encoding.update({"units": "seconds since 1970-01-01 00:00:00"})
            if "tz" in ds[var].dtype.name:
                ds[var].encoding["units"] += "Z"
        elif isinstance(ds[var].dtype, object) and isinstance(
            ds[var].item(0), pd.Timestamp
        ):
            timezone_aware = bool(ds[var].item(0).tz)
            var_attrs = ds[var].attrs
            if ds[var].size == 1:
                ds[var] = ds[var].item(0).tz_convert(None)
            else:
                ds[var] = (
                    ds[var].dims,
                    pd.to_datetime(ds[var].values, utc=timezone_aware).tz_convert(None),
                )
            ds[var].attrs = var_attrs
            ds[var].encoding.update({"units": "seconds since 1970-01-01 00:00:00"})
            if timezone_aware:
                ds[var].attrs["timezone"] = "UTC"
                ds[var].encoding["units"] += "Z"

        elif ds[var].dtype.name == "object":
            ds[var].encoding["dtype"] = "str"

    return ds


def _sort_attributes(attrs, attribute_order):
    """Sort attributes by given order. Attributes missing from the ordered list are followed alphabetically."""
    attrs_output = {attr: attrs[attr] for attr in attribute_order if attr in attrs}
    unknown_order_attrs = dict(
        sorted([attr for attr in attrs.items() if attr not in attribute_order])
    )
    return {**attrs_output, **unknown_order_attrs}


def standardize_global_attributes(attrs):
    """Standardize global attributes order"""
    return _sort_attributes(attrs, global_attributes_order)


def standardize_variable_attributes(ds):
    """
    Method to generate simple generic variable attributes and reorder attributes in a consistent order.
    """
    for var in ds:
        # Generate min/max values attributes
        if (
            ds[var].dtype in [float, int, "float32", "float64", "int64", "int32"]
            and "flag_values" not in ds[var].attrs
        ):
            ds[var].attrs["actual_range"] = tuple(
                np.array((ds[var].min().item(0), ds[var].max().item(0))).astype(
                    ds[var].dtype
                )
            )

        ds[var].attrs = _sort_attributes(ds[var].attrs, variable_attributes_order)
    return ds


def get_spatial_coverage_attributes(
    ds,
    time="time",
    lat="latitude",
    lon="longitude",
    depth="depth",
):
    """
    This method generates the geospatial and time coverage attributes associated to an xarray dataset.
    """
    # TODO add resolution attributes
    time_spatial_coverage = {}
    # time
    if time in ds:
        time_spatial_coverage.update(
            {
                "time_coverage_start": ds[time].min().item(0),
                "time_coverage_end": ds[time].max().item(0),
                "time_coverage_duration": pd.to_timedelta(
                    (ds[time].max() - ds[time].min()).values
                ).isoformat(),
            }
        )

    # lat/long
    if lat in ds and lon in ds:
        time_spatial_coverage.update(
            {
                "geospatial_lat_min": ds[lat].min().item(0),
                "geospatial_lat_max": ds[lat].max().item(0),
                "geospatial_lat_units": ds[lat].attrs.get("units"),
                "geospatial_lon_min": ds[lon].min().item(0),
                "geospatial_lon_max": ds[lon].max().item(0),
                "geospatial_lon_units": ds[lon].attrs.get("units"),
            }
        )

    # depth coverage
    if depth in ds:
        ds["depth"].attrs["positive"] = ds["depth"].attrs.get("positive", "down")
        time_spatial_coverage.update(
            {
                "geospatial_vertical_min": ds[depth].min().item(0),
                "geospatial_vertical_max": ds[depth].max().item(0),
                "geospatial_vertical_units": ds[depth].attrs["units"],
                "geospatial_vertical_positive": "down",
            }
        )

    # Add to global attributes
    ds.attrs.update(time_spatial_coverage)
    return ds


global_attributes_order = [
    "organization",
    "institution",
    "institution_fr",
    "country",
    "ioc_country_code",
    "iso_3166_country_code",
    "ices_edmo_code",
    "sdn_institution_urn",
    "program",
    "project",
    "infoUrl",
    "title",
    "processing_level",
    "summary",
    "comments",
    "platform",
    "sdn_platform_urn",
    "platform_imo_number",
    "platform_vocabulary",
    "cruise_name",
    "cruise_number",
    "cruise_description",
    "chief_scientist",
    "mission_start_date",
    "mission_end_date",
    "platform",
    "platform_name",
    "platform_owner",
    "platform_type",
    "country_of_origin",
    "ices_platform_codes",
    "wmo_platform_code",
    "call_sign",
    "id",
    "naming_authority",
    "original_filename",
    "event_number",
    "profile_direction",
    "event_start_time",
    "event_end_time",
    "initial_latitude",
    "initial_longitude",
    "station",
    "instrument",
    "instrument_type",
    "instrument_model",
    "instrument_serial_number",
    "instrument_vocabulary",
    "instrument_description",
    "instrument_manufacturer_header",
    "date_created",
    "creator_name",
    "creator_email",
    "creator_institution",
    "creator_country",
    "creator_sector",
    "creator_url",
    "creator_type",
    "publisher_name",
    "publisher_email",
    "publisher_country",
    "publisher_url",
    "publisher_type",
    "publisher_institution",
    "date_modified",
    "date_issued",
    "history",
    "time_coverage_start",
    "time_coverage_end",
    "time_coverage_duration",
    "time_coverage_resolution",
    "geospatial_lat_min",
    "geospatial_lat_max",
    "geospatial_lat_units",
    "geospatial_lon_min",
    "geospatial_lon_max",
    "geospatial_lon_units",
    "geospatial_vertical_min",
    "geospatial_vertical_max",
    "geospatial_vertical_units",
    "geospatial_vertical_positive",
    "geospatial_vertical_resolution",
    "cdm_data_type",
    "cdm_profile_variables",
    "keywords",
    "acknowledgement",
    "license",
    "keywords_vocabulary",
    "standard_name_vocabulary",
    "Conventions",
]

variable_attributes_order = [
    "long_name",
    "units",
    "time_zone",
    "scale",
    "standard_name",
    "sdn_parameter_name",
    "sdn_parameter_urn",
    "sdn_uom_urn",
    "sdn_uom_name",
    "ioos_category",
    "gf3_code",
    "source",
    "reference",
    "comments",
    "definition",
    "ancillary_variables",
    "cell_method",
    "actual_range",
    "valid_range",
    "value_min",
    "value_max",
    "mising_value",
    "_FillValue",
    "fileAccessBaseUrl",
    "_Encoding",
    "grid_mapping",
]
