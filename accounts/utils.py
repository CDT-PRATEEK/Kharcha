CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
}

def get_currency_symbol(profile):
    if not profile:
        return "₹"
    return CURRENCY_SYMBOLS.get(profile.default_currency, "₹")
