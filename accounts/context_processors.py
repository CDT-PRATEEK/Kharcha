from .utils import get_currency_symbol

def currency_context(request):
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        return {
            "currency": get_currency_symbol(profile)
        }
    return {
        "currency": "₹"
    }
