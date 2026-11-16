import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class NoCdnTests(TestCase):
    # tipme.in.th is the donation page the original linked to (a hyperlink + QR payload, never a loaded asset)
    URL = re.compile(r"""(?:https?:)?//(?!localhost|127\.0\.0\.1|tipme\.in\.th)[\w.-]+\.[a-z]{2,}""", re.I)

    def test_no_external_urls_in_templates_or_own_static(self):
        base = Path(settings.BASE_DIR)
        files = [*base.glob("templates/**/*.html"), *base.glob("templates/**/*.txt"),
                 *base.glob("static/css/**/*.css"), *base.glob("static/js/**/*.js")]
        self.assertTrue(files)
        offenders = []
        for f in files:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if self.URL.search(line):
                    offenders.append(f"{f.relative_to(base)}:{n}: {line.strip()[:80]}")
        self.assertEqual(offenders, [])

    def test_bootstrap_is_served_locally(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("/static/vendor/bootstrap/css/bootstrap.min.css", html)
        self.assertIn("/static/vendor/bootstrap/js/bootstrap.bundle.min.js", html)
        self.assertTrue((Path(settings.BASE_DIR) / "static/vendor/bootstrap/js/bootstrap.bundle.min.js").exists())

    def test_csp_header_blocks_third_parties(self):
        csp = self.client.get(reverse("home"))["Content-Security-Policy"]
        for directive in ("default-src 'self'", "script-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline'", "font-src 'self'",
                          "connect-src 'self'", "object-src 'none'"):
            self.assertIn(directive, csp)
        self.assertNotIn("http", csp)
        self.assertNotIn("Content-Security-Policy", self.client.get("/admin/login/"))


class HealthTests(TestCase):
    def test_healthz(self):
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})


class LocalAssetsTests(TestCase):
    """Every /static/ file a rendered page points at must exist (nothing falls back to a CDN)."""

    def test_all_referenced_static_files_exist_on_every_page(self):
        from django.contrib.staticfiles import finders
        from accounts.models import User
        from chat.models import ChatSession
        from community.models import Post

        user = User.objects.create_user("a@b.com", "pw-pw-pw-12", full_name="A", archetype="B")
        session = ChatSession.objects.create(user=user, title="t", language="ja", difficulty="n5")
        post = Post.objects.create(author=user, content="hello")
        public = ["home", "accounts:login", "accounts:register", "accounts:password_reset"]
        private = [reverse("dashboard"), reverse("chat:index"), reverse("chat:detail", args=[session.pk]),
                   reverse("community:feed"), reverse("community:detail", args=[post.pk]),
                   reverse("community:profile", args=[user.pk]), reverse("community:search") + "?q=a",
                   reverse("accounts:edit_profile")]
        pages = [reverse(n) for n in public]
        checked = 0
        for authed, urls in ((False, pages), (True, private)):
            self.client.logout()
            if authed:
                self.client.force_login(user)
            for url in urls:
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, url)
                for ref in set(re.findall(r"""(?:src|href)=["'](/static/[^"'?#]+)""", r.content.decode())):
                    self.assertIsNotNone(finders.find(ref[len("/static/"):]), f"{url} -> missing {ref}")
                    checked += 1
        self.assertGreater(checked, 40)
