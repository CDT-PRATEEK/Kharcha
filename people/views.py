# people/views.py
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.contrib import messages
from django.utils.html import format_html
from django.db import transaction
from django.views.decorators.http import require_POST
from django.db.models.functions import Coalesce
from django.db import models
from django.db.models import Value
from django.core.paginator import Paginator

from .models import Person, PersonLedgerEntry
from accounts.utils import get_currency_symbol
from .forms import ManualAdjustmentForm, PersonForm
from .utils import apply_income_to_person_ledger, apply_expense_to_person_ledger
from income.models import Income
from expenses.models import Expense
from django.db.models import Max


@login_required
def people_list(request):
    """
    Default:
      - Show ONLY actively tracked people (TRACK)
      - Exclude archived / NO_TRACK
      - Exclude people with no active ledger entries

    ?show_untracked=1:
      - Show ALL people (including archived / NO_TRACK)

    Ordering:
      - Most recently updated person (ledger activity) first
    """

    show_untracked = request.GET.get("show_untracked") == "1"

    search = (request.GET.get("q") or "").strip()


    qs = Person.objects.filter(user=request.user)

    if search:
        qs = qs.filter(name__icontains=search)


    if not show_untracked:
        qs = (
            qs.filter(
                tracking_preference=Person.TRACK,
                archived=False,
                ledger_entries__archived=False,   # must have active ledger
            )
            .distinct()
        )

    people = (
        qs.annotate(
            net_balance=Coalesce(
                Sum(
                    "ledger_entries__amount",
                    filter=models.Q(ledger_entries__archived=False),
                ),
                Value(Decimal("0.00")),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            ),
            last_activity=Max(
                "ledger_entries__created_at",
                filter=models.Q(ledger_entries__archived=False),
            ),
        )
        .order_by("-last_activity", "name")  #  MOST RECENT FIRST
    )


    context = {
        "people": people,
        "show_untracked": show_untracked,
        "search": search,
    }
    return render(request, "people/people_list.html", context)

