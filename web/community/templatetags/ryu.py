from django import template
from django.utils import timezone, translation
from django.utils.dateformat import format as date_format

register = template.Library()


@register.filter
def en_date(value, fmt="M d"):
    """The original showed English month names ('Nov 13'); keep that whatever the site language."""
    if not value:
        return ""
    with translation.override("en"):
        return date_format(timezone.localtime(value), fmt)


@register.filter
def handle(name):
    """'Some Name' -> 'somename' (the original's @handle)."""
    return "".join(str(name or "").split()).lower()
