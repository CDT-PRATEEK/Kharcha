from django.db import models
from django.contrib.auth.models import User


def normalize_name(value: str) -> str:
   
    if not value:
        return ""
    parts = value.strip().split()
    return " ".join(p.capitalize() for p in parts)


class Category(models.Model):
    name = models.CharField(max_length=50)
    # null user = global default category (Food, Rent, Miscellaneous, etc.)
    # non-null user = custom category created by that specific user
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        # no duplicate "Food" for same user;
        # still allows global "Food" + per-user "Food"
        unique_together = ("name", "user")

    def save(self, *args, **kwargs):
        if self.name:
           
            self.name = normalize_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        # e.g. "Food" or "Food" 
        return self.name


class Expense(models.Model):
    PAYMENT_TYPE_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("card", "Card"),
        ("netbanking", "Net Banking"),
        ("wallet", "Wallet"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default="cash",
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Source of money
    is_borrowed = models.BooleanField(default=False)
    borrowed_from = models.CharField(max_length=100, blank=True)

    # Beneficiary
    is_for_others = models.BooleanField(default=False)
    paid_for = models.CharField(max_length=100, blank=True)

   


    class Meta:
        # Default ordering: latest expenses first
        ordering = ["-date", "-created_at"]

    def save(self, *args, **kwargs):
        """
        Central place for cleaning / normalizing:
        - normalize lender & paid_for names (RAVI/ravi -> Ravi)
        - keep borrowed_from empty if not borrowed
        - keep paid_for empty if not for others
        """
        # Normalize names
        if self.borrowed_from:
            self.borrowed_from = normalize_name(self.borrowed_from)
        if self.paid_for:
            self.paid_for = normalize_name(self.paid_for)

        # Basic consistency:
        # If not borrowed, there should be no lender stored.
        if not self.is_borrowed:
            self.borrowed_from = ""

        # If not marked as "for others", do not keep a paid_for name.
        if not self.is_for_others:
            self.paid_for = ""

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.amount} on {self.date}"