@login_required
def person_detail(request, pk):
    user = request.user
    person = get_object_or_404(Person, pk=pk, user=user)

    # All ledger entries + current balance
    

    # ---- Ledger queryset (ACTIVE entries only) ----
    ledger_qs = person.ledger_entries.filter(archived=False).order_by("-created_at")

    # Balance must be computed on FULL queryset (NOT paginated)
    agg = ledger_qs.aggregate(total=Sum("amount"))
    balance = agg["total"] or Decimal("0.00")

    # ---- Pagination ----
    paginator = Paginator(ledger_qs, 10)  # 👈 10 entries per page
    page_number = request.GET.get("page")
    ledger_page = paginator.get_page(page_number)



    if request.method == "POST":
        action = request.POST.get("action")

        # -------- ADJUST WIZARD --------
        if action == "manual_adjust":
            request.session["force_ledger_track"] = True
            amount_str = request.POST.get("amount") or "0"
            direction = request.POST.get("direction")  # they_paid / you_paid / i_borrowed
            note = (request.POST.get("note") or "").strip()

            try:
                amount = Decimal(amount_str)
            except Exception:
                amount = Decimal("0.00")

            if amount <= 0:
                messages.warning(request, "Please enter a positive amount.")
                return redirect("person-detail", pk=person.pk)

            # Where to come back after income/expense
            next_url = request.build_absolute_uri(request.path)
            currency = get_currency_symbol(request.user.profile)

            if direction == "they_paid":
                
                if balance < Decimal("0.00"):
                    # Inform and redirect back to person detail (user should change selection)
                    messages.warning(
                        request,
                        format_html(
                            "You currently owe <strong>{p}</strong> {currency}{amt}. "
                            "If they gave you money for borrowing, choose "
                            "<strong>'You borrowed from them'</strong> instead. "
                            "Use <strong>'They repaid you'</strong> only when they owe you.",
                            p=person.name,
                            currency=currency,
                            amt=abs(balance),
                        )
                    )
                    return redirect("person-detail", pk=person.pk)

                params = {
                    "source": "loan_repayment",
                    "person": person.name,
                    "amount": str(amount),
                    "note": note,
                    "next": request.build_absolute_uri(request.path),
                    "from_people": "1",
                }
                add_income_url = reverse("income-add") + "?" + urlencode(params)

                messages.info(
                    request,
                    format_html(
                        "We’ll record this as an income.<br>"
                        "Check details and save it there."
                    ),
                )

                return redirect(add_income_url)


            elif direction == "you_paid":
                # =========================================================
                # SCENARIO 1: They Owe You (Balance > 0)
                # Logic: You cannot "Repay" a debt that doesn't exist.
                # Action: Pivot to Add Expense, but CLEAR flags and category.
                # =========================================================
                if balance > Decimal("0.00"):
                    
                    if "force_ledger_track" in request.session:
                        del request.session["force_ledger_track"]

                    params = {
                        "amount": str(amount),
                        "paid_for": person.name,
                        "note": note,
                        "next": request.build_absolute_uri(request.path),
                        
                    }
                    add_expense_url = reverse("add-expense") + "?" + urlencode(params)
                    currency = get_currency_symbol(request.user.profile)

                    messages.info(
                        request,
                        format_html(
                            "Since {p} owes you money, this isn't a repayment.<br>"
                            "We redirected you to add a <strong>new expense</strong> for them instead.",
                            p=person.name
                        ),
                    )
                    return redirect(add_expense_url)

                # =========================================================
                # SCENARIO 2: Settled (Balance == 0)
                # Logic: Same as above. Can't repay 0.
                # Action: Pivot to Add Expense, clear flags and category.
                # =========================================================
                if balance == Decimal("0.00"):
                    
                    if "force_ledger_track" in request.session:
                        del request.session["force_ledger_track"]

                    params = {
                        "amount": str(amount),
                        "paid_for": person.name,
                        "note": note,
                        "next": request.build_absolute_uri(request.path),
                        
                    }
                    add_expense_url = reverse("add-expense") + "?" + urlencode(params)

                    messages.info(
                        request,
                        format_html(
                            "Balances are settled.<br>"
                            "Redirecting to record this as a <strong>new expense</strong>."
                        ),
                    )
                    return redirect(add_expense_url)

                # =========================================================
                # SCENARIO 3: You Owe Them (Balance < 0) - THE REAL REPAYMENT
                # Logic: This is the ONLY valid "Repayment".
                # =========================================================
                
                #  Overpayment Check
                if amount > abs(balance):
                    currency = get_currency_symbol(request.user.profile)
                    messages.warning(
                        request,
                        format_html(
                            "You cannot repay <strong>{currency}{amount}</strong> because you only owe <strong>{currency}{owe}</strong>.<br>"
                            "Please enter an amount up to {currency}{owe} to settle.",
                            currency=currency,
                            amount=amount,
                            owe=abs(balance),
                        )
                    )
                    return redirect("person-detail", pk=person.pk)

                
                request.session["force_ledger_track"] = True

                params = {
                    "amount": str(amount),
                    "paid_for": person.name,
                    "note": note,
                    "category": "loan_repayment", 
                    "next": request.build_absolute_uri(request.path),
                    "from_people": "1", 
                }
                add_expense_url = reverse("add-expense") + "?" + urlencode(params)

                messages.info(request, "Recording repayment...")
                return redirect(add_expense_url)
            elif direction == "i_borrowed":
                # You borrowed from them → Income (Loan)
                params = {
                    "source": "loan",
                    "person": person.name,
                    "amount": str(amount),
                    "note": note,
                    "next": next_url,
                    "from_people": "1",
                }
                add_income_url = reverse("income-add") + "?" + urlencode(params)

                messages.info(
                    request,
                    format_html(
                        "We'll record this as loan income.<br>"
                        "Check details and save it there."
                    ),
                )
                return redirect(add_income_url)

            else:
                messages.warning(request, "Please choose a valid option.")
                return redirect("person-detail", pk=person.pk)

        # -------- MARK FULLY SETTLED --------
        elif action == "mark_settled":
            if balance != 0:
                PersonLedgerEntry.objects.create(
                    user=user,
                    person=person,
                    amount=-balance,          # bring balance back to 0
                    source_type="manual",
                    note="Marked as fully settled",
                )
                messages.success(
                    request,
                    f"Marked balance with {person.name} as fully settled."
                )
            else:
                messages.info(
                    request,
                    f"You and {person.name} are already settled."
                )

            return redirect("person-detail", pk=person.pk)

        # If some unknown action sneaks in
        else:
            messages.warning(request, "Unknown action.")
            return redirect("person-detail", pk=person.pk)

    # -------- GET: normal render --------
    context = {
        "person": person,
        "ledger_page": ledger_page,
        "balance": balance,
    }
    return render(request, "people/person_detail.html", context)


@login_required
def person_create(request):
    if request.method == "POST":
        form = PersonForm(request.POST, user=request.user)   #  pass user
        if form.is_valid():
            person = form.save(commit=False)
            person.user = request.user
            person.save()
            return redirect("person-detail", pk=person.pk)
    else:
        form = PersonForm(user=request.user)  

    context = {"form": form}
    return render(request, "people/person_form.html", context)


