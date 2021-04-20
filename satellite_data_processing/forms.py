from django import forms


class FindLocationForm(forms.Form):
    location = forms.CharField(max_length=200, required=False)


class DateInput(forms.DateInput):
    input_type = 'date'


class DatePickerForm(forms.Form):
    starting_date = forms.DateField(widget=DateInput, required=False)
    ending_date = forms.DateField(widget=DateInput, required=False)


class LatLonForm(forms.Form):
    latitude = forms.CharField(max_length=200, required=False)
    longitude = forms.CharField(max_length=200, required=False)
