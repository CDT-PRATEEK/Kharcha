from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    CURRENCY_CHOICES = [
        ("INR", "₹ INR (Indian Rupee)"),
        ("USD", "$ USD (US Dollar)"),
        ("EUR", "€ EUR (Euro)"),
        ("GBP", "£ GBP (British Pound)"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100, blank=True)

    default_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="INR",
    )

    def __str__(self):
        return self.full_name or self.user.username
    


