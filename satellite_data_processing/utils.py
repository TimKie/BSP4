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


# ------------------------------------------------- Google Earth Engine ------------------------------------------------
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


def get_path_row(lat, lon):
    shapefile = 'landsat-path-row/WRS2_descending.shp'
    wrs = osgeo.ogr.Open(shapefile)
    layer = wrs.GetLayer(0)

    point = shapely.geometry.Point(lon, lat)
    mode = 'D'

    def checkPoint(feature, point, mode):
        geom = feature.GetGeometryRef()  # Get geometry from feature
        shape = shapely.wkt.loads(geom.ExportToWkt())  # Import geometry into shapely to easily work with the point
        if point.within(shape) and feature['MODE'] == mode:
            return True
        else:
            return False

    # get all the paths and rows form the features intersecting with the point
    list_of_paths_and_rows = []
    i = 0
    while layer.GetFeature(i) is not None:
        if checkPoint(layer.GetFeature(i), point, mode):
            feature = layer.GetFeature(i)
            path = feature['PATH']
            row = feature['ROW']
            list_of_paths_and_rows.append((path, row))
        i += 1

    return list_of_paths_and_rows


# ---------------------------------------------------- AWS get data ----------------------------------------------------
import requests
from bs4 import BeautifulSoup
import shutil


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
            filename = li.a['href']  # find_next('a').get('href') #Go to each 'a' html tag and get the url, return string that is the file name

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


# ----------------------------------------- Masking data (bands) with shapefile ----------------------------------------
import glob
import rasterio.mask
import geopandas as gpd


def mask_bands(location):
    geoms = gpd.read_file('countries.geojson')
    geoms = geoms.loc[geoms['ADMIN'] == location]

    for filepath in glob.glob("./L8_raw_data/*"):
        # Opening file
        print("---- Masking: {}".format(filepath[14:]))
        band = rasterio.open(filepath)

        # Changing CRS of GeoJson to the one of the bands
        geoms = geoms.to_crs(band.crs)

        # Masking && cropping
        out_image, out_transform = rasterio.mask.mask(band, geoms.geometry, crop=True)

        # Metadata is copied from the source image to the output image
        out_meta = band.meta

        # Update the metadata of the image to reduce the shape to the size of the mask
        out_meta.update({"driver": "GTiff",
                         "height": out_image.shape[1],
                         "width": out_image.shape[2],
                         "transform": out_transform})

        # Write masked image to TIF file
        name = filepath
        with rasterio.open(name, "w", **out_meta) as dest:
            dest.write(out_image)


# ------------------------------------------------ Indicator computation -----------------------------------------------
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


def compute_indicator(path, indicator):
    # initialize graph (overwritten after computation)
    graph = ""

    # Read the images using matplotlib
    path_of_b4 = ""
    path_of_b5 = ""
    path_of_b6 = ""
    path_of_b7 = ""

    for item in os.listdir(path):
        if item.endswith('B4.TIF'):
            path_of_b4 = os.path.join(path, item)
        if item.endswith('B5.TIF'):
            path_of_b5 = os.path.join(path, item)
        if item.endswith('B6.TIF'):
            path_of_b6 = os.path.join(path, item)
        if item.endswith('B7.TIF'):
            path_of_b7 = os.path.join(path, item)
    band4 = plt.imread(path_of_b4)
    band5 = plt.imread(path_of_b5)
    band6 = plt.imread(path_of_b6)
    band7 = plt.imread(path_of_b7)

    # selecting the right computation according to the selected indicator by the user
# ----------------------------- NDVI (Normalized Difference Vegetation Index) computation ------------------------------
    if indicator == 'NDVI':
        print('---- Computing NDVI')

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
        ndvi_nan[np.where(abs(red) == 0)] = np.nan  # Turns all the values that are 0 to nan, this makes the picture clearer (removes background)
        ndvi32 = ndvi_nan.astype("float32")

        plt.switch_backend('AGG')
        plt.title('NDVI')
        mapPretty = plt.imshow(ndvi32, cmap="Greens")
        mapPretty.set_clim(0, 1)
        plt.colorbar(orientation='horizontal', fraction=0.03)
        plt.axis('off')
        graph = get_graph()

# -------------------------------- NDWI (Normalized Difference Water Index) computation --------------------------------
    elif indicator == 'NDWI':
        print('---- Computing NDWI')

        # Set the data type to int32 to account for any values that will go beyond the 16-bit range. Turn images into arrays in order to make the NDWI calculation.
        nir = np.array(band5, dtype="int32")
        swir = np.array(band6, dtype="int32")

        # Calculate NDWI. Need to account for possible 0 division error, so if the denominator equals 0, then consider the result as 0.
        numerator = np.subtract(nir, swir)
        denominator = np.add(swir, nir)
        ndwi = np.true_divide(numerator, denominator, where=denominator != 0)

        # Truncate values below 0 to 0. Do this because the NDWI values below 0 are not important ecologically.
        ndwi[ndwi < 0] = 0

        # Turn 0s into nans to get clear background in the image
        ndwi_nan = ndwi.copy()
        ndwi_nan[np.where(abs(swir) == 0)] = np.nan  # Turns all the values that are 0 to nan, this makes the picture clearer (removes background)
        ndwi32 = ndwi_nan.astype("float32")

        plt.switch_backend('AGG')
        plt.title('NDWI')
        mapPretty = plt.imshow(ndwi32, cmap="Blues")
        mapPretty.set_clim(0, 1)
        plt.colorbar(orientation='horizontal', fraction=0.03)
        plt.axis('off')
        graph = get_graph()

