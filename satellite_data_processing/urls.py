from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('earth_engine/', views.earth_engine_view, name='earth_engine'),
    path('aws/', views.aws_test, name='aws'),
]
