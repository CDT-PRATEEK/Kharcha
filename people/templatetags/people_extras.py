from django import template

register = template.Library()

@register.filter
def abs_val(value):
    """Return absolute value of a number."""
    try:
        return abs(value)
    except Exception:
        return value