# -------------------------------- NDSI (Normalized Difference Soil Index) computation ---------------------------------
    elif indicator == 'NDSI':
        print('---- Computing NDSI')

        # Set the data type to int32 to account for any values that will go beyond the 16-bit range. Turn images into arrays in order to make the NDSI calculation.
        nir = np.array(band5, dtype="int32")
        swir = np.array(band6, dtype="int32")

        # Calculate NDSI. Need to account for possible 0 division error, so if the denominator equals 0, then consider the result as 0.
        numerator = np.subtract(swir, nir)
        denominator = np.add(swir, nir)
        ndsi = np.true_divide(numerator, denominator, where=denominator != 0)

        # Truncate values below 0 to 0. Do this because the NDSI values below 0 are not important ecologically.
        ndsi[ndsi < 0] = 0

        # Turn 0s into nans to get clear background in the image
        ndsi_nan = ndsi.copy()
        ndsi_nan[np.where(abs(nir) == 0)] = np.nan  # Turns all the values that are 0 to nan, this makes the picture clearer (removes background)
        ndsi32 = ndsi_nan.astype("float32")

        plt.switch_backend('AGG')
        plt.title('NDSI')
        mapPretty = plt.imshow(ndsi32, cmap="YlOrBr")
        mapPretty.set_clim(0, 1)
        plt.colorbar(orientation='horizontal', fraction=0.03)
        plt.axis('off')
        graph = get_graph()

# ------------------------------- SLAVI (Specific Leaf Area Vegetation Index) computation ------------------------------
    elif indicator == 'SLAVI':
        print('---- Computing SLAVI')

        # Set the data type to int32 to account for any values that will go beyond the 16-bit range. Turn images into arrays in order to make the SLAVI calculation.
        red = np.array(band4, dtype="int32")
        nir = np.array(band5, dtype="int32")
        swir = np.array(band6, dtype="int32")

        # Calculate SLAVI. Need to account for possible 0 division error, so if the denominator equals 0, then consider the result as 0.
        numerator = nir
        denominator = np.add(swir, red)
        slavi = np.true_divide(numerator, denominator, where=denominator != 0)

        # Truncate values below 0 to 0. Do this because the SLAVI values below 0 are not important ecologically.
        slavi[slavi < 0] = 0

        # Turn 0s into nans to get clear background in the image
        slavi_nan = slavi.copy()
        slavi_nan[np.where(abs(red) == 0)] = np.nan  # Turns all the values that are 0 to nan, this makes the picture clearer (removes background)
        slavi32 = slavi_nan.astype("float32")

        plt.switch_backend('AGG')
        plt.title('SLAVI')
        mapPretty = plt.imshow(slavi32, cmap="YlGn")
        mapPretty.set_clim(0, 1)
        plt.colorbar(orientation='horizontal', fraction=0.03)
        plt.axis('off')
        graph = get_graph()

# ---------------------------------- NDRE (Normalized Difference Red Edge) computation ---------------------------------
    elif indicator == 'NDRE':
        print('---- Computing NDRE')

        # Set the data type to int32 to account for any values that will go beyond the 16-bit range. Turn images into arrays in order to make the NDRE calculation.
        nir = np.array(band5, dtype="int32")
        swir2 = np.array(band7, dtype="int32")

        # Calculate NDRE. Need to account for possible 0 division error, so if the denominator equals 0, then consider the result as 0.
        numerator = np.subtract(nir, swir2)
        denominator = np.add(swir2, nir)
        ndre = np.true_divide(numerator, denominator, where=denominator != 0)

        # Truncate values below 0 to 0. Do this because the NDRE values below 0 are not important ecologically.
        ndre[ndre < 0] = 0

        # Turn 0s into nans to get clear background in the image
        ndre_nan = ndre.copy()
        ndre_nan[np.where(abs(nir) == 0)] = np.nan  # Turns all the values that are 0 to nan, this makes the picture clearer (removes background)
        ndre32 = ndre_nan.astype("float32")

        plt.switch_backend('AGG')
        plt.title('NDRE')
        mapPretty = plt.imshow(ndre32, cmap="RdYlGn")
        mapPretty.set_clim(0, 1)
        plt.colorbar(orientation='horizontal', fraction=0.03)
        plt.axis('off')
        graph = get_graph()

    # deleting the bands downloaded before as they are not needed anymore
    bands = glob.glob('./L8_raw_data/*')
    for band in bands:
        os.remove(band)

    return graph
