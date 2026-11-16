"""Public pages (About, FAQ, guides) and machine-readable files (robots, sitemap, llms, PWA)."""
import hashlib
import json
import time
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from chat.languages import LANGUAGES

from . import seo
from .content import CONTENT_UPDATED, GUIDES, GUIDES_BY_SLUG, faqs, product_facts

# ---------- pages ----------


@require_GET
def about(request):
    return render(request, "home.html", {
        "total_users": get_user_model().objects.count(),
        "language_count": len(LANGUAGES),
        "faq_preview": faqs()[:4],
        "contact_email": settings.CONTACT_EMAIL,
        "jsonld": seo.jsonld(seo.organization(request), seo.website(request), seo.web_application(request),
                             seo.breadcrumbs(request, [("หน้าหลัก", "/"), ("เกี่ยวกับ", reverse("about"))])),
    })


@require_GET
def faq(request):
    return render(request, "public/faq.html", {
        "faqs": faqs(), "updated": CONTENT_UPDATED, "contact_email": settings.CONTACT_EMAIL,
        "jsonld": seo.jsonld(seo.organization(request), seo.faq_page(request),
                             seo.breadcrumbs(request, [("หน้าหลัก", "/"), ("คำถามที่พบบ่อย", reverse("faq"))])),
    })


@require_GET
def guides(request):
    items = [{"@type": "ListItem", "position": i, "url": seo.absolute(request, reverse("guide", args=[g["slug"]])),
              "name": g["title"]} for i, g in enumerate(GUIDES, start=1)]
    return render(request, "public/guides.html", {
        "guides": GUIDES, "contact_email": settings.CONTACT_EMAIL,
        "jsonld": seo.jsonld(seo.organization(request),
                             {"@type": "ItemList", "name": "คู่มือเรียนภาษากับ AI", "itemListElement": items},
                             seo.breadcrumbs(request, [("หน้าหลัก", "/"), ("คู่มือ", reverse("guides"))])),
    })


@require_GET
def guide(request, slug):
    g = GUIDES_BY_SLUG.get(slug)
    if not g:
        raise Http404
    meta = seo.page_meta(request, "guides")
    meta.update(title=g["title"], description=g["description"], og_type="article",
                canonical=seo.absolute(request, request.path))
    return render(request, "public/guide.html", {
        "guide": g, "updated": CONTENT_UPDATED, "meta": meta, "contact_email": settings.CONTACT_EMAIL,
        "others": [o for o in GUIDES if o["slug"] != slug],
        "jsonld": seo.jsonld(seo.organization(request), seo.article(request, g),
                             seo.breadcrumbs(request, [("หน้าหลัก", "/"), ("คู่มือ", reverse("guides")),
                                                      (g["title"], request.path)])),
    })


@require_GET
def offline(request):
    """Shown by the service worker when there is no connection. Must not depend on the session."""
    return render(request, "public/offline.html")


# ---------- machine-readable ----------

def _text(body: str, content_type: str = "text/plain; charset=utf-8", max_age: int = 3600) -> HttpResponse:
    response = HttpResponse(body, content_type=content_type)
    response["Cache-Control"] = f"public, max-age={max_age}"
    return response


PUBLIC_PATHS = ["/", "/about/", "/faq/", "/guides/", "/accounts/register/"]


@require_GET
def robots_txt(request):
    base = seo.site_url(request)
    lines = [
        "# ARAI GO GU",
        "User-agent: *",
        "Allow: /$", "Allow: /about/", "Allow: /faq/", "Allow: /guides/", "Allow: /accounts/register/",
        "Allow: /static/", "Allow: /llms.txt", "Allow: /llms-full.txt",
        # private, per-user or action URLs
        "Disallow: /admin/", "Disallow: /chat/", "Disallow: /dashboard/", "Disallow: /community/",
        "Disallow: /accounts/", "Disallow: /media/", "Disallow: /*?",
        "",
        # AI assistants and AI search may read and cite the public pages (same rules as above)
        *[line for bot in ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
                           "PerplexityBot", "Google-Extended", "Applebot-Extended")
          for line in (f"User-agent: {bot}", "Allow: /$", "Allow: /about/", "Allow: /faq/", "Allow: /guides/",
                       "Allow: /llms.txt", "Allow: /llms-full.txt", "Disallow: /", "")],
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return _text("\n".join(lines))


@require_GET
def sitemap_xml(request):
    base = seo.site_url(request)
    updated = CONTENT_UPDATED.isoformat()
    urls = [(p, "weekly" if p == "/" else "monthly", "1.0" if p == "/" else "0.7") for p in PUBLIC_PATHS]
    urls += [(reverse("guide", args=[g["slug"]]), "monthly", "0.8") for g in GUIDES]
    entries = "".join(
        f"<url><loc>{escape(base + path)}</loc><lastmod>{updated}</lastmod>"
        f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        for path, freq, prio in urls
    )
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>\n')
    return _text(body, "application/xml; charset=utf-8")


def _llms_context(request):
    return {"base": seo.site_url(request), "facts": product_facts(), "faqs": faqs(), "guides": GUIDES,
            "updated": CONTENT_UPDATED, "contact_email": settings.CONTACT_EMAIL, "languages": LANGUAGES}


@require_GET
def llms_txt(request):
    """llmstxt.org: a short Markdown map of the site for AI assistants."""
    return _text(render_to_string("public/llms.txt", _llms_context(request)), "text/markdown; charset=utf-8")


@require_GET
def llms_full_txt(request):
    """Everything citable in one Markdown file: product facts, FAQ and the full guides."""
    return _text(render_to_string("public/llms-full.txt", _llms_context(request)), "text/markdown; charset=utf-8")


# ---------- PWA ----------

@require_GET
@cache_control(no_cache=True)
def manifest(request):
    body = render_to_string("public/manifest.webmanifest", {"guest_limit": settings.GUEST_DAILY_CHAT_LIMIT}, request)
    return HttpResponse(body, content_type="application/manifest+json; charset=utf-8")


_BOOT = hashlib.sha256(str(time.time()).encode()).hexdigest()[:6]

# Files the app shell needs offline. With ManifestStaticFilesStorage these resolve to hashed,
# immutable URLs, so the cache name changes on every deploy that changes any of them.
SHELL_STATIC = [
    "vendor/bootstrap/css/bootstrap.min.css", "vendor/bootstrap/js/bootstrap.bundle.min.js",
    "vendor/bootstrap-icons/bootstrap-icons.min.css", "vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
    "css/fonts.css", "css/app.css", "css/pages/chat_app.css", "css/pages/auth.css",
    "js/app.js", "js/chat_app.js",
    "fonts/inter-latin-wght-normal.woff2", "fonts/noto-sans-thai-thai-wght-normal.woff2",
    "fonts/noto-sans-thai-latin-wght-normal.woff2",
    "img/ryu-128.webp", "img/icons/icon-192.png", "img/icons/favicon-32.png",
]


@require_GET
@cache_control(no_cache=True)
def service_worker(request):
    precache = [static(p) for p in SHELL_STATIC] + [reverse("offline")]
    version = hashlib.sha256("|".join(precache).encode()).hexdigest()[:12]
    if settings.DEBUG:  # unhashed names in development: a new version per server start
        version += "-" + _BOOT
    body = render_to_string("public/sw.js", {"precache_json": json.dumps(precache), "version": version,
                                             "offline_url": reverse("offline"), "debug": settings.DEBUG})
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    return response
