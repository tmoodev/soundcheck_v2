"""Authentication and user management forms."""
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password

from .models import User

tw = "w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": tw, "placeholder": "Email address", "autofocus": True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": tw, "placeholder": "Password"})
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get("email", "").lower()
        password = self.cleaned_data.get("password")
        if email and password:
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Invalid email or password.")
            if not self.user_cache.is_active:
                raise forms.ValidationError("This account has been disabled.")
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class MFAVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            "class": tw,
            "placeholder": "6-digit code or recovery code",
            "autocomplete": "one-time-code",
            "inputmode": "numeric",
            "autofocus": True,
        })
    )
    remember_device = forms.BooleanField(required=False, label="Remember this device for 7 days")


class MFASetupForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={
            "class": tw,
            "placeholder": "Enter the 6-digit code from your authenticator",
            "autocomplete": "one-time-code",
            "inputmode": "numeric",
            "autofocus": True,
        })
    )


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": tw, "placeholder": "Email address"})
    )


class PasswordResetConfirmForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": tw, "placeholder": "New password"}),
        validators=[validate_password],
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": tw, "placeholder": "Confirm new password"})
    )

    def clean(self):
        cd = super().clean()
        if cd.get("password") != cd.get("password_confirm"):
            raise forms.ValidationError("Passwords do not match.")
        return cd


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": tw, "placeholder": "Initial password"}),
        validators=[validate_password],
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "role"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": tw}),
            "first_name": forms.TextInput(attrs={"class": tw}),
            "last_name": forms.TextInput(attrs={"class": tw}),
            "role": forms.Select(attrs={"class": tw}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "role", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": tw}),
            "last_name": forms.TextInput(attrs={"class": tw}),
            "role": forms.Select(attrs={"class": tw}),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded text-blue-500"}),
        }
