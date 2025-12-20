from django import forms
from .models import Expense, Category
from django.db.models import Q
from django.db import models
from .models import Expense, Category


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "date",
            "category",
            "amount",
            "description",
            "payment_type",
            "borrowed_from",
            "paid_for",
        ]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "category": forms.Select(
                attrs={"class": "form-select"}
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter amount spent",
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional note (e.g. Zomato, Milk)",
                }
            ),
            "payment_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "borrowed_from": forms.TextInput(
                attrs={"class": "form-control", "id": "borrowedFromInput"}
            ),
            "paid_for": forms.TextInput(
                attrs={"class": "form-control", "id": "paidForInput"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user is not None:
            self.fields["category"].queryset = (
                Category.objects.filter(
                    models.Q(user__isnull=True) | models.Q(user=self.user)
                ).order_by("name")
            )

        if not self.instance.pk:
            self.fields["payment_type"].initial = "cash"

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned_data = super().clean()

        source_kind = self.data.get("source_kind", "own")
        beneficiary_kind = self.data.get("beneficiary_kind", "me")

        borrowed_from = (cleaned_data.get("borrowed_from") or "").strip()
        paid_for = (cleaned_data.get("paid_for") or "").strip()

        if source_kind == "borrowed" and not borrowed_from:
            self.add_error("borrowed_from", "Please enter who you borrowed from.")

        if beneficiary_kind == "other" and not paid_for:
            self.add_error("paid_for", "Please enter who you paid for.")

        cleaned_data["borrowed_from"] = borrowed_from
        cleaned_data["paid_for"] = paid_for

        return cleaned_data