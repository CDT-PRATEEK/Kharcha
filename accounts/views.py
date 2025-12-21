from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import uuid
import os
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
import secrets
from .forms import ProfileForm  
from expenses.models import Expense
from income.models import Income
from django.db.models import Sum
from decimal import Decimal
from django.utils.timezone import now
from django.contrib.auth.views import PasswordResetView
from .forms import SmartPasswordResetForm , CustomUserCreationForm
from django.contrib.auth import get_user_model 
from django.views.decorators.http import require_POST



User = get_user_model()



def guest_login_view(request):
    
    random_suffix = uuid.uuid4().hex[:8]
    username = f'guest_{random_suffix}'
    

    # This creates a cryptographically strong random string
    random_password = secrets.token_urlsafe(32)
    
    guest_user = User.objects.create_user(
        username=username, 
        password=random_password 
    )

    login(request, guest_user, backend='django.contrib.auth.backends.ModelBackend')

    request.session['is_guest_session'] = True
    
    messages.success(request, "Welcome! You are using a Guest Account.This is a sandbox environment. Guest data is purged automatically on a weekly schedule.")
    
    next_url = request.GET.get('next') or 'my-expenses'
    return redirect(next_url)

def register_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("my-expenses")
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/register.html", {"form": form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user() 
            login(request, user)
            # if ?next=/something is present, redirect there, else to my-expenses
            next_url = request.GET.get('next') or 'my-expenses'
            return redirect(next_url)
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile_view(request):
    profile = request.user.profile

    is_guest = request.session.get('is_guest_session', False)

    today = now().date()
    month_start = today.replace(day=1)

    total_expense = (
        Expense.objects
        .filter(user=request.user, date__gte=month_start)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    total_income = (
        Income.objects
        .filter(user=request.user, date__gte=month_start)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    monthly_net = total_income - total_expense

    if request.method == "POST":

        if is_guest:
            messages.error(request, "To personalize your profile, please create an account.")
            return redirect("profile")
        
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully")
            return redirect("profile")
    else:
        form = ProfileForm(instance=profile)

    context = {
        "form": form,
        "monthly_net": monthly_net,
        "currency": profile.default_currency,
        "is_guest": is_guest,
    }
    return render(request, "accounts/profile.html", context)

@login_required
@require_POST 
def delete_account_view(request):
    
    # Checks the session variable
    if request.session.get('is_guest_session', False):
        messages.error(request, "Guest accounts cannot be manually deleted.")
        return redirect('profile')

    user = request.user
    user.delete()
    
    logout(request)
    messages.success(request, "Your account has been successfully deleted. We will miss you!")
    return redirect('home')


class SmartPasswordResetView(PasswordResetView):
    form_class = SmartPasswordResetForm


@csrf_exempt
def cleanup_guests(request):
    
    secret_key = request.GET.get('key')
    correct_key = os.environ.get('CLEANUP_KEY')
    
    
    if not correct_key or secret_key != correct_key:
        return HttpResponse("Unauthorized: Wrong or missing Key", status=403)

    
    cutoff_date = timezone.now() - timedelta(hours=24)

    old_guests = User.objects.filter(
        username__startswith='guest_',  
        email=''                        
    ).filter(
        # Last login was over 24 hours ago OR never logged in & joined over 24h ago
        Q(last_login__lt=cutoff_date) | 
        Q(last_login__isnull=True, date_joined__lt=cutoff_date)
    )

    count = old_guests.count()

    if count > 0:
        old_guests.delete()
        msg = f'Successfully cleaned up {count} abandoned guest accounts.'
    else:
        msg = 'No abandoned guest accounts found.'
    

    return HttpResponse(msg)