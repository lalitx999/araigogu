import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .content import GUIDES, faqs


def static_exists(url: str) -> bool:
    from django.contrib.staticfiles import finders
    return finders.find(url.removeprefix("/static/")) is not None


def jsonld_types(html: str) -> set[str]:
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    types = set()
    for block in blocks:
        for node in json.loads(block)["@graph"]:
            types.add(node["@type"])
    return types


@override_settings(SITE_URL="https://araigogu.test")
class SeoTests(TestCase):
    def test_public_pages_are_indexable_with_canonical_og_and_schema(self):
        cases = {
            reverse("home"): {"Organization", "WebSite", "WebApplication"},
            reverse("about"): {"Organization", "WebApplication", "BreadcrumbList"},
            reverse("faq"): {"FAQPage", "BreadcrumbList"},
            reverse("guides"): {"ItemList", "BreadcrumbList"},
            reverse("guide", args=[GUIDES[0]["slug"]]): {"Article", "BreadcrumbList"},
        }
        for url, expected in cases.items():
            html = self.client.get(url).content.decode()
            self.assertIn('<meta name="robots" content="index, follow', html, url)
            self.assertIn(f'<link rel="canonical" href="https://araigogu.test{url}">', html, url)
            self.assertIn('property="og:image" content="https://araigogu.test/static/img/og-image.png"', html, url)
            self.assertTrue(expected <= jsonld_types(html), (url, jsonld_types(html)))

    def test_private_pages_are_noindex_without_canonical(self):
        u = User.objects.create_user("a@b.com", "pw-pw-pw-12", full_name="A")
        self.client.force_login(u)
        for name in ("dashboard", "community:feed", "accounts:edit_profile"):
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn('content="noindex, nofollow"', html, name)
            self.assertNotIn('rel="canonical"', html, name)

    def test_faq_schema_matches_visible_answers(self):
        html = self.client.get(reverse("faq")).content.decode()
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
        faq = next(n for n in json.loads(block)["@graph"] if n["@type"] == "FAQPage")
        self.assertEqual(len(faq["mainEntity"]), len(faqs()))
        for item in faqs():
            self.assertIn(item["q"], html)  # every question in the schema is also on the page

    def test_jsonld_cannot_break_out_of_its_script_tag(self):
        from . import seo
        out = seo.jsonld({"@type": "Thing", "name": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script><script>", out)

    def test_unknown_guide_is_404(self):
        self.assertEqual(self.client.get(reverse("guide", args=["nope"])).status_code, 404)

    def test_robots_and_sitemap(self):
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Sitemap: https://araigogu.test/sitemap.xml", robots)
        self.assertIn("Disallow: /chat/", robots)
        self.assertIn("User-agent: GPTBot", robots)
        sitemap = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap["Content-Type"], "application/xml; charset=utf-8")
        body = sitemap.content.decode()
        for g in GUIDES:
            self.assertIn(f"https://araigogu.test/guides/{g['slug']}/", body)
        self.assertNotIn("/dashboard/", body)

    @override_settings(GUEST_DAILY_CHAT_LIMIT=7)
    def test_llms_files_list_pages_and_live_facts(self):
        short = self.client.get("/llms.txt")
        self.assertTrue(short["Content-Type"].startswith("text/markdown"))
        text = short.content.decode()
        self.assertTrue(text.startswith("# ARAI GO GU"))
        self.assertIn("7 messages a day", text)
        self.assertIn("https://araigogu.test/llms-full.txt", text)
        self.assertNotIn("&quot;", text)  # not HTML-escaped
        full = self.client.get("/llms-full.txt").content.decode()
        for g in GUIDES:
            self.assertIn(g["summary"], full)
        for item in faqs():
            self.assertIn(item["q"], full)
        self.assertEqual(self.client.get("/llm.txt").content.decode(), text)  # alias


class PwaTests(TestCase):
    def test_manifest_is_valid_json_with_icons_and_shortcuts(self):
        r = self.client.get(reverse("manifest"))
        self.assertEqual(r["Content-Type"], "application/manifest+json; charset=utf-8")
        m = json.loads(r.content)
        self.assertEqual((m["start_url"], m["scope"], m["display"]), ("/?source=pwa", "/", "standalone"))
        sizes = {(i["sizes"], i["purpose"]) for i in m["icons"]}
        self.assertTrue({("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes)
        for icon in m["icons"]:
            self.assertTrue(static_exists(icon["src"]), icon["src"])
        self.assertGreaterEqual(len(m["shortcuts"]), 3)

    def test_service_worker_is_served_from_root_and_precaches_existing_files(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r["Content-Type"], "application/javascript; charset=utf-8")
        self.assertIn("no-cache", r["Cache-Control"])
        precache = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", r.content.decode()).group(1))
        self.assertIn(reverse("offline"), precache)
        for url in precache:
            if url.startswith("/static/"):
                self.assertTrue(static_exists(url), url)
            else:
                self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_offline_page_works_without_a_session(self):
        r = self.client.get(reverse("offline"))
        self.assertContains(r, "ไม่มีการเชื่อมต่ออินเทอร์เน็ต")

    def test_every_layout_links_the_manifest(self):
        for url in (reverse("home"), reverse("about"), reverse("accounts:login"), reverse("faq")):
            self.assertContains(self.client.get(url), 'rel="manifest"', msg_prefix=url)
