"""Page metadata (title, description, robots, canonical) and schema.org JSON-LD."""
import json

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import mark_safe

from .content import CONTENT_UPDATED, faqs, product_facts

DEFAULT_DESCRIPTION = (
    "เรียนภาษาได้ทุกที่ แค่แชทกับพี่ริว AI ติวเตอร์ที่อธิบายเป็นภาษาไทย ตรวจไวยากรณ์ ฝึกบทสนทนา "
    "เตรียมสอบ JLPT TOEIC HSK และแปลจากรูปภาพ ทดลองใช้ฟรีไม่ต้องสมัคร"
)

# url name -> (title, description, indexable). Anything not listed is private: noindex.
PAGES = {
    "home": ("พี่ริว AI ติวเตอร์ภาษา แชทเรียนภาษาฟรี", DEFAULT_DESCRIPTION, True),
    "about": ("เกี่ยวกับ ARAI GO GU", "ARAI GO GU คือเว็บแอปเรียนภาษาด้วยการแชทกับพี่ริว AI ติวเตอร์ รู้จักวิธีใช้ ฟีเจอร์ และคอร์สเรียน", True),
    "faq": ("คำถามที่พบบ่อย", "คำตอบเรื่องการใช้งาน ARAI GO GU: ใช้ฟรีไหม สอนภาษาอะไรได้บ้าง ส่งรูปได้ไหม และข้อมูลถูกเก็บอย่างไร", True),
    "guides": ("คู่มือเรียนภาษากับ AI", "คู่มือใช้ AI ติวเตอร์เรียนภาษาญี่ปุ่น อังกฤษ และเตรียมสอบ JLPT TOEIC HSK อย่างได้ผล", True),
    "register": ("สมัครสมาชิกฟรี", "สมัครฟรีเพื่อบันทึกประวัติแชท ส่งรูปการบ้านให้พี่ริวช่วยตรวจ และดูสถิติการเรียน", True),
    "login": ("เข้าสู่ระบบ", "เข้าสู่ระบบ ARAI GO GU เพื่อเรียนต่อกับพี่ริว", False),
}


def site_url(request=None) -> str:
    if settings.SITE_URL:
        return settings.SITE_URL
    return request.build_absolute_uri("/").rstrip("/") if request else ""


def absolute(request, path: str) -> str:
    return path if path.startswith("http") else site_url(request) + path


def page_meta(request, url_name: str) -> dict:
    title, description, indexable = PAGES.get(url_name, ("", DEFAULT_DESCRIPTION, False))
    path = request.path if indexable else ""
    return {
        "title": title,
        "description": description,
        "robots": "index, follow, max-image-preview:large" if indexable else "noindex, nofollow",
        "canonical": absolute(request, path) if indexable else "",
        "og_type": "website",
        "image": absolute(request, static("img/og-image.png")),
    }


def jsonld(*objects) -> str:
    """<script type="application/ld+json"> with '<' escaped so content can never close the tag."""
    graph = {"@context": "https://schema.org", "@graph": [o for o in objects if o]}
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


def organization(request) -> dict:
    base = site_url(request)
    return {
        "@type": "Organization", "@id": f"{base}/#org", "name": settings.SITE_NAME, "url": f"{base}/",
        "logo": {"@type": "ImageObject", "url": absolute(request, static("img/icons/icon-512.png")), "width": 512, "height": 512},
        "email": settings.CONTACT_EMAIL,
    }


def website(request) -> dict:
    base = site_url(request)
    return {"@type": "WebSite", "@id": f"{base}/#website", "name": settings.SITE_NAME, "url": f"{base}/",
            "inLanguage": "th", "publisher": {"@id": f"{base}/#org"}}


def web_application(request) -> dict:
    base, f = site_url(request), product_facts()
    return {
        "@type": "WebApplication", "@id": f"{base}/#app", "name": "พี่ริว AI ติวเตอร์ภาษา",
        "alternateName": settings.SITE_NAME, "url": f"{base}/",
        "applicationCategory": "EducationalApplication", "operatingSystem": "Web, Android, iOS, Windows, macOS",
        "browserRequirements": "Requires JavaScript. Installable as a Progressive Web App.",
        "inLanguage": "th", "isAccessibleForFree": True,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "THB"},
        "featureList": [
            f"แชทเรียนภาษากับ AI {f['languages']} ภาษา",
            "ตรวจไวยากรณ์พร้อมอธิบายเหตุผล", "ฝึกบทสนทนาแบบจำลองสถานการณ์",
            "ข้อสอบเสมือนจริง JLPT TOEIC HSK", "แปลและอธิบายจากรูปภาพ", "ฟังเสียงอ่านและพิมพ์ด้วยเสียง",
            f"ทดลองใช้ฟรี {f['guest_limit']} ข้อความต่อวันโดยไม่ต้องสมัคร",
        ],
        "image": absolute(request, static("img/og-image.png")),
        "publisher": {"@id": f"{base}/#org"},
    }


def faq_page(request) -> dict:
    return {
        "@type": "FAQPage", "@id": absolute(request, reverse("faq")) + "#faq",
        "mainEntity": [{"@type": "Question", "name": item["q"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["a"]}} for item in faqs()],
    }


def breadcrumbs(request, trail: list[tuple[str, str]]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": absolute(request, path)}
                            for i, (name, path) in enumerate(trail, start=1)],
    }


def article(request, guide: dict) -> dict:
    base, url = site_url(request), absolute(request, reverse("guide", args=[guide["slug"]]))
    return {
        "@type": "Article", "@id": f"{url}#article", "headline": guide["title"], "description": guide["description"],
        "abstract": guide["summary"], "inLanguage": "th", "url": url, "mainEntityOfPage": url,
        "datePublished": CONTENT_UPDATED.isoformat(), "dateModified": CONTENT_UPDATED.isoformat(),
        "author": {"@id": f"{base}/#org"}, "publisher": {"@id": f"{base}/#org"},
        "image": absolute(request, static("img/og-image.png")),
        "about": {"@type": "Thing", "name": "การเรียนภาษาต่างประเทศ"},
    }
