from django.contrib.gis.geoip2 import GeoIP2

# Helper Functions


# getting the ip address of the client to locate the initial position
def get_ip_address(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# get the location of an ip
def get_geoip(ip):
    g = GeoIP2()
    country = g.country(ip)
    city = g.city(ip)
    lat, lon = g.lat_lon(ip)

    return country, city, lat, lon


# --------------------------------------- Google Earth Engine ---------------------------------------
# code from https://github.com/giswqs/qgis-earthengine-examples/blob/master/Folium/ee-api-folium-setup.ipynb
import ee
import folium

# ee.Authenticate()
ee.Initialize()


# Define a method for displaying Earth Engine image tiles on a folium map.
def add_ee_layer(self, ee_object, vis_params, name):
    try:
        # display ee.Image()
        if isinstance(ee_object, ee.image.Image):
            map_id_dict = ee.Image(ee_object).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True,
                show=False,
            ).add_to(self)
        # display ee.ImageCollection()
        elif isinstance(ee_object, ee.imagecollection.ImageCollection):
            ee_object_new = ee_object.mosaic()
            map_id_dict = ee.Image(ee_object_new).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True,
                show=False,
            ).add_to(self)
        # display ee.Geometry()
        elif isinstance(ee_object, ee.geometry.Geometry):
            folium.GeoJson(
                data=ee_object.getInfo(),
                name=name,
                overlay=True,
                control=True,
                show=False,
            ).add_to(self)
        # display ee.FeatureCollection()
        elif isinstance(ee_object, ee.featurecollection.FeatureCollection):
            ee_object_new = ee.Image().paint(ee_object, 0, 2)
            map_id_dict = ee.Image(ee_object_new).getMapId(vis_params)
            folium.raster_layers.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True,
                show=False,
            ).add_to(self)

    except:
        print("Could not display {}".format(name))


# Add EE drawing method to folium.
folium.Map.add_ee_layer = add_ee_layer

# ----------------------------------- Convert Latitude and Longitude to Row and Path -----------------------------------
# https://www.earthdatascience.org/tutorials/convert-landsat-path-row-to-lat-lon/

import io
from osgeo import ogr
import osgeo
import shapely.wkt
import shapely.geometry
import urllib.request
import zipfile


def get_row_path(lat, lon):
    url = "https://prd-wret.s3-us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/atoms/files/WRS2_descending_0.zip"
    r = urllib.request.urlopen(url)
    zip_file = zipfile.ZipFile(io.BytesIO(r.read()))
    zip_file.extractall("landsat-path-row")
    zip_file.close()

    shapefile = 'landsat-path-row/WRS2_descending.shp'
    wrs = osgeo.ogr.Open(shapefile)
    layer = wrs.GetLayer(0)

    point = shapely.geometry.Point(lon, lat)
    mode = 'D'

    def checkPoint(feature, point, mode):
        geom = feature.GetGeometryRef()  # Get geometry from feature
        shape = shapely.wkt.loads(geom.ExportToWkt())  # Import geometry into shapely to easily work with our point
        if point.within(shape) and feature['MODE'] == mode:
            return True
        else:
            return False

    i = 0
    while not checkPoint(layer.GetFeature(i), point, mode):
        i += 1
    feature = layer.GetFeature(i)
    path = feature['PATH']
    row = feature['ROW']

    return path, row
