from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from expenses.views import month_redirect_url 
from accounts.utils import get_currency_symbol 


from .models import Income
from .forms import IncomeForm
import csv
from django.http import HttpResponse
from people.models import Person, PersonLedgerEntry




def _month_bounds(d: date):
    first = d.replace(day=1)
    next_month_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = next_month_first - timedelta(days=1)
    return first, last


@login_required
def income_list(request):
    user = request.user

    # ---------------- Date range (from_date / to_date) like expenses ----------------
    today = date.today()
    from_date_str = request.GET.get("from_date") or ""
    to_date_str = request.GET.get("to_date") or ""

    if from_date_str and to_date_str:
        try:
            current_from = date.fromisoformat(from_date_str)
            current_to = date.fromisoformat(to_date_str)
        except ValueError:
            # fallback = this month
            current_from, current_to = _month_bounds(today)
            from_date_str = current_from.isoformat()
            to_date_str = current_to.isoformat()
    else:
        # default = this month
        current_from, current_to = _month_bounds(today)
        from_date_str = current_from.isoformat()
        to_date_str = current_to.isoformat()

    # current month label
    month_label = current_from.strftime("%B %Y")

    # prev / next month ranges
    current_month_first = current_from.replace(day=1)

    prev_month_last = current_month_first - timedelta(days=1)
    prev_from, prev_to = _month_bounds(prev_month_last)
    prev_from_date = prev_from.isoformat()
    prev_to_date = prev_to.isoformat()

    next_month_first = (current_month_first.replace(day=28) + timedelta(days=4)).replace(day=1)
    next_from, next_to = _month_bounds(next_month_first)
    next_from_date = next_from.isoformat()
    next_to_date = next_to.isoformat()

    # next month should not go beyond current month start
    this_from, this_to = _month_bounds(today)
    this_from_date = this_from.isoformat()
    this_to_date = this_to.isoformat()
    has_next_month = next_from <= this_from

    # ---------------- Base queryset ----------------
    base_qs = (
        Income.objects
        .filter(user=user, date__range=(current_from, current_to))
        .order_by("-date", "-created_at")
    )

    # ---------------- Filters (source / person / payment_type) ----------------
    selected_source = request.GET.get("source", "all")
    selected_person = request.GET.get("person", "all")
    payment_type = request.GET.get("payment_type", "all")

    if selected_source != "all":
        base_qs = base_qs.filter(source=selected_source)

    if selected_person != "all":
        base_qs = base_qs.filter(person__iexact=selected_person)

    if payment_type != "all":
        base_qs = base_qs.filter(payment_type=payment_type)

    # person list for dropdown
    person_list = (
        Income.objects
        .filter(user=user)
        .exclude(person__isnull=True)
        .exclude(person="")
        .values_list("person", flat=True)
        .distinct()
        .order_by("person")
    )

    # ---------------- Summary & flags ----------------
    summary = base_qs.aggregate(total_amount=Sum("amount"))
    total = summary["total_amount"] or Decimal("0.00")
    has_results = base_qs.exists()

    # ---------------- Pagination ----------------
    page_number = request.GET.get("page", 1)
    paginator = Paginator(base_qs, 20)
    page_obj = paginator.get_page(page_number)

    # ---------------- Querystrings for links ----------------
    qs = request.GET.copy()
    qs.pop("page", None)
    base_querystring = qs.urlencode()

    month_qs = request.GET.copy()
    for key in ["from_date", "to_date", "page"]:
        month_qs.pop(key, None)
    month_base_qs = month_qs.urlencode()

    context = {
        "incomes": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,

        "from_date": from_date_str,
        "to_date": to_date_str,

        "month_label": month_label,
        "prev_from_date": prev_from_date,
        "prev_to_date": prev_to_date,
        "next_from_date": next_from_date,
        "next_to_date": next_to_date,
        "this_from_date": this_from_date,
        "this_to_date": this_to_date,
        "has_next_month": has_next_month,
        "month_base_qs": month_base_qs,
        "base_querystring": base_querystring,

        "selected_source": selected_source,
        "selected_person": selected_person,
        "payment_type": payment_type,
        "person_list": person_list,

        "total": total,
        "has_results": has_results,
    }
    return render(request, "income/income_list.html", context)

