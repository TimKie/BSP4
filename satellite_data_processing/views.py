from django.shortcuts import render
from .forms import *
from geopy.geocoders import Nominatim
import folium
from .utils import *
import ee
from folium import plugins


def home(request):
    form_location = FindLocationForm(request.POST or None)
    form_lat_lon = LatLonForm(request.POST or None)

    geolocator = Nominatim(user_agent='satellite_data_processing')

    # initial location which is displayed on the map
    ip = get_ip_address(request)  # this code cannot be used when working with the localhost
    ip = '2.56.107.255'  # so the ip address is overwritten with a static ip address for development
    country, city, initial_location_lat, initial_location_lon = get_geoip(ip)

    initial_location = geolocator.geocode(city)
    initial_location_point = (initial_location_lat, initial_location_lon)

    # initial folium map
    m = folium.Map(location=initial_location_point)

    # location marker
    folium.Marker([initial_location_lat, initial_location_lon], tooltip='click here for more info',
                  popup=initial_location, icon=folium.Icon(color='blue')).add_to(m)

    if form_location.is_valid():
        location_ = form_location.cleaned_data.get('location')
        location = geolocator.geocode(location_)

        # location coordinates
        location_lat = location.latitude
        location_lon = location.longitude
        location_point = (location_lat, location_lon)

        # folium map modification
        m = folium.Map(location=location_point)

        # new location marker
        folium.Marker([location_lat, location_lon], tooltip='click here for more info',
                      popup=location, icon=folium.Icon(color='blue')).add_to(m)

    if form_lat_lon.is_valid():
        lon = form_lat_lon.cleaned_data.get('longitude')
        lat = form_lat_lon.cleaned_data.get('latitude')
        location_point = (lat, lon)

        # folium map modification
        m = folium.Map(location=location_point)

        # new location marker
        folium.Marker([lat, lon], icon=folium.Icon(color='blue')).add_to(m)


    # Add custom basemaps to folium
    basemaps = {
        'Google Maps': folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Maps',
            overlay=False,
            control=True
        ),
        'Google Satellite': folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Satellite',
            overlay=False,
            control=True
        ),
    }

    # Add custom basemaps
    basemaps['Google Maps'].add_to(m)
    basemaps['Google Satellite'].add_to(m)

    # ----------------- JRC Surface Water -----------------
    dataset = ee.Image('JRC/GSW1_1/GlobalSurfaceWater')
    occurrence = dataset.select('occurrence')
    occurrenceVis = {
        'min': 0.0,
        'max': 100.0,
        'palette': ['ffffff', 'ffbbbb', '0000ff']
        # List of CSS-style color strings (single-band images only)	comma-separated list of hex strings
    }
    m.add_ee_layer(occurrence, occurrenceVis, 'JRC Surface Water')

    # ----------------- NDVI (annual) -----------------
    ndvi_dataset = ee.ImageCollection("LANDSAT/LC08/C01/T1_ANNUAL_NDVI").filterDate('2020-01-01', '2020-12-31')
    ndvi_colorized = ndvi_dataset.select('NDVI')
    ndvi_colorizedVis = {
        'min': 0.0,
        'max': 1.0,
        'palette': ['FFFFFF', 'CE7E45', 'DF923D', 'F1B555', 'FCD163', '99B718', '74A901', '66A000', '529400', '3E8601',
                    '207401', '056201', '004C00', '023B01', '012E01', '011D01', '011301'],
    }
    m.add_ee_layer(ndvi_colorized, ndvi_colorizedVis, 'NDVI')

    # ----------------- NDWI (annual) -----------------
    ndwi_dataset = ee.ImageCollection('LANDSAT/LC08/C01/T1_ANNUAL_NDWI').filterDate('2020-01-01', '2020-12-31')
    ndwi_colorized = ndwi_dataset.select('NDWI')
    ndwi_colorizedVis = {
        'min': 0.0,
        'max': 1.0,
        'palette': ['0000ff', '00ffff', 'ffff00', 'ff0000', 'ffffff'],
    }
    m.add_ee_layer(ndwi_colorized, ndwi_colorizedVis, 'NDWI')

    # ----------------- Boundaries -----------------

    dataset = ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017")
    countries = dataset
    m.add_ee_layer(countries, {}, 'Boundaries')

    # Add a layer control panel to the map.
    m.add_child(folium.LayerControl())
    plugins.Fullscreen().add_to(m)

    # transform the map into html code
    m = m._repr_html_()

    context = {
        'form_location': form_location,
        'form_lat_lon': form_lat_lon,
        'map': m,
    }

    return render(request, 'home.html', context)


