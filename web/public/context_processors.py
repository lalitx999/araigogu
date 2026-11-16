from . import seo as seo_lib


def seo(request):
    """Default <head> metadata by URL name; a view can pass its own `meta` to override it."""
    match = getattr(request, "resolver_match", None)
    return {"meta": seo_lib.page_meta(request, match.url_name if match and match.url_name else "")}
