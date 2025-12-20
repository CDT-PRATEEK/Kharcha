# people/models.py
from decimal import Decimal

from django.conf import settings
from django.db import models


class Person(models.Model):
    """
    A person with whom the user has money interactions (borrowing, lending, paying for, etc).
    This is per-user: two different Kharcha users can both have a 'Ravi'.
    """

    # User FK
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="people",
    )

    
    name = models.CharField(max_length=100)

    # Tracking constants (use these everywhere in code)
    TRACK = "TRACK"
    NO_TRACK = "NO_TRACK"
    ASK = "ASK"

    TRACKING_CHOICES = [
        (TRACK, "Track balances"),
        (NO_TRACK, "Do not track"),
        (ASK, "Ask every time"),
    ]

    tracking_preference = models.CharField(
        max_length=16,
        choices=TRACKING_CHOICES,
        default=ASK,
        help_text="Should Kharcha track balances with this person?",
    )

    # Legacy boolean for older code paths (kept for backward compatibility)
    auto_suggest_enabled = models.BooleanField(
        default=True,
        help_text="If disabled, Kharcha will not show balance suggestions for this person.",
    )
    archived = models.BooleanField(default=False, help_text="If true, hide this person from main People list (untracked/archived).")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.name:
            
            self.name = self.name.strip().title()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    @property
    def balance(self) -> Decimal:
        """
        Net balance with this person.

        Convention:
        - Positive  => person owes YOU that amount (they should pay you).
        - Negative  => YOU owe THEM that amount.
        - Zero      => settled.
        """
        agg = self.ledger_entries.aggregate(total=models.Sum("amount"))
        return agg["total"] or Decimal("0.00")

    @property
    def balance_label(self) -> str:
        amt = self.balance
        if amt > 0:
            return f"{self.name} owes you ₹{amt}"
        elif amt < 0:
            return f"You owe {self.name} ₹{abs(amt)}"
        else:
            return "Settled"


class PersonLedgerEntry(models.Model):
    """
    A single change in balance with a person.

    amount:
      - Positive => increases what *they* owe you.
      - Negative => increases what *you* owe them.

    It may be linked to an Expense, an Income, or be a purely manual adjustment.
    """

    SOURCE_TYPE_CHOICES = [
        ("expense", "Expense"),
        ("income", "Income"),
        ("manual", "Manual adjustment"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="person_ledger_entries",
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source_type = models.CharField(
        max_length=10,
        choices=SOURCE_TYPE_CHOICES,
        default="manual",
    )

    # Optional links
    expense = models.ForeignKey(
        "expenses.Expense",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="person_ledger_entries",
    )
    income = models.ForeignKey(
        "income.Income",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="person_ledger_entries",
    )
    archived = models.BooleanField(default=False, help_text="If true, this ledger row is archived and not counted in active balances.")

    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.amount >= 0 else "-"
        return f"{self.person.name}: {sign}{abs(self.amount)} ({self.source_type})"
