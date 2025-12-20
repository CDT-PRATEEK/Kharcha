from decimal import Decimal
import logging

from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Expense
from people.models import PersonLedgerEntry
from people.utils import apply_expense_to_person_ledger  # Ledger rebuild helper

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")


@receiver(post_save, sender=Expense)
def rebuild_expense_person_ledger(sender, instance: Expense, created, **kwargs):
    """
    Idempotently rebuild PersonLedgerEntry records linked to an Expense.

    Behavior:
    - Remove all existing PersonLedgerEntry rows associated with this expense
      (covers edit/update scenarios).
    - Delegate ledger creation to the helper, which determines:
        * Which Person entries should be created (borrowed_from / paid_for logic)
        * Whether entries should be created based on the person's tracking preference
    - This signal must NOT force-apply ASK persons. Explicit user actions
      (via banners/views) are responsible for that behavior.
    """

    # Defensive check: an Expense should always have an associated user
    user = getattr(instance, "user", None)
    if not user:
        logger.warning(
            "Expense saved without an associated user. Expense id=%s",
            getattr(instance, "pk", "<unknown>"),
        )
        return

    # Defensive conversion to Decimal to avoid unexpected type issues
    try:
        amount = Decimal(instance.amount or ZERO)
    except Exception:
        amount = ZERO

    try:
        with transaction.atomic():
            # Remove existing ledger rows for this expense (edit/update case)
            PersonLedgerEntry.objects.filter(expense=instance).delete()

            # Delegate ledger entry creation to the helper.
            # force_apply is intentionally False to respect tracking preferences.
            apply_expense_to_person_ledger(user, instance, force_apply=False)

    except Exception as exc:
        # Log and re-raise to ensure failures are visible during development
        logger.exception(
            "Failed to rebuild PersonLedgerEntry records for Expense id=%s",
            instance.pk,
        )
        raise


@receiver(post_delete, sender=Expense)
def cleanup_expense_person_ledger(sender, instance: Expense, **kwargs):
    """
    Remove all PersonLedgerEntry records associated with an Expense
    when the Expense is deleted.
    """
    try:
        PersonLedgerEntry.objects.filter(expense=instance).delete()
    except Exception:
        logger.exception(
            "Failed to clean up PersonLedgerEntry records for deleted Expense id=%s",
            getattr(instance, "pk", "<unknown>"),
        )
        raise
