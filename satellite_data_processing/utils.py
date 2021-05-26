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


def get_bands_data(scenes, list_of_file_suffix):
    for i, scene in scenes.iterrows():
        # Request the html text of the download_url from the amazon server.
        response = requests.get(scene.download_url)

        # Check the status code works
        if response.status_code == 200:

            # Import the html to beautiful soup
            html = BeautifulSoup(response.content, 'html.parser')

            # Create the dir where we will put this image files
            entity_dir = os.path.join('./L8_raw_data', scene.productId)
            os.makedirs(entity_dir, exist_ok=True)

            # Second loop: for each band of this image that we find using the html <li> tag
            for li in html.find_all('li'):

                # Get the href tag - this links to other pages so we can go through
                # several pages, as each date is its own page.
                filename = li.a['href']  # find_next('a').get('href') #Go to each 'a' html tag and get the url, return string that is the file name

                # check if the last 6 items in file name are in the strings we want
                if filename[-6:] in list_of_file_suffix:
                    print('---- Downloading: {}'.format(filename))
                    # replace the index.html part of the url with the filename
                    response = requests.get(scene.download_url.replace('index.html', filename), stream=True)

                    # Download the files
                    # code from: https://stackoverflow.com/a/18043472/5361345

                    with open(os.path.join(entity_dir, filename), 'wb') as output:
                        shutil.copyfileobj(response.raw, output)
                    del response


# ----------------------------------------- Masking data (bands) with shapefile ----------------------------------------
import glob
import rasterio.mask
import geopandas as gpd


def mask_bands(location):
    geoms = gpd.read_file('countries.geojson')
    geoms = geoms.loc[geoms['ADMIN'] == location]

    for filepath in glob.glob('./L8_raw_data/*/*.TIF'):
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
    i = 1
    for folder_path in glob.glob(path+'*'):
        # initialize graph (overwritten after computation)
        graph = ""

        # Read the images using matplotlib
        path_of_b4 = ""
        path_of_b5 = ""
        path_of_b6 = ""
        path_of_b7 = ""

        for item in os.listdir(folder_path):
            if item.endswith('B4.TIF'):
                path_of_b4 = os.path.join(folder_path, item)
            if item.endswith('B5.TIF'):
                path_of_b5 = os.path.join(folder_path, item)
            if item.endswith('B6.TIF'):
                path_of_b6 = os.path.join(folder_path, item)
            if item.endswith('B7.TIF'):
                path_of_b7 = os.path.join(folder_path, item)
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

            # writing the NDVI image
            print("writing the NDVI image...")
            b4 = rasterio.open(path_of_b4)
            meta = b4.meta
            meta.update(driver='GTiff')
            meta.update(dtype=rasterio.float32)

            with rasterio.open('./L8_raw_data/OUTPUT' + str(i) + '.tiff', 'w', **meta) as dst:
                dst.write(ndvi32, 1)

            i += 1

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

            # writing the NDWI image
            print("writing the NDWI image...")
            b4 = rasterio.open(path_of_b4)
            meta = b4.meta
            meta.update(driver='GTiff')
            meta.update(dtype=rasterio.float32)

            with rasterio.open('./L8_raw_data/OUTPUT' + str(i) + '.tiff', 'w', **meta) as dst:
                dst.write(ndwi32, 1)

            i += 1

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

            # writing the NDSI image
            print("writing the NDSI image...")
            b4 = rasterio.open(path_of_b4)
            meta = b4.meta
            meta.update(driver='GTiff')
            meta.update(dtype=rasterio.float32)

            with rasterio.open('./L8_raw_data/OUTPUT' + str(i) + '.tiff', 'w', **meta) as dst:
                dst.write(ndsi32, 1)

            i += 1

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

            # writing the SLAVI image
            print("writing the SLAVI image...")
            b4 = rasterio.open(path_of_b4)
            meta = b4.meta
            meta.update(driver='GTiff')
            meta.update(dtype=rasterio.float32)

            with rasterio.open('./L8_raw_data/OUTPUT' + str(i) + '.tiff', 'w', **meta) as dst:
                dst.write(slavi32, 1)

            i += 1

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

            # writing the NDRE image
            print("writing the NDRE image...")
            b4 = rasterio.open(path_of_b4)
            meta = b4.meta
            meta.update(driver='GTiff')
            meta.update(dtype=rasterio.float32)

            with rasterio.open('./L8_raw_data/OUTPUT' + str(i) + '.tiff', 'w', **meta) as dst:
                dst.write(ndre32, 1)

            i += 1



# -------------------------------------------- Plotting bands of all scenes --------------------------------------------
import cartopy.crs as ccrs
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling


def plotting_image(location):
    geoms = gpd.read_file('countries.geojson')
    shapefile = geoms.loc[geoms['ADMIN'] == location]

    xmin, xmax, ymin, ymax = [], [], [], []

    for image_path in glob.glob('L8_raw_data/OUTPUT*'):
        with rasterio.open(image_path) as src_raster:
            xmin.append(src_raster.bounds.left)
            xmax.append(src_raster.bounds.right)
            ymin.append(src_raster.bounds.bottom)
            ymax.append(src_raster.bounds.top)

    fig, ax = plt.subplots(1, 1, figsize=(20, 15), subplot_kw={'projection': ccrs.UTM(16)})

    ax.set_extent([min(xmin), max(xmax), min(ymin), max(ymax)], ccrs.UTM(16))

    # somehow the shape is not plotted on the final image
    shapefile.plot(ax=ax, transform=ccrs.PlateCarree())

    for image_path in glob.glob('L8_raw_data/OUTPUT*'):
        with rasterio.open(image_path) as src_raster:
            extent = [src_raster.bounds[i] for i in [0, 2, 1, 3]]

            dst_transform = from_origin(src_raster.bounds.left, src_raster.bounds.top, 250, 250)

            width = np.ceil((src_raster.bounds.right - src_raster.bounds.left) / 250.).astype('uint')
            height = np.ceil((src_raster.bounds.top - src_raster.bounds.bottom) / 250.).astype('uint')

            dst = np.zeros((height, width))

            """I had to add src_crs and dst_crs in order for the re-project to work"""
            reproject(src_raster.read(1), dst,
                      src_crs=src_raster.crs,
                      dst_crs=src_raster.crs,
                      src_transform=src_raster.transform,
                      dst_transform=dst_transform,
                      resampling=Resampling.nearest)

            ax.matshow(np.ma.masked_equal(dst, 0), extent=extent, transform=ccrs.UTM(16))

    fig.savefig('satellite_data_processing/static/multiple_bands_plot.png')
