from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def qs_page(context, page_number):
    """Build ?query with page=N while preserving other GET params (e.g. edit=)."""
    request = context['request']
    query = request.GET.copy()
    query['page'] = page_number
    return '?' + query.urlencode()