@login_required
def apply_income_to_people(request, person_id, income_id):
    user = request.user
    person = get_object_or_404(Person, pk=person_id, user=user)
    income = get_object_or_404(Income, pk=income_id, user=user)

    next_url = request.GET.get("next") or reverse("income-list")

    # Mark income as applied — signal will rebuild ledger entries (signals should check TRACK)
    income.applied_to_people = True
    income.save()

    messages.success(request, f"Updated balance with {person.name} using this income entry.")
    return redirect(next_url)


# ----------------- ASK banner actions (APPLY / APPLY & TRACK / NO_TRACK) -----------------



@login_required
@require_POST
def apply_expense_and_track(request, person_id, expense_id):
    """
    User clicked "Yes — track & apply" for an ASK person.
    We set tracking_preference -> TRACK and force-apply ledger changes for this expense.
    """
    user = request.user
    person = get_object_or_404(Person, pk=person_id, user=user)
    expense = get_object_or_404(Expense, pk=expense_id, user=user)

    request.session.pop("pending_banner", None) # persistent banner 

    # Set to TRACK using model constant
    person.tracking_preference = Person.TRACK
    person.save(update_fields=["tracking_preference"])

    try:
        # force apply regardless of previous preference
        apply_expense_to_person_ledger(user, expense, force_apply=True)
    except Exception as e:
        messages.warning(request, "Failed to apply expense to ledger: " + str(e))
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("my-expenses")
        return redirect(next_url)

    messages.success(request, f"Now tracking {person.name}; ledger updated for this expense.")
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("my-expenses")
    return redirect(next_url)


@login_required
@require_POST
def apply_expense_once(request, person_id, expense_id):
    """
    User clicked "Apply this once" for an ASK person.
    We force-apply ledger entries for this expense but keep person's preference unchanged.
    """
    user = request.user
    person = get_object_or_404(Person, pk=person_id, user=user)
    expense = get_object_or_404(Expense, pk=expense_id, user=user)

    
    request.session.pop("pending_banner", None)

    try:
        apply_expense_to_person_ledger(user, expense, force_apply=True)
    except Exception as e:
        messages.warning(request, "Failed to apply expense to ledger: " + str(e))
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("my-expenses")
        return redirect(next_url)

    messages.success(request, f"Applied this expense to {person.name} for now (preference still Ask).")
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("my-expenses")
    return redirect(next_url)


@login_required
def set_person_no_track(request, person_id):
    if request.method != "POST":
        next_url = request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("people-list")
        return redirect(next_url)

    #  CLEAR PERSISTENT BANNER
    request.session.pop("pending_banner", None)

    person = get_object_or_404(Person, pk=person_id, user=request.user)

    if hasattr(person, "tracking_preference"):
        person.tracking_preference = Person.NO_TRACK
        person.archived = True
        person.save(update_fields=["tracking_preference", "archived"])
    else:
        if hasattr(person, "auto_suggest_enabled"):
            person.auto_suggest_enabled = False
            person.save(update_fields=["auto_suggest_enabled"])

    # Archive ledger rows (keep data but hide from active sums)
    PersonLedgerEntry.objects.filter(user=request.user, person=person).update(archived=True)

    messages.success(request, f"We will not track balances with {person.name} going forward. They are archived and can be restored from the Untracked list.")
    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("people-list")
    return redirect(next_url)



@login_required
def set_person_track(request, person_id):
    if request.method != "POST":
        next_url = request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("people-list")
        return redirect(next_url)

    #  CLEAR PERSISTENT BANNER
    request.session.pop("pending_banner", None)

    person = get_object_or_404(Person, pk=person_id, user=request.user)

    if hasattr(person, "tracking_preference"):
        person.tracking_preference = Person.TRACK
        person.save(update_fields=["tracking_preference"])
    else:
        if hasattr(person, "auto_suggest_enabled"):
            person.auto_suggest_enabled = True
            person.save(update_fields=["auto_suggest_enabled"])

    messages.success(request, f"Now tracking balances with {person.name}.")
    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("people-list")
    return redirect(next_url)


@login_required
def set_person_ask(request, person_id):
    if request.method != "POST":
        next_url = request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("people-list")
        return redirect(next_url)

    #  CLEAR PERSISTENT BANNER
    request.session.pop("pending_banner", None)
    person = get_object_or_404(Person, pk=person_id, user=request.user)

    if hasattr(person, "tracking_preference"):
        person.tracking_preference = Person.ASK
        person.save(update_fields=["tracking_preference"])
    else:
        if hasattr(person, "auto_suggest_enabled"):
            person.auto_suggest_enabled = True
            person.save(update_fields=["auto_suggest_enabled"])

    messages.success(request, f"We will ask before tracking {person.name} next time.")
    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER") or reverse("people-list")
    return redirect(next_url)


