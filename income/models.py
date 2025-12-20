from django.conf import settings
from django.db import models


class Income(models.Model):
    SOURCE_CHOICES = [
        ("salary_wages", "Salary / Wages"),
        ("business", "Business Income"),
        ("investment", "Investment Income"),
        ("refund", "Refund / Reimbursement"),
        ("gift_support", "Gift / Allowance"),
        ("loan", "Loan"),                   
        ("loan_repayment", "Loan Repayment"),
        ("other", "Other"),
    ]

    PAYMENT_TYPE_CHOICES = [
        ("cash", "Cash"),
        ("upi", "UPI"),
        ("card", "Card"),
        ("netbanking", "Net Banking"),
        ("wallet", "Wallet"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="incomes",
    )

    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default="other",
    )

    # Payment type similar to Expense
    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default="cash",
    )

    # Person (optional)
    person = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who gave you this money? (optional)",
    )

    # Description (optional)
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Note like 'Nov salary', 'Refund for shoes', etc.",
    )

    applied_to_people = models.BooleanField(
        default=False,
        help_text="If true this income has been applied to the Person ledger (via banner or wizard).",
    )



    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def save(self, *args, **kwargs):
        if self.person:
            self.person = self.person.strip().title()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} +₹{self.amount} on {self.date}"
