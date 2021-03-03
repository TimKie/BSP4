from django import forms
from .models import Location


class FindLocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ('location',)
