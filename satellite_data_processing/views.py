from django.shortcuts import render, redirect
from .forms import *
from geopy.geocoders import Nominatim
from .utils import *
import ee
from folium import plugins
from os import path


# ------------------------------------------- AWS -------------------------------------------
import pandas as pd
from .models import *


def aws(request):
    location_form = FindLocationForm(request.POST or None)
    date_form = DatePickerForm(request.POST or None)
    indicator_choices_form = IndicatorChoiceForm(request.POST or None)

    geolocator = Nominatim(user_agent='satellite_data_processing')


# -------------- initialize data when form is not valid --------------
    location_lat = 0
    location_lon = 0
    starting_date = 0
    ending_date = 0
    selected_scene = 0
    list_of_path_and_rows = []
    s = 0


# -------------- processing when forms are valid (user entered location and/or date range) --------------
    if indicator_choices_form.is_valid():
        indicator = indicator_choices_form.cleaned_data.get('choices')
        indicator_choices_form.save()

    if date_form.is_valid():
        starting_date = date_form.cleaned_data.get('starting_date')
        ending_date = date_form.cleaned_data.get('ending_date')

    if location_form.is_valid():
        location_ = location_form.cleaned_data.get('location')
        location = geolocator.geocode(location_)

        location_form.save()

        if location is not None:
            # location coordinates
            location_lat = location.latitude
            location_lon = location.longitude

            # get all paths an rows of the location
            list_of_path_and_rows = get_path_row(location_lat, location_lon)
            print("---- list_of_path_and_rows:", list_of_path_and_rows)

            list_of_scenes = []
            # get all the scenes for the rows and paths
            for item in list_of_path_and_rows:
                path = item[0]
                row = item[1]
                all_scenes = pd.read_csv('scene_list.gz', compression='gzip')
                scenes = all_scenes[(all_scenes.path == path) & (all_scenes.row == row) &
                                    (~all_scenes.productId.str.contains('_T2')) &
                                    (~all_scenes.productId.str.contains('_RT'))]
                list_of_scenes.append(scenes)
            scenes = pd.concat(list_of_scenes)

            # get only the scenes within the dat range if a date range is entered
            if (starting_date is not None) and (ending_date is not None):
                starting_date = str(starting_date)
                ending_date = str(ending_date)

                scenes = scenes.loc[(scenes['acquisitionDate'] > starting_date) & (scenes['acquisitionDate'] <= ending_date)]

            # adding a column to the scenes dataframe which helps to get all the corresponding scenes after the user selects one scene
            scenes_after_new_index = []
            for i, item in enumerate(list_of_path_and_rows):
                path = item[0]
                row = item[1]
                sc = scenes.loc[(scenes['path'] == path) & (scenes['row'] == row)]
                sc['index_for_path_and_row'] = i
                scenes_after_new_index.append(sc)

            scenes = pd.concat(scenes_after_new_index)

            s = scenes.sort_values('acquisitionDate')
            s.reset_index(drop=True, inplace=True)

            # set the name of the index column to 'Index'
            s.index.names = ['Index']

            s.to_csv("./scenes_in_date_range.csv")


# -------------- After scene is selected --------------
    if request.method == 'POST':
        scene_productId = request.POST.get('submit_scene')
        if scene_productId is not None:
            scenes_csv = pd.read_csv('scenes_in_date_range.csv')
            selected_scene = scenes_csv.loc[scenes_csv['productId'] == scene_productId]

            list_of_idx = scenes_csv["Index"].to_list()

            index_of_selected_scene = int(selected_scene['Index'])

            # dict of distances between selected scene and other scenes in date range
            dict_of_distances = dict()
            for idx in list_of_idx:
                distance = abs(idx - index_of_selected_scene)
                dict_of_distances[idx] = distance

            # sort dict of distances according to the values (distance)
            dict_of_distances = dict(sorted(dict_of_distances.items(), key=lambda item: item[1]))
            del dict_of_distances[index_of_selected_scene]

            # get the scenes which are closest to the selected scene, but have a different path-row combination
            list_of_final_scenes = []
            idx_path_row_of_selected_scene = int(selected_scene['index_for_path_and_row'])
            for idx, distance in dict_of_distances.items():
                scene = scenes_csv.loc[scenes_csv['Index'] == idx]
                idx_path_row_of_scene = int(scene['index_for_path_and_row'])
                if idx_path_row_of_scene != idx_path_row_of_selected_scene:
                    list_of_final_scenes.append(scene)

            # concat all the corresponding scenes and only keep the first ones as they have the smallest distance
            final_scenes = pd.concat(list_of_final_scenes)
            final_scenes = final_scenes.drop_duplicates(subset='index_for_path_and_row', keep="first")

            # concat the corresponding scenes with the initial scene selected by the user
            final_scenes = pd.concat([final_scenes, selected_scene])

            final_scenes.to_csv("./selected_scenes_in_date_range.csv")

            return redirect('aws_img')


# -------------- Variables passed to the template --------------
    context = {
        'location_form': location_form,
        'date_form': date_form,
        'indicator_choices_form': indicator_choices_form,
        'lat': location_lat,
        'lon': location_lon,
        'starting_date': starting_date,
        'ending_date': ending_date,
        'list_of_path_and_rows': list_of_path_and_rows,
        'scene': selected_scene,
        'scenes': s
    }

    return render(request, 'aws.html', context)


# ------------------------------------------- AWS IMG -------------------------------------------
def aws_img(request):
    selected_scenes = pd.read_csv('selected_scenes_in_date_range.csv')

    # Fetch the latest location from the database
    location = Location.objects.exclude(location__exact='').last().location
    print("------------ location:", str(location))

    # Fetch the latest indicator from the database
    indicator = Indicator.objects.exclude(indicator__exact='').last().indicator
    print("------------ indicator:", str(indicator))

    # download data of band 4, band 5, band 6 and band 7
    get_bands_data(selected_scenes, ['B4.TIF', 'B5.TIF', 'B6.TIF', 'B7.TIF'])

    # masking the bands that were downloaded previously
    mask_bands(str(location))

    # computing the corresponding indicator
    compute_indicator('./L8_raw_data/', str(indicator))

    # creating the final image
    plotting_image(str(location))

    # delete all entries in the database tables as they are not needed anymore
    Location.objects.all().delete()
    Indicator.objects.all().delete()

    # deleting the bands downloaded before and tiff files computed previously as they are not needed anymore
    for element in glob.glob('./L8_raw_data/*'):
        if path.isfile(element):
            os.remove(element)
        elif path.isdir(element):
            shutil.rmtree(element)

    context = {
        'scenes': selected_scenes,
    }

    return render(request, 'aws_img.html', context)


# ------------------------------------------- ABOUT -------------------------------------------
def about(request):
    return render(request, 'about.html', {'title': 'About'})


# ------------------------------------------- GEE -------------------------------------------
def google_earth_engine(request):
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

    return render(request, 'google_earth_engine.html', context)
