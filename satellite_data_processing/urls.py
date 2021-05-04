from django.urls import path
from . import views

urlpatterns = [
    path('', views.aws, name='aws'),
    path('about/', views.about, name='about'),
    path('google_earth_engine/', views.google_earth_engine, name='google_earth_engine'),
    path('aws_img/', views.aws_img, name='aws_img'),
]