@login_required
def income_add(request):
    next_url = request.GET.get("next") or request.POST.get("next", "")
    from_people = request.GET.get("from_people") or request.POST.get("from_people")
    currency = get_currency_symbol(request.user.profile)


    def canonical_source_from_param(src):
        if not src:
            return None
        src = src.strip().lower()
        return dict((k.lower(), k) for k, _ in Income.SOURCE_CHOICES).get(src)

    if request.method == "POST":
        form = IncomeForm(request.POST)
        if form.is_valid():
            income = form.save(commit=False)
            income.user = request.user

            # ========== FROM PEOPLE FLOW ==========
            if from_people == "1" and income.person and income.source in {"loan", "loan_repayment"}:
                person = Person.objects.filter(
                    user=request.user,
                    name__iexact=income.person.strip()
                ).first()

                if person:
                    balance = (
                        PersonLedgerEntry.objects
                        .filter(user=request.user, person=person, archived=False)
                        .aggregate(total=Sum("amount"))["total"]
                        or Decimal("0.00")
                    )

                    # Loan repayment when YOU owe them → do NOT auto apply
                    if income.source == "loan_repayment" and balance <= 0:
                        income.applied_to_people = False
                        income.save()
                        return redirect(next_url or "people-list")

                    #  Safe to auto apply
                    income.applied_to_people = True
                    income.save()
                    return redirect(next_url or "people-list")

                income.save()
                return redirect(next_url or "people-list")

            # ========== NORMAL MANUAL ENTRY ==========
            income.save()
            redirect_url = month_redirect_url(
                next_url,
                getattr(income, "date", None) or income.created_at.date()
            )

            # ========== ASK BANNER (SESSION) ==========
            if (
                from_people != "1"
                and income.person
                and income.source in {"loan", "loan_repayment"}
            ):
                person = Person.objects.filter(
                    user=request.user,
                    name__iexact=income.person.strip()
                ).first()

                if person and person.tracking_preference == Person.ASK:
                    apply_track = reverse(
                        "people-apply-income-and-track",
                        args=[person.pk, income.pk]
                    ) + f"?next={redirect_url}"

                    apply_once = reverse(
                        "people-apply-income-once",
                        args=[person.pk, income.pk]
                    ) + f"?next={redirect_url}"

                    dont_track = reverse(
                        "people-set-no-track",
                        args=[person.pk]
                    ) + f"?next={redirect_url}"

                    html = (
                        f"<strong>Income involves {person.name}</strong> — {currency}{income.amount}. "
                        f"Do you want Kharcha to track balances with <strong>{person.name}</strong>? "
                        f"<a href='#' class='ask-btn ask-yes' data-post-url='{apply_track}'>Yes — track & apply</a> · "
                        f"<a href='#' class='ask-btn ask-once' data-post-url='{apply_once}'>Apply this once</a> · "
                        f"<a href='#' class='ask-btn ask-no' data-post-url='{dont_track}'>No — don't track</a>"
                    )

                    request.session["pending_banner"] = {
                        "type": "income_ask",
                        "html": str(html),
                    }
                    request.session.modified = True

            return redirect(redirect_url)

    # ========== GET ==========
    initial = {}
    if request.GET.get("amount"):
        initial["amount"] = request.GET["amount"]
    if request.GET.get("person"):
        initial["person"] = request.GET["person"]
    if request.GET.get("note"):
        initial["description"] = request.GET["note"]

    src = canonical_source_from_param(request.GET.get("source"))
    if src:
        initial["source"] = src

    form = IncomeForm(initial=initial)

    return render(
        request,
        "income/income_form.html",
        {
            "form": form,
            "is_edit": False,
            "next": next_url,
            "from_people": from_people or "",
        },
    )




@login_required
def income_edit(request, pk):
    income = get_object_or_404(Income, pk=pk, user=request.user)

    next_url = request.GET.get("next") or request.POST.get("next")
    if not next_url:
        next_url = month_redirect_url(None, getattr(income, "date", None) or income.created_at.date())

    if request.method == "POST":
        form = IncomeForm(request.POST, instance=income)
        if form.is_valid():
            income = form.save(commit=False)
            income.user = request.user
            # We don't call apply_income_to_person_ledger here; signals will rebuild on save
            income.save()
            if next_url:
                return redirect(next_url)
            return redirect("income-list")
    else:
        form = IncomeForm(instance=income)

    return render(request, "income/income_form.html", {"form": form, "is_edit": True, "next": next_url})




@login_required
def income_delete(request, pk):
    income = get_object_or_404(Income, pk=pk, user=request.user)
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("income-list")

    if request.method == "POST":
        income.delete()
        return redirect(next_url)

    # we use modal; no separate template
    return redirect(next_url)


@login_required
def income_download_csv(request):
    """
    Download the filtered income list as CSV.
    This view intentionally duplicates filter logic
    to avoid impacting existing behavior.
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
            current_from, current_to = _month_bounds(today)
    else:
        current_from, current_to = _month_bounds(today)

    qs = (
        Income.objects
        .filter(user=user, date__range=(current_from, current_to))
        .order_by("-date", "-created_at")
    )

    selected_source = request.GET.get("source", "all")
    selected_person = request.GET.get("person", "all")
    payment_type = request.GET.get("payment_type", "all")

    if selected_source != "all":
        qs = qs.filter(source=selected_source)

    if selected_person != "all":
        qs = qs.filter(person__iexact=selected_person)

    if payment_type != "all":
        qs = qs.filter(payment_type=payment_type)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="income_{formatted_date}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Date",
        "Amount",
        "Source",
        "Person",
        "Payment Type",
        "Description",
    ])

    for income in qs:
        writer.writerow([
            income.date,
            income.amount,
            income.source,
            income.person or "",
            income.payment_type or "",
            income.description or "",
        ])

    return response