def about(request):
    return render(request, 'about.html', {'title': 'About'})


# --------------------------------------- AWS Test ---------------------------------------
import pandas as pd


def aws_test(request):
    location_form = FindLocationForm(request.POST or None)
    date_form = DatePickerForm(request.POST or None)

    geolocator = Nominatim(user_agent='satellite_data_processing')


# -------------- initialize data when form is not valid --------------
    location_lat = 0
    location_lon = 0
    starting_date = 0
    ending_date = 0
    path = 0
    row = 0
    selected_scene = ""
    ndvi_img = 0
    ndwi_img = 0
    s = 0


# -------------- processing when form is valid (user entered location and/or date range) --------------
    if date_form.is_valid():
        starting_date = date_form.cleaned_data.get('starting_date')
        ending_date = date_form.cleaned_data.get('ending_date')

    if location_form.is_valid():
        location_ = location_form.cleaned_data.get('location')
        location = geolocator.geocode(location_)

        if location is not None:
            # location coordinates
            location_lat = location.latitude
            location_lon = location.longitude

            path, row = get_row_path(location_lat, location_lon)

            # get scenes for row and path
            all_scenes = pd.read_csv('scene_list.gz', compression='gzip')
            scenes = all_scenes[(all_scenes.path == path) & (all_scenes.row == row) &
                                (~all_scenes.productId.str.contains('_T2')) &
                                (~all_scenes.productId.str.contains('_RT'))]

            # get only the scenes within the dat range if a dat range is entered
            if (starting_date is not None) and (ending_date is not None):
                starting_date = str(starting_date)
                ending_date = str(ending_date)

                scenes = scenes.loc[(scenes['acquisitionDate'] > starting_date) & (scenes['acquisitionDate'] <= ending_date)]

            s = scenes.sort_values('acquisitionDate')

            s.to_csv("./scenes_in_date_range.csv")


# -------------- After scene is selected --------------
    if request.method == 'POST':
        scene_productId = request.POST.get('submit_scene')
        if scene_productId is not None:
            scenes_csv = pd.read_csv('scenes_in_date_range.csv')
            selected_scene = scenes_csv.loc[scenes_csv['productId'] == scene_productId].iloc[0]

            # I somehow have to store the location after pressing the "Find" button such that I can afterwards
            # (after the user selected the scene and the page is refreshed) pass this location to the mask_bands function
            location_ = location_form.cleaned_data.get('location')
            print("--------------- location_:", location_)

            # download data of band 4 and band 5
            get_bands_data(selected_scene, ['B4.TIF', 'B5.TIF', 'B6.TIF'])

            # masking the bands that were downloaded previously
            mask_bands('Luxembourg')

            # computing the NDVI
            ndvi_img = compute_NDVI('./L8_raw_data')

            # computing the NDWI
            ndwi_img = compute_NDWI('./L8_raw_data')


# -------------- Variables passed to the template --------------
    context = {
        'location_form': location_form,
        'date_form': date_form,
        'lat': location_lat,
        'lon': location_lon,
        'starting_date': starting_date,
        'ending_date': ending_date,
        'path': path,
        'row': row,
        'scene': selected_scene,
        'ndvi_img': ndvi_img,
        'ndwi_img': ndwi_img,
        'scenes': s
    }

    return render(request, 'aws.html', context)
