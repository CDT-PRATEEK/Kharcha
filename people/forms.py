from decimal import Decimal

from django import forms

from .models import Person

class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["name", "auto_suggest_enabled"]
        labels = {
            "name": "Person's name",
            "auto_suggest_enabled": "Show smart suggestions for this person",
        }

    def __init__(self, *args, **kwargs):
        # so we know which user's people to check against
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        normalized = name.title()  # same as Person.save

        if self.user:
            
            if Person.objects.filter(user=self.user, name__iexact=normalized).exists():
                raise forms.ValidationError(
                    "You already have someone with this name."
                )

        return normalized


class ManualAdjustmentForm(forms.Form):
    DIRECTION_CHOICES = [
        ("they_paid_you", "They paid you"),
        ("you_paid_them", "You paid them"),
    ]

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount",
        help_text="How much was adjusted between you and this person?",
    )

    direction = forms.ChoiceField(
        choices=DIRECTION_CHOICES,
        widget=forms.RadioSelect,
        label="Who paid whom?",
    )

    note = forms.CharField(
        max_length=255,
        required=False,
        label="Note (optional)",
    )
