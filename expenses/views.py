
from datetime import date
import calendar
from decimal import Decimal
from urllib.parse import urlparse, parse_qs, urlencode
import csv
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import HttpResponse
from django.urls import reverse
from accounts.utils import get_currency_symbol
from django.contrib import messages
from .forms import ExpenseForm
from .models import Expense, Category
from people.utils import get_or_create_person_by_name, apply_expense_to_person_ledger
from people.models import Person


def month_start_end(year, month):
    """Return (first_day, last_day) for a given year/month."""
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    return start, end


def month_redirect_url(next_url, exp_date):
    """
    Use the expense date's month to build a my-expenses URL.
    Reuse existing filters from next_url (except from_date, to_date, page).
    """
    
    base_path = "/my-expenses/"

    
    if not exp_date:
        today = timezone.localdate()
        exp_date = today

    # Month range for the expense's date
    start, end = month_start_end(exp_date.year, exp_date.month)
    month_from = start.isoformat()
    month_to = end.isoformat()

    if not next_url:
        return f"{base_path}?from_date={month_from}&to_date={month_to}"

    parsed = urlparse(next_url)
    q = parse_qs(parsed.query)

    # Remove previous range + page from next_url
    for key in ["from_date", "to_date", "page"]:
        q.pop(key, None)

    # Set new month from/to based on expense.date
    q["from_date"] = [month_from]
    q["to_date"] = [month_to]

    new_query = urlencode(q, doseq=True)
    return parsed.path + ("?" + new_query if new_query else "")


