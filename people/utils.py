
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum

from .models import Person, PersonLedgerEntry
from django.utils.html import format_html
from django.urls import reverse
from expenses.models import Expense


ZERO = Decimal("0.00")



# -------------------------------------------------
# Name helpers
# -------------------------------------------------

def _normalize_name(raw_name: Optional[str]) -> Optional[str]:
    if not raw_name:
        return None
    name = raw_name.strip()
    if not name:
        return None
    return name.title()


def get_person_by_name(user, raw_name) -> Optional[Person]:
    """
    Case-insensitive FIND ONLY.
     Does NOT create a Person.
    """
    name = _normalize_name(raw_name)
    if not name:
        return None
    return Person.objects.filter(user=user, name__iexact=name).first()


def get_or_create_person_by_name(user, raw_name) -> Optional[Person]:
    """
    Find or CREATE a Person.
    Use ONLY after explicit user consent.
    """
    name = _normalize_name(raw_name)
    if not name:
        return None

    person = Person.objects.filter(user=user, name__iexact=name).first()
    if person:
        if person.name != name:
            person.name = name
            person.save(update_fields=["name"])
        return person

    return Person.objects.create(
        user=user,
        name=name,
        tracking_preference=Person.ASK,
        auto_suggest_enabled=True,
    )


# -------------------------------------------------
# Balance helpers
# -------------------------------------------------

def person_balance(user, person) -> Decimal:
    agg = PersonLedgerEntry.objects.filter(
        user=user,
        person=person,
        archived=False,
    ).aggregate(total=Sum("amount"))
    return agg["total"] or ZERO


# -------------------------------------------------
# Income → Ledger  
# -------------------------------------------------

@transaction.atomic
def apply_income_to_person_ledger(user, person: Person, income) -> bool:
    """
    Apply income AFTER explicit consent.
    SAFE + idempotent + delete-safe.
    """
    if not person or not income:
        return False

    try:
        amount = Decimal(income.amount)
    except Exception:
        return False

    if amount <= ZERO:
        return False

    #  removing any old ledger rows for this income
    PersonLedgerEntry.objects.filter(
        user=user,
        income=income,
    ).delete()

    current_balance = person_balance(user, person)

    if income.source == "loan":
        ledger_amount = -amount
        note = f"Loan from {person.name}"

    elif income.source == "loan_repayment":
        if current_balance <= ZERO:
            return False
        ledger_amount = -min(amount, current_balance)
        note = f"Repayment by {person.name}"

    else:
        return False

    PersonLedgerEntry.objects.create(
        user=user,
        person=person,
        amount=ledger_amount,
        source_type="income",
        note=note,
        income=income,   #  ALWAYS LINK
    )
    return True

@transaction.atomic
def apply_expense_to_person_ledger(user, expense, *args, **kwargs) -> bool:
    force_apply = kwargs.get("force_apply", False)
    ZERO = Decimal("0.00")

    if not expense:
        return False
    
    
    PersonLedgerEntry.objects.filter(expense=expense).delete()

    try:
        amount = Decimal(expense.amount)
    except Exception:
        return False

    if amount <= ZERO:
        return False

    # 2.  "BORROWED FROM" (Money coming IN)
    if expense.is_borrowed and expense.borrowed_from:
        person = get_person_by_name(user, expense.borrowed_from)
        if person:
            PersonLedgerEntry.objects.create(
                user=user,
                person=person,
                amount=-amount,  # You owe them
                source_type="expense",
                note=f"Borrowed: {expense.description or 'Expense'}",
                expense=expense,
            )

    # 3.  "PAID FOR" (Money going OUT)
    if expense.is_for_others and expense.paid_for:
        person = get_person_by_name(user, expense.paid_for)
        if person:
            
            is_repayment_category = False
            
            if expense.category:
                
                cat_name = expense.category.name.lower().strip()
                
                # Check for keywords instead of exact match
                if "repayment" in cat_name or "settlement" in cat_name:
                    is_repayment_category = True

            if is_repayment_category:
                # If Manual Entry (force_apply=False), check if we actually owe them.
                if not force_apply:
                    agg = person.ledger_entries.filter(archived=False).aggregate(total=Sum("amount"))
                    current_balance = agg["total"] or ZERO
                    
                    # BLOCK if we don't owe them (Balance is 0 or Positive)
                    if current_balance >= ZERO:
                        return False 

            # Create the entry (only if not blocked above)
            PersonLedgerEntry.objects.create(
                user=user,
                person=person,
                amount=amount,  # They owe you (or reduces your debt)
                source_type="expense",
                note=f"Paid for: {expense.description or 'Expense'}",
                expense=expense,
            )

    return True