from django.shortcuts import render, get_object_or_404
from .models import *
from .forms import *
from geopy.geocoders import Nominatim
import folium
from .utils import *


def home(request):
    form = FindLocationForm(request.POST or None)
    geolocator = Nominatim(user_agent='satellite_data_processing')

    # initial location which is displayed on the map
    ip = get_ip_address(request)                # this code cannot be used when working with the localhost
    ip = '184.61.2.37'                          # so the ip address is overwritten with a static ip address for development
    country, city, initial_location_lat, initial_location_lon = get_geoip(ip)

    initial_location = geolocator.geocode(city)
    initial_location_point = (initial_location_lat, initial_location_lon)

    # initial folium map
    m = folium.Map(width=900, height=600, location=initial_location_point)

    # location marker
    folium.Marker([initial_location_lat, initial_location_lon], tooltip='click here for more info',
                  popup=initial_location, icon=folium.Icon(color='blue')).add_to(m)

    if form.is_valid():
        instance = form.save(commit=False)
        location_ = form.cleaned_data.get('location')
        location = geolocator.geocode(location_)

        # location coordinates
        location_lat = location.latitude
        location_lon = location.longitude
        location_point = (location_lat, location_lon)

        # folium map modification
        m = folium.Map(width=900, height=600, location=location_point)

        # new location marker
        folium.Marker([location_lat, location_lon], tooltip='click here for more info',
                      popup=location, icon=folium.Icon(color='blue')).add_to(m)

        instance.save()

    # transform the map into html code
    m = m._repr_html_()

    context = {
        'form': form,
        'map': m,
    }

    return render(request, 'home.html', context)


def about(request):
    return render(request, 'about.html', {'title': 'About'})