@login_required
def person_change_tracking(request, person_id):
    """
    Simple page to change a person's tracking preference.
    GET -> render the three-option form.
    POST -> set tracking_preference to one of: TRACK / ASK / NO_TRACK
            (falls back to auto_suggest_enabled if model lacks field)
    """
    person = get_object_or_404(Person, pk=person_id, user=request.user)

    if request.method == "POST":
        choice = request.POST.get("tracking_choice")
        if choice not in {Person.TRACK, Person.ASK, Person.NO_TRACK}:
            messages.warning(request, "Invalid choice.")
            return redirect(request.path)

        if hasattr(person, "tracking_preference"):
            person.tracking_preference = choice
            person.save(update_fields=["tracking_preference"])
        else:
            # legacy fallback
            if hasattr(person, "auto_suggest_enabled"):
                person.auto_suggest_enabled = (choice != Person.NO_TRACK)
                person.save(update_fields=["auto_suggest_enabled"])

        messages.success(request, f"Tracking preference updated for {person.name}.")
        # redirect back to person detail or next param
        next_url = request.POST.get("next") or request.GET.get("next") or reverse("person-detail", args=[person.pk])
        return redirect(next_url)

    # GET -> render
    return render(request, "people/person_change_tracking.html", {"person": person})

@login_required
def restore_person_tracking(request, person_id):
    """
    POST handler. Expects form field 'restore_action' with values:
      - 'reapply'  -> unarchive person and unarchive their ledger rows (reintroduce previous balance)
      - 'start_fresh' -> unarchive person but archive existing ledger rows so balance starts at 0
    """
    if request.method != "POST":
        return redirect(request.META.get("HTTP_REFERER") or reverse("people-list"))

    person = get_object_or_404(Person, pk=person_id, user=request.user)
    action = request.POST.get("restore_action")

    if action == "reapply":
        person.archived = False
        person.tracking_preference = Person.TRACK
        person.save(update_fields=["archived", "tracking_preference"])
        # unarchive ledger rows
        PersonLedgerEntry.objects.filter(user=request.user, person=person).update(archived=False)
        messages.success(request, f"Restored tracking for {person.name} and reapplied previous balance.")
    else:
        messages.warning(request, "Invalid restore action.")
    return redirect(reverse("person-detail", args=[person.pk]))


from django.views.decorators.http import require_POST

@login_required
@require_POST
def apply_income_and_track(request, person_id, income_id):
    user = request.user
    person = get_object_or_404(Person, pk=person_id, user=user)
    income = get_object_or_404(Income, pk=income_id, user=user)

    #  CLEAR PERSISTENT BANNER
    request.session.pop("pending_banner", None)
    # set person to track
    if hasattr(Person, "TRACK"):
        person.tracking_preference = Person.TRACK
    else:
        person.tracking_preference = "track"
    person.save(update_fields=["tracking_preference"])

    # marking income as explicitly applied 
    income.applied_to_people = True
    income.save(update_fields=["applied_to_people"])

    
    try:
        apply_income_to_person_ledger(user, person, income)
    except Exception as e:
        messages.warning(request, "Failed to apply income to ledger: " + str(e))
        next_url = request.POST.get("next") or request.GET.get("next") or "/"
        return redirect(next_url)

    messages.success(request, f"Now tracking {person.name}; ledger updated for this income.")
    return redirect(request.GET.get("next") or "/")

@login_required
@require_POST
def apply_income_once(request, person_id, income_id):
    user = request.user
    person = get_object_or_404(Person, pk=person_id, user=user)
    income = get_object_or_404(Income, pk=income_id, user=user)

    #  CLEAR PERSISTENT BANNER
    request.session.pop("pending_banner", None)

    # Mark income as applied once
    income.applied_to_people = True
    income.save(update_fields=["applied_to_people"])

    try:
        apply_income_to_person_ledger(user, person, income)
    except Exception as e:
        messages.warning(request, "Failed to apply income to ledger: " + str(e))
        next_url = request.POST.get("next") or request.GET.get("next") or "/"
        return redirect(next_url)

    messages.success(request, f"Applied this income to {person.name} for now (preference unchanged).")
    return redirect(request.GET.get("next") or "/")

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import redirect

@login_required
@require_POST
def clear_pending_banner(request):
    request.session.pop("pending_banner", None)
    return redirect(request.META.get("HTTP_REFERER", "/"))

@login_required
@require_POST
def person_delete(request, pk):
    person = get_object_or_404(Person, pk=pk, user=request.user)

    name = person.name

    # Clear any pending banner involving this person
    request.session.pop("pending_banner", None)

    # Hard delete person 
    person.delete()

    messages.success(
        request,
        f"{name} has been permanently removed from People and history."
    )

    return redirect("people-list")


