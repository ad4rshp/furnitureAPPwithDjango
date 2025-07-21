from django import forms
from .models import Address
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['first_name', 'last_name', 'street_address', 'city', 'state', 'zip_code', 'country', 'is_default']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last Name'}),
            'street_address': forms.TextInput(attrs={'placeholder': 'e.g., 123 Main St'}),
            'city': forms.TextInput(attrs={'placeholder': 'e.g., Mumbai'}),
            'state': forms.TextInput(attrs={'placeholder': 'e.g., Maharashtra'}),
            'zip_code': forms.TextInput(attrs={'placeholder': 'e.g., 400001'}),
            'country': forms.TextInput(attrs={'placeholder': 'e.g., India'}),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'street_address': 'Street Address',
            'city': 'City',
            'state': 'State/Province',
            'zip_code': 'Zip/Postal Code',
            'country': 'Country',
            'is_default': 'Set as default address',
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Your First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Your Last Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'your.email@example.com'}),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email Address',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email address is already in use by another account.")
        return email

class CustomUserCreationForm(BaseUserCreationForm):
    first_name = forms.CharField(max_length=150, required=False, help_text='Optional.')
    last_name = forms.CharField(max_length=150, required=False, help_text='Optional.')

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = BaseUserCreationForm.Meta.fields + ('first_name', 'last_name', 'email',)
        labels = {
            'email': 'Email Address',
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name')
        user.last_name = self.cleaned_data.get('last_name')
        if commit:
            user.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_order = ['username', 'email', 'first_name', 'last_name', 'password', 'password2']
        self.order_fields(field_order)
        self.fields['first_name'].widget.attrs['placeholder'] = 'First Name'
        self.fields['last_name'].widget.attrs['placeholder'] = 'Last Name'
        self.fields['email'].widget.attrs['placeholder'] = 'Email Address (Optional)'
