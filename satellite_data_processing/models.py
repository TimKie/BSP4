from django.db import models


class Location(models.Model):
    location = models.CharField(max_length=100, blank=True, primary_key=True)


class Indicator(models.Model):
    indicator = models.CharField(max_length=100, blank=True, primary_key=True)

