from django import forms
from .models import Profile
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()


        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists. "
                "Please sign in using Google or reset your password."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower()
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "full_name",
            "default_currency",
        ]
        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your full name",
                }
            ),
            "default_currency": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }


class SmartPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        users = super().get_users(email)
        valid_users = []

        for user in users:
            if user.has_usable_password():
                valid_users.append(user)
            else:
                # social-only user
                self.social_user_detected = True

        return valid_users