@login_required
def my_expenses(request):
    user = request.user

    # ---- Base queryset: this user's expenses ----
    base_qs = Expense.objects.filter(user=user).select_related("category")

    # ========= 1. DATE RANGE & MONTH NAV LOGIC =========
    today = timezone.localdate()

    raw_from = request.GET.get("from_date")
    raw_to = request.GET.get("to_date")

    # If user hasn't provided any from/to → default to current month
    if "from_date" not in request.GET and "to_date" not in request.GET:
        active_start, active_end = month_start_end(today.year, today.month)
        from_date = active_start.isoformat()
        to_date = active_end.isoformat()
    else:
        # User interacted with filters
        from_date = raw_from or ""
        to_date = raw_to or ""

        # Try to infer the "active month" from from_date if possible
        try:
            if from_date:
                fd = date.fromisoformat(from_date)
            else:
                fd = today
        except ValueError:
            fd = today

        active_start, active_end = month_start_end(fd.year, fd.month)

    # Apply date filters to base_qs
    if from_date:
        base_qs = base_qs.filter(date__gte=from_date)
    if to_date:
        base_qs = base_qs.filter(date__lte=to_date)

    # We'll show this label in UI (e.g. "December 2025")
    month_label = active_start.strftime("%B %Y")

    # Compute previous month & next month ranges
    # prev month
    if active_start.month == 1:
        prev_year = active_start.year - 1
        prev_month = 12
    else:
        prev_year = active_start.year
        prev_month = active_start.month - 1
    prev_start, prev_end = month_start_end(prev_year, prev_month)

    # next month
    if active_start.month == 12:
        next_year = active_start.year + 1
        next_month = 1
    else:
        next_year = active_start.year
        next_month = active_start.month + 1
    next_start, next_end = month_start_end(next_year, next_month)

    # Determine if we should allow going to "next month" (not beyond current month)
    current_month_start, current_month_end = month_start_end(today.year, today.month)
    has_next_month = next_start <= current_month_start

    # This month range (for "This Month" button)
    this_start, this_end = month_start_end(today.year, today.month)
    this_from_date = this_start.isoformat()
    this_to_date = this_end.isoformat()

    # ========= 2. OTHER FILTERS (keep your existing logic) =========

    # ---- Category filter ----
    selected_category = request.GET.get("category", "all")
    selected_category_name = None

    if selected_category != "all":
        base_qs = base_qs.filter(category_id=selected_category)
        cat_obj = Category.objects.filter(pk=selected_category).first()
        if cat_obj:
            selected_category_name = cat_obj.name

    # ---- Payment type filter ----
    payment_type = request.GET.get("payment_type", "all")
    if payment_type != "all":
        base_qs = base_qs.filter(payment_type=payment_type)

    # ---- From / Lender / For filters ----
    from_filter = request.GET.get("from_filter", "all")          # 'all' | 'own' | 'borrowed'
    selected_lender = request.GET.get("lender", "all")
    selected_for_person = request.GET.get("for_person", "all")   # 'all' | 'me' | name

    filtered_qs = base_qs

    if from_filter == "own":
        filtered_qs = filtered_qs.filter(is_borrowed=False)
    elif from_filter == "borrowed":
        filtered_qs = filtered_qs.filter(is_borrowed=True)

    if selected_lender != "all":
        filtered_qs = filtered_qs.filter(
            is_borrowed=True,
            borrowed_from__iexact=selected_lender,
        )

    if selected_for_person == "me":
        filtered_qs = filtered_qs.filter(is_for_others=False)
    elif selected_for_person not in ("all", ""):
        filtered_qs = filtered_qs.filter(
            is_for_others=True,
            paid_for__iexact=selected_for_person,
        )

    # ---- Dropdown lists for lender / for_person ----
    lender_list = (
        Expense.objects
        .filter(user=user, is_borrowed=True)
        .exclude(borrowed_from__isnull=True)
        .exclude(borrowed_from="")
        .values_list("borrowed_from", flat=True)
        .distinct()
        .order_by("borrowed_from")
    )

    for_person_list = (
        Expense.objects
        .filter(user=user, is_for_others=True)
        .exclude(paid_for__isnull=True)
        .exclude(paid_for="")
        .values_list("paid_for", flat=True)
        .distinct()
        .order_by("paid_for")
    )

    has_results = filtered_qs.exists()

    # "filters_off" = only date filters used; others at defaults
    filters_off = (
        selected_category == "all"
        and payment_type == "all"
        and from_filter == "all"
        and selected_lender == "all"
        and selected_for_person == "all"
    )

    # ========= 3. SUMMARY (same idea as before) =========
    total_agg = filtered_qs.aggregate(
        total_amount=Sum("amount"),
    )
    total = total_agg["total_amount"] or Decimal("0.00")

    own_self_total = Decimal("0.00")
    own_others_total = Decimal("0.00")
    borrowed_self_total = Decimal("0.00")

    if filters_off and has_results:
        detail_agg = filtered_qs.aggregate(
            own_self=Sum("amount", filter=Q(is_borrowed=False, is_for_others=False)),
            own_others=Sum("amount", filter=Q(is_borrowed=False, is_for_others=True)),
            borrowed_self=Sum("amount", filter=Q(is_borrowed=True, is_for_others=False)),
        )
        own_self_total = detail_agg["own_self"] or Decimal("0.00")
        own_others_total = detail_agg["own_others"] or Decimal("0.00")
        borrowed_self_total = detail_agg["borrowed_self"] or Decimal("0.00")

    categories = Category.objects.filter(Q(user=user) | Q(user__isnull=True)).order_by("name")

    # ========= 4. PAGINATION =========
    paginator = Paginator(filtered_qs, 25)  # 25 rows per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Build querystring for pagination (keep filters, drop page)
    qd = request.GET.copy()
    if "page" in qd:
        qd.pop("page")
    base_querystring = qd.urlencode()

    # Build querystring for month nav (drop from/to/page, keep other filters)
    month_qd = request.GET.copy()
    for key in ["from_date", "to_date", "page"]:
        if key in month_qd:
            month_qd.pop(key)
    month_base_qs = month_qd.urlencode()

    context = {
        "expenses": page_obj,
        "page_obj": page_obj,
        "base_querystring": base_querystring,
        "categories": categories,
        "from_date": from_date,
        "to_date": to_date,
        "selected_category": selected_category,
        "selected_category_name": selected_category_name,
        "payment_type": payment_type,
        "from_filter": from_filter,
        "lender_list": lender_list,
        "for_person_list": for_person_list,
        "selected_lender": selected_lender,
        "selected_for_person": selected_for_person,
        "has_results": has_results,
        "filters_off": filters_off,
        "total": total,
        "own_self_total": own_self_total,
        "own_others_total": own_others_total,
        "borrowed_self_total": borrowed_self_total,
        # Month nav stuff
        "month_label": month_label,
        "month_base_qs": month_base_qs,
        "prev_from_date": prev_start.isoformat(),
        "prev_to_date": prev_end.isoformat(),
        "next_from_date": next_start.isoformat(),
        "next_to_date": next_end.isoformat(),
        "has_next_month": has_next_month,
        "this_from_date": this_from_date,
        "this_to_date": this_to_date,
    }

    return render(request, "expenses/my_expenses.html", context)


