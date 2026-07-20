from django import template

register = template.Library()

@register.filter
def getitem(d, key):
    """Dict key lookup: {{ my_dict|getitem:key }}. Works with int and string keys."""
    try:
        return d[key]
    except (KeyError, TypeError):
        try:
            return d[int(key)]
        except (KeyError, TypeError, ValueError):
            return 0

@register.filter
def is_none(value):
    return value is None

@register.filter
def pts_display(value):
    """Render None (no bet) as em dash; integers pass through unchanged."""
    return '—' if value is None else value
