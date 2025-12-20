from django import forms
from .models import Income


class IncomeForm(forms.ModelForm):
    class Meta:
        model = Income
        fields = ["date", "amount", "source", "payment_type", "person", "description"]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "Amount received",
                }
            ),
            "source": forms.Select(
                attrs={"class": "form-select"}
            ),
            "payment_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "person": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Who was this with ?",
                }
            ),
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional note (Nov salary, refund, gift, etc.)",
                }
            ),
        }