def home(request):
    if request.user.is_authenticated:
        return redirect("my-expenses")
    return render(request, "home.html")



@login_required
def add_expense(request):
    next_url = request.GET.get("next") or request.POST.get("next", "")
    from_people = request.GET.get("from_people") or request.POST.get("from_people")
    currency = get_currency_symbol(request.user.profile)

    if request.method == "POST":
        
        
        source_kind = request.POST.get("source_kind", "own")
        beneficiary_kind = request.POST.get("beneficiary_kind", "me")
        
        

        form = ExpenseForm(request.POST, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user

            # Reset flags
            expense.is_borrowed = False
            expense.borrowed_from = ""
            expense.is_for_others = False
            expense.paid_for = ""

            # Q1: Borrowed?
            if source_kind == "borrowed":
                expense.is_borrowed = True
                expense.borrowed_from = (request.POST.get("borrowed_from") or "").strip()

            # Q2: For Others?
            # if a name exists even if radio is wrong
            paid_for_val = (request.POST.get("paid_for") or "").strip()
            if beneficiary_kind == "other" or paid_for_val:
                expense.is_for_others = True
                expense.paid_for = paid_for_val
                print(f"DEBUG: Detected 'For Others'. Name: {expense.paid_for}") # 👈 Debug

            # Category Logic
            new_category_name = (request.POST.get("new_category") or "").strip()
            if new_category_name:
                normalized_name = new_category_name.strip().title()
                existing_category = Category.objects.filter(user=request.user, name__iexact=normalized_name).first()
                if not existing_category:
                    existing_category = Category.objects.filter(user__isnull=True, name__iexact=normalized_name).first()
                
                if existing_category:
                    expense.category = existing_category
                else:
                    expense.category = Category.objects.create(name=normalized_name, user=request.user)

            if expense.category is None:
                misc, _ = Category.objects.get_or_create(name="Miscellaneous", user=None)
                expense.category = misc
            

            
            # Preventing "Repayment" if not owing money
            
            
            force_track_session = request.session.get("force_ledger_track", False)
            
            # Check GET/POST for from_people flag
            from_people_param = request.GET.get("from_people") or request.POST.get("from_people")
            is_wizard = force_track_session or (str(from_people_param) == "1")

            # 2. If NOT from Wizard, apply strict rules
            if not is_wizard:
                cat_name = ""
                if expense.category:
                    cat_name = expense.category.name.lower().strip()
                
                
                if "repayment" in cat_name or "settlement" in cat_name:
                    # Identify the person
                    check_person = None
                    if expense.is_for_others and expense.paid_for:
                        
                        from people.utils import get_person_by_name
                        check_person = get_person_by_name(request.user, expense.paid_for)
                    
                    if check_person:
                        # Check Balance
                        from django.db.models import Sum
                        agg = check_person.ledger_entries.filter(archived=False).aggregate(total=Sum("amount"))
                        current_balance = agg["total"] or Decimal("0.00")
                        
                        # BLOCK if Balance >= 0 (We don't owe them, so we can't repay)
                        if current_balance >= 0:
                            messages.warning(
                                request, 
                                f"You cannot use category '{expense.category.name}' because you don't owe {check_person.name} anything. If you're lending, please use 'Loan' instead."
                            )
                            
                            # Re-render the form with errors
                            context = {
                                "form": form,
                                "is_edit": False, 
                                "next": next_url,
                                "source_kind": source_kind,
                                "beneficiary_kind_default": beneficiary_kind,
                                "from_people": from_people,
                            }
                            return render(request, "expenses/expense_form.html", context)


        
            expense.save()
            

        
            

            # Check Session (using .get first so we don't lose it on failure)
            force_track_session = request.session.get("force_ledger_track", False)
           

            target_person = None
            if expense.is_borrowed and expense.borrowed_from:
                target_person = get_or_create_person_by_name(request.user, expense.borrowed_from)
                print(f"DEBUG: Target Person (Borrowed) -> {target_person.name}")
            elif expense.is_for_others and expense.paid_for:
                target_person = get_or_create_person_by_name(request.user, expense.paid_for)
                print(f"DEBUG: Target Person (Paid For) -> {target_person.name}")
            else:
                print("DEBUG: No target person identified.")

            if target_person:
                is_wizard_flow = force_track_session or (str(from_people) == "1")
               

                if is_wizard_flow:
                    print("DEBUG: ACTION -> Force Applying to Ledger...") 
                    #  Session POP 
                    if force_track_session:
                        request.session.pop("force_ledger_track", None)
                        
                    apply_expense_to_person_ledger(request.user, expense, force_apply=True)
                    

                else:
                    
                    if target_person.tracking_preference == Person.TRACK:
                        
                        apply_expense_to_person_ledger(request.user, expense, force_apply=True)

                    elif target_person.tracking_preference == Person.ASK:
                        
                        request.session.pop("pending_banner", None)
                        redirect_target = month_redirect_url(next_url, expense.date)

                        apply_and_track_url = reverse("people-apply-expense-and-track", args=[target_person.pk, expense.pk]) + "?" + urlencode({"next": redirect_target})
                        apply_once_url = reverse("people-apply-expense-once", args=[target_person.pk, expense.pk]) + "?" + urlencode({"next": redirect_target})
                        set_no_track_url = reverse("people-set-no-track", args=[target_person.pk]) + "?" + urlencode({"next": redirect_target})

                        banner_html = (
                            f"<div style='margin-bottom:.4rem;'>"
                            f"<strong>Expense involves {target_person.name}</strong> — {currency}{expense.amount}. "
                            f"Do you want Kharcha to track balances with <strong>{target_person.name}</strong>? "
                            f"<a href='#' class='ask-btn ask-yes' data-post-url='{apply_and_track_url}'>Yes — track & apply</a> · "
                            f"<a href='#' class='ask-btn ask-once' data-post-url='{apply_once_url}'>Apply this once</a> · "
                            f"<a href='#' class='ask-btn ask-no' data-post-url='{set_no_track_url}'>No — don't track</a>"
                            f"</div>"
                        )
                        request.session["pending_banner"] = {"type": "expense_ask", "html": banner_html}
                        request.session.modified = True
            
            
            return redirect(month_redirect_url(next_url, expense.date))
        else:
            print("DEBUG: Form Invalid:", form.errors)

    else:
        # GET Request Logic (Simplified for brevity - your existing code works here)
        source_kind = request.GET.get("source_kind", "own")
        beneficiary_kind_default = request.GET.get("beneficiary_kind", "me")
        initial = {}
        amount = request.GET.get("amount")
        if amount: initial["amount"] = amount
        paid_for = request.GET.get("paid_for")
        if paid_for:
            initial["paid_for"] = paid_for
            beneficiary_kind_default = "other"
        note = request.GET.get("note")
        if note: initial["description"] = note
        
        # Category prefill
        cat_param = request.GET.get("category")
        if cat_param:
            alias = cat_param.strip().lower().replace("_", " ").replace("-", " ").strip()
            lookup_name = "Repayment" if alias in {"repayment", "loan repayment", "loan_repayment"} else cat_param.strip().title()
            category_obj = Category.objects.filter(user=request.user, name__iexact=lookup_name).first()
            if not category_obj: category_obj = Category.objects.filter(user__isnull=True, name__iexact=lookup_name).first()
            if category_obj: initial["category"] = category_obj.pk

        form = ExpenseForm(initial=initial, user=request.user)

    context = {
        "form": form,
        "is_edit": False,
        "next": next_url,
        "source_kind": source_kind,
        "beneficiary_kind_default": beneficiary_kind_default,
        "from_people": from_people,
    }
    return render(request, "expenses/expense_form.html", context)


@login_required
def edit_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)

    # If there's a ?next= in the URL or POST, use it.
    # Otherwise, default to that expense's month view.
    next_url = request.GET.get("next") or request.POST.get("next")
    if not next_url:
        next_url = month_redirect_url(None, expense.date)

    # Determine current radio defaults from the expense instance
    source_kind = "borrowed" if expense.is_borrowed else "own"
    beneficiary_kind_default = "other" if expense.is_for_others else "me"

    if request.method == "POST":
        # Read radios from POST (fall back to previously-determined defaults)
        source_kind = request.POST.get("source_kind", source_kind)
        beneficiary_kind = request.POST.get("beneficiary_kind", beneficiary_kind_default)

        form = ExpenseForm(request.POST, instance=expense, user=request.user)

        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user

            # apply radio choices to model flags
            expense.is_borrowed = (source_kind == "borrowed")
            expense.is_for_others = (beneficiary_kind == "other")

            # Update borrowed_from / paid_for from POST (or clear if not applicable)
            if expense.is_borrowed:
                expense.borrowed_from = (request.POST.get("borrowed_from") or "").strip()
            else:
                expense.borrowed_from = ""

            if expense.is_for_others:
                expense.paid_for = (request.POST.get("paid_for") or "").strip()
            else:
                expense.paid_for = ""

            # same new_category logic as add_expense ...
            new_category_name = (request.POST.get("new_category") or "").strip()
            if new_category_name:
                normalized_name = new_category_name.strip().title()

                existing_category = Category.objects.filter(
                    user=request.user,
                    name__iexact=normalized_name,
                ).first()

                if not existing_category:
                    existing_category = Category.objects.filter(
                        user__isnull=True,
                        name__iexact=normalized_name,
                    ).first()

                if existing_category:
                    expense.category = existing_category
                else:
                    expense.category = Category.objects.create(
                        name=normalized_name,
                        user=request.user,
                    )

            if expense.category is None:
                misc, _ = Category.objects.get_or_create(
                    name="Miscellaneous",
                    user=None,
                )
                expense.category = misc

            expense.save()

            redirect_url = month_redirect_url(next_url, expense.date)
            return redirect(redirect_url)
    else:
        form = ExpenseForm(instance=expense, user=request.user)

    context = {
        "form": form,
        "source_kind": source_kind,
        # IMPORTANT: template expects beneficiary_kind_default
        "beneficiary_kind_default": beneficiary_kind_default,
        "is_edit": True,
        "next": next_url,
    }
    return render(request, "expenses/expense_form.html", context)

