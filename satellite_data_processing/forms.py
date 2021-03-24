from django import forms


class FindLocationForm(forms.Form):
    location = forms.CharField(max_length=200, required=False)


class LatLonForm(forms.Form):
    latitude = forms.CharField(max_length=200, required=False)
    longitude = forms.CharField(max_length=200, required=False)
