from django import forms
from .models import *


class FindLocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ('location',)
    #location = forms.CharField(max_length=200, required=False)


class DateInput(forms.DateInput):
    input_type = 'date'


class DatePickerForm(forms.Form):
    starting_date = forms.DateField(widget=DateInput, required=False)
    ending_date = forms.DateField(widget=DateInput, required=False)


class LatLonForm(forms.Form):
    latitude = forms.CharField(max_length=200, required=False)
    longitude = forms.CharField(max_length=200, required=False)


class IndicatorChoiceForm(forms.ModelForm):
    class Meta:
        model = Indicator
        fields = ('indicator',)

        CHOICES = [
            ('NDVI', 'Normalized Difference Vegetation Index'),
            ('NDWI', 'Normalized Difference Water Index'),
            ('NDSI', 'Normalized Difference Soil Index'),
            ('NDRE', 'Normalized Difference Red Edge'),
            ('SLAVI', 'Specific Leaf Area Vegetation Index')
        ]

        widgets = {
            'indicator': forms.Select(choices=CHOICES, attrs={'class': 'form-control'}),
        }
