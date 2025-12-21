from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import SmartPasswordResetView


urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    # Forgot password
    path(
            "password-reset/",
            SmartPasswordResetView.as_view(
                template_name="accounts/password_reset.html"
            ),
            name="password_reset",
        ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path('guest-login/', views.guest_login_view, name='guest_login'),

    path('profile/delete/', views.delete_account_view, name='delete-account'),

    path('secret-cleanup-hook/', views.cleanup_guests, name='cleanup_guests'),

]
