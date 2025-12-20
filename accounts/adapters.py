from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_email
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        """
        Handles NORMAL username/password signup
        """
        user = super().save_user(request, user, form, commit=False)

        # Normalizing email
        if user.email:
            user.email = user.email.lower()

        # Safety: username should NEVER be an email for password users
        if user.username and "@" in user.username and not user.email:
            user.email = user.username.lower()

        if commit:
            user.save()
        return user


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Google / social login flow

        Goals:
        1. Copy Google email → User.email
        2. Keep username == email for social users
        3. Attach social account to existing password user if email matches
        4. Populate first_name / last_name (ONLY if missing)
        """

        user = sociallogin.user
        email = user_email(user)

        if not email:
            return

        email = email.lower()

        
        user.email = email

        #  username=email for social users ONLY if not already set
        if not user.username:
            user.username = email

        #  Filling names ONLY if missing (never overwrite)
        extra = sociallogin.account.extra_data or {}

        if not user.first_name:
            user.first_name = extra.get("given_name", "") or ""

        if not user.last_name:
            user.last_name = extra.get("family_name", "") or ""

        try:
            existing_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return

        
        if not sociallogin.is_existing:
            sociallogin.connect(request, existing_user)
