from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    return dictionary.get(key)

@register.filter
def sum_marks(items):
    """Calculate total marks from exam items"""
    total = 0
    for item in items:
        if hasattr(item, 'question') and hasattr(item.question, 'mark'):
            total += item.question.mark
    return total