@login_required
def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    next_url = request.GET.get("next") or request.POST.get("next")
    redirect_url = month_redirect_url(next_url, expense.date)

    if request.method == "POST":
        expense.delete()
        return redirect(redirect_url)

    # If someone hits the URL via GET directly, just send them back
    return redirect(redirect_url)


@login_required
def expense_download_csv(request):
    """
    Download the filtered expense list as CSV.
    Duplicates filtering logic intentionally to avoid
    impacting existing expense views.
    """

    user = request.user
    today = date.today()
    formatted_date = today.strftime("%d-%b-%Y").lower()

    from_date_str = request.GET.get("from_date") or ""
    to_date_str = request.GET.get("to_date") or ""

    if from_date_str and to_date_str:
        try:
            current_from = date.fromisoformat(from_date_str)
            current_to = date.fromisoformat(to_date_str)
        except ValueError:
            current_from, current_to = today.replace(day=1), today
    else:
        current_from, current_to = today.replace(day=1), today

    qs = (
        Expense.objects
        .filter(user=user, date__range=(current_from, current_to))
        .order_by("-date", "-created_at")
    )

    selected_category = request.GET.get("category", "all")
    selected_person = request.GET.get("person", "all")
    payment_type = request.GET.get("payment_type", "all")

    if selected_category != "all":
        qs = qs.filter(category_id=selected_category)

    if selected_person != "all":
        qs = qs.filter(paid_for__iexact=selected_person)

    if payment_type != "all":
        qs = qs.filter(payment_type=payment_type)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="expenses_{formatted_date}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Date",
        "Amount",
        "Category",
        "Description",
        "Paid For",
        "Payment Type",
    ])

    for expense in qs:
        writer.writerow([
            expense.date,
            expense.amount,
            expense.category.name if expense.category else "",
            expense.description or "",
            expense.paid_for or "",
            expense.payment_type or "",
        ])

    return response
