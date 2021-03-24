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

url = "https://prd-wret.s3-us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/atoms/files/WRS2_descending_0.zip"
r = urllib.request.urlopen(url)
zip_file = zipfile.ZipFile(io.BytesIO(r.read()))
zip_file.extractall("landsat-path-row")
zip_file.close()


def get_row_path(lat, lon):
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


# ---------------------------------------------------- AWS get data ----------------------------------------------------
import requests
from bs4 import BeautifulSoup
import os, shutil


def get_bands_data(scene, list_of_file_suffix):
    # Request the html text of the download_url from the amazon server.
    response = requests.get(scene.download_url)

    # Check the status code works
    if response.status_code == 200:

        # Import the html to beautiful soup
        html = BeautifulSoup(response.content, 'html.parser')

        # Create the directory to store the files
        storeInFolder = './L8_raw_data'

        # Second loop: for each band of this image that we find using the html <li> tag
        for li in html.find_all('li'):

            # Get the href tag - this links to other pages so we can go through
            # several pages, as each date is its own page.
            filename = li.a[
                'href']  # find_next('a').get('href') #Go to each 'a' html tag and get the url, return string that is the file name

            # check if the last 6 items in file name are in the strings we want
            if filename[-6:] in list_of_file_suffix:
                print('---- Downloading: {}'.format(filename))
                response = requests.get(scene.download_url.replace('index.html', filename),
                                        stream=True)  # replace the index.html part of the url with the filename

                # Download the files
                # code from: https://stackoverflow.com/a/18043472/5361345

                with open(os.path.join(storeInFolder, filename), 'wb') as output:
                    shutil.copyfileobj(response.raw, output)
                del response


# -------------------------------------------------- NDVI computation --------------------------------------------------
import numpy as np
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import os


def get_graph():
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    image_png = buffer.getvalue()
    graph = base64.b64encode(image_png)
    graph = graph.decode('utf-8')
    buffer.close()
    return graph


def compute_NDVI(path):
    print('---- Computing NDVI')

    # Read the images using matplotlib
    path_of_b4 = ""
    path_of_b5 = ""

    for item in os.listdir(path):
        if item.endswith('B4.TIF'):
            path_of_b4 = os.path.join(path, item)
        if item.endswith('B5.TIF'):
            path_of_b5 = os.path.join(path, item)
    band4 = plt.imread(path_of_b4)
    band5 = plt.imread(path_of_b5)

    os.remove(path_of_b4)
    os.remove(path_of_b5)

    # Set the data type to int32 to account for any values that will go beyond the 16-bit range. Turn images into arrays in order to make the NDVI calculation.
    red = np.array(band4, dtype="int32")
    nir = np.array(band5, dtype="int32")

    # Calculate NDVI. Need to account for possible 0 division error, so if the denominator equals 0, then consider the result as 0.
    numerator = np.subtract(nir, red)
    denominator = np.add(red, nir)
    ndvi = np.true_divide(numerator, denominator, where=denominator != 0)

    # Truncate values below 0 to 0. Do this because the NDVI values below 0 are not important ecologically.
    ndvi[ndvi < 0] = 0

    # Turn 0s into nans to get clear background in the image
    ndvi_nan = ndvi.copy()
    ndvi_nan[np.where(abs(
        red) == 0)] = np.nan  # Turns all the values that are 0 to nan, this makes the picture clearer (removes background)
    ndvi32 = ndvi_nan.astype("float32")

    plt.switch_backend('AGG')
    plt.title('NDVI')
    mapPretty = plt.imshow(ndvi32, cmap="Greens")
    mapPretty.set_clim(0, 1)
    plt.colorbar(orientation='horizontal', fraction=0.03)
    plt.axis('off')
    graph = get_graph()
    return graph
