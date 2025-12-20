
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Person
from .utils import apply_income_to_person_ledger, get_person_by_name
from income.models import Income
from people.models import PersonLedgerEntry
from people.utils import apply_expense_to_person_ledger
from expenses.models import Expense


logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")


@receiver(post_save, sender=Income)
def handle_income_post_save(sender, instance: Income, created, **kwargs):
    """
    Auto-apply income to Person ledger ONLY when:
      - Person already exists
      - tracking_preference == TRACK

    This signal MUST NOT create Person records.
    """
    user = getattr(instance, "user", None)
    if not user:
        logger.warning("Income saved without user: id=%s", getattr(instance, "pk", "<unknown>"))
        return

    person_name = getattr(instance, "person", None)
    if not person_name:
        return  # income not linked to a person

    
    person = get_person_by_name(user, person_name)
    if not person:
        logger.debug(
            "Income #%s references person '%s' but person does not exist yet (ASK flow).",
            instance.pk,
            person_name,
        )
        return

    # Only auto-apply if user explicitly tracks this person
    if person.tracking_preference != Person.TRACK:
        logger.debug(
            "Income #%s not auto-applied: person %s preference=%s",
            instance.pk,
            person.name,
            person.tracking_preference,
        )
        return

    try:
        with transaction.atomic():
            applied = apply_income_to_person_ledger(user, person, instance)
            if applied:
                logger.info(
                    "Auto-applied income #%s to ledger for person %s",
                    instance.pk,
                    person.name,
                )
    except Exception as exc:
        logger.exception(
            "Failed to auto-apply income #%s to person ledger: %s",
            instance.pk,
            exc,
        )
        raise

