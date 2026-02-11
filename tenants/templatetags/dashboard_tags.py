"""Custom template tags for the dashboard."""
from django import template

register = template.Library()


@register.filter(name="split_pairs")
def split_pairs(value):
    """Split 'Label1:key1,Label2:key2' into list of (label, key) tuples.
    Usage: {% for label, key in "Name:name,Age:age"|split_pairs %}
    """
    pairs = []
    for pair in value.split(","):
        parts = pair.strip().split(":")
        if len(parts) == 2:
            pairs.append((parts[0].strip(), parts[1].strip()))
    return pairs


@register.filter(name="intcomma_safe")
def intcomma_safe(value):
    """Format an integer with commas. Safe for None."""
    if value is None:
        return "0"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


@register.filter(name="stringformat")
def stringformat_filter(value, arg):
    """Convert value using string format. E.g. {{ val|stringformat:'s' }}"""
    try:
        return f"%{arg}" % value
    except (TypeError, ValueError):
        return str(value)
