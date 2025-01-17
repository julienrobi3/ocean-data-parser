import logging
import unittest
from glob import glob

from ocean_data_parser import geo

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

geojson_files = glob("./tests/parsers_test_files/geojson/**/*.geojson", recursive=True)


class StationTests(unittest.TestCase):
    def test_nearest_station(self):
        stations = (("first", 50, -120), ("second", 70, -120))
        nearest = geo.get_nearest_station(52, -120, stations=stations)
        assert nearest == "first", "Wrong nearest station was selected"

    def test_nearest_station_with_max_distance(self):
        stations = (("first", 50, -120), ("second", 70, -120))
        nearest = geo.get_nearest_station(
            52, -120, stations=stations, max_distance_from_station_km=10000
        )
        assert nearest == "first", "Wrong nearest station was selected"

    def test_nearest_station_with_too_far_stations(self):
        stations = (("first", 50, -120), ("second", 70, -120))
        nearest = geo.get_nearest_station(
            52, -120, stations=stations, max_distance_from_station_km=1
        )
        assert nearest is None


class GeoJSONTests(unittest.TestCase):
    def test_geojson_parser(self):
        collections = [geo.read_geojson(file) for file in geojson_files]
        assert collections
        assert isinstance(collections[0], dict)

    def test_geo_code(self):
        # parse test files
        geographical_areas = {}
        for file in geojson_files:
            geographical_areas.update(geo.read_geojson(file))

        lat, lon = 48.77228044489474, -62.36630494246806  # south of Anticosti Island
        geo_code = geo.get_geo_code((lon, lat), geographical_areas)
        assert isinstance(geo_code, str)
