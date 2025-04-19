from django import forms
from .models import Product
from django.contrib.auth.models import User
import os.path
from django.contrib.admin.helpers import ActionForm
from django.utils.translation import gettext_lazy as _

class UploadFileForm(forms.Form):
    file = forms.FileField(label="Upload Excel or CSV File")


class ProductForm(forms.ModelForm):
    department_choices = [
        ('IT', 'IT Department'),
        ('HR', 'Human Resources'),
        ('Finance', 'Finance Department'),
        ('Sales', 'Sales Department'),
    ]

    department = forms.ChoiceField(choices=department_choices, required=True, widget=forms.Select(attrs={'class': 'form-control'}))
    user = forms.ModelChoiceField(queryset=User.objects.all(), required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    users = forms.ModelMultipleChoiceField(queryset=User.objects.all(), required=False, widget=forms.SelectMultiple(attrs={'class': 'form-control'}))

    class Meta:
        model = Product
        fields = ['host_name_category', 'model_number', 'serial_number', 'department', 'location', 'user', 'users']

class ProductUploadForm(forms.Form):
    file = forms.FileField
    

    #today 25/03/2025
    # class ImportExcelForm(forms.Form):
    #     file = forms.FileField(label='choose excel file to upload')



class ImportForm(forms.Form):
    import_file = forms.FileField(
        label=_('File to import')
        )
    input_format = forms.ChoiceField(
        label=_('Format'),
        choices=(),
        )

    def __init__(self, import_formats, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        for i, f in enumerate(import_formats):
            choices.append((str(i), f().get_title(),))
        if len(import_formats) > 1:
            choices.insert(0, ('', '---'))

        self.fields['input_format'].choices = choices


class ConfirmImportForm(forms.Form):
    import_file_name = forms.CharField(widget=forms.HiddenInput())
    original_file_name = forms.CharField(widget=forms.HiddenInput())
    input_format = forms.CharField(widget=forms.HiddenInput())

    def clean_import_file_name(self):
        data = self.cleaned_data['import_file_name']
        data = os.path.basename(data)
        return data


class ExportForm(forms.Form):
    file_format = forms.ChoiceField(
        label=_('Format'),
        choices=(),
        )

    def __init__(self, formats, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        for i, f in enumerate(formats):
            choices.append((str(i), f().get_title(),))
        if len(formats) > 1:
            choices.insert(0, ('', '---'))

        self.fields['file_format'].choices = choices


def export_action_form_factory(formats):
    """
    Returns an ActionForm subclass containing a ChoiceField populated with
    the given formats.
    """
    class _ExportActionForm(ActionForm):
        """
        Action form with export format ChoiceField.
        """
        file_format = forms.ChoiceField(
            label=_('Format'), choices=formats, required=False)
    _ExportActionForm.__name__ = str('ExportActionForm')

    return _ExportActionForm