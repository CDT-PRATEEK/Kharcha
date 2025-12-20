# income/signals.py
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Income
from people.models import PersonLedgerEntry, Person
from people.utils import get_or_create_person_by_name, apply_income_to_person_ledger

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")


@receiver(post_save, sender=Income)
def rebuild_income_person_ledger(sender, instance: Income, created, **kwargs):
    """
    Idempotent: delete old PersonLedgerEntry rows for this Income, then decide whether to apply.
    - If instance.applied_to_people is True -> force apply (user explicitly applied)
    - Else -> apply only when person.tracking_preference == Person.TRACK
    """
    user = getattr(instance, "user", None)
    if not user:
        logger.warning("Income saved without user: id=%s", getattr(instance, "pk", "<unknown>"))
        return

    person_raw = (getattr(instance, "person", "") or "").strip()
    if not person_raw:
        # nothing to do
        return

    try:
        with transaction.atomic():
            # delete any previous ledger entries for this income
            PersonLedgerEntry.objects.filter(income=instance).delete()

            person = get_or_create_person_by_name(user, person_raw)
            if not person:
                return

            force_apply = bool(getattr(instance, "applied_to_people", False))
            should_auto_apply = (getattr(person, "tracking_preference", Person.ASK) == Person.TRACK)

            if not force_apply and not should_auto_apply:
                logger.debug("Income #%s not applied: person %s pref=%s, applied_to_people=%s",
                             instance.pk, person.name, getattr(person, "tracking_preference", None), getattr(instance, "applied_to_people", False))
                return

            # delegate ledger creation logic to helper
            applied = apply_income_to_person_ledger(user, person, instance)
            if applied:
                logger.info("Income #%s applied to person %s ledger (force=%s).", instance.pk, person.name, force_apply)
    except Exception as exc:
        logger.exception("Failed to rebuild person ledger for Income id=%s: %s", instance.pk, exc)
        raise


@receiver(post_delete, sender=Income)
def cleanup_income_person_ledger(sender, instance: Income, **kwargs):
    try:
        PersonLedgerEntry.objects.filter(income=instance).delete()
    except Exception:
        logger.exception("Failed to cleanup PersonLedgerEntry for deleted Income id=%s", getattr(instance, "pk", "<unknown>"))
        raise

