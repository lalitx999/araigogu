import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ConsentLog, User

RL = {"post": (10, 3600), "comment": (30, 3600), "ryu": (20, 3600), "register": (5, 3600),
      "login_fail": (10, 900), "password_reset": (5, 3600)}
PW = "S3cure-pass-99"


class AuthTests(TestCase):
    def register(self, **over):
        data = {"full_name": "Somchai", "email": "Som@Example.com", "password1": PW, "password2": PW, "accept_terms": "on"}
        data.update(over)
        return self.client.post(reverse("accounts:register"), data)

    def test_register_logs_in_lowercases_email_and_records_consent(self):
        r = self.register()
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        u = User.objects.get(email="som@example.com")
        self.assertTrue(ConsentLog.objects.filter(user=u).exists())
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_register_requires_terms_unique_email_and_matching_passwords(self):
        User.objects.create_user("a@b.com", "x" * 12, full_name="A")
        self.assertEqual(self.register(email="A@b.com").status_code, 200)
        self.assertEqual(self.register(email="n@b.com", accept_terms="").status_code, 200)
        self.assertEqual(self.register(email="m@b.com", password2="different-pass-1").status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_register_page_shows_field_errors_in_original_markup(self):
        html = self.register(email="not-an-email").content.decode()
        self.assertIn('id="registerForm"', html)
        self.assertIn("is-invalid", html)
        self.assertIn('name="full_name"', html)

    def test_login_with_email_goes_to_the_chat(self):
        User.objects.create_user("a@b.com", PW, full_name="A")
        r = self.client.post(reverse("accounts:login"), {"username": "a@b.com", "password": PW, "remember": "on"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_login_without_remember_me_ends_with_browser(self):
        User.objects.create_user("a@b.com", PW, full_name="A")
        self.client.post(reverse("accounts:login"), {"username": "a@b.com", "password": PW})
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_wrong_password_shows_message(self):
        User.objects.create_user("a@b.com", PW, full_name="A")
        r = self.client.post(reverse("accounts:login"), {"username": "a@b.com", "password": "nope"})
        self.assertContains(r, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")

    def test_logout_link_works_with_get(self):
        User.objects.create_user("a@b.com", PW, full_name="A")
        self.client.login(username="a@b.com", password=PW)
        r = self.client.get(reverse("accounts:logout"))
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_private_pages_require_login(self):
        for name in ("dashboard", "community:feed", "community:search", "accounts:edit_profile"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)

    def test_home_is_the_chat_for_guests_and_members(self):
        User.objects.create_user("a@b.com", PW, full_name="A")
        r = self.client.get(reverse("home"))
        self.assertContains(r, 'data-guest="1"')
        self.assertContains(r, "ทดลองใช้ฟรี")
        self.client.login(username="a@b.com", password=PW)
        r = self.client.get(reverse("home"))
        self.assertContains(r, 'data-guest="0"')
        self.assertNotContains(r, "ทดลองใช้ฟรี")
        self.assertContains(self.client.get(reverse("about")), "Arai Go GU")  # the old landing page


class ProfileEditTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("a@b.com", PW, full_name="A")
        self.client.force_login(self.u)

    def test_edit_profile_saves_and_redirects_to_profile(self):
        r = self.client.post(reverse("accounts:edit_profile"), {"full_name": "New Name", "bio": "hi", "archetype": "B"})
        self.assertRedirects(r, reverse("community:profile", args=[self.u.pk]), fetch_redirect_response=False)
        self.u.refresh_from_db()
        self.assertEqual((self.u.full_name, self.u.bio, self.u.archetype), ("New Name", "hi", "B"))

    def test_archetype_a_is_admin_only(self):
        self.client.post(reverse("accounts:edit_profile"), {"full_name": "A", "bio": "", "archetype": "A"})
        self.u.refresh_from_db()
        self.assertEqual(self.u.archetype, "")
        self.u.is_staff = True
        self.u.save()
        self.client.post(reverse("accounts:edit_profile"), {"full_name": "A", "bio": "", "archetype": "A"})
        self.u.refresh_from_db()
        self.assertEqual(self.u.archetype, "A")

    def test_page_lists_archetypes_without_A_for_members(self):
        html = self.client.get(reverse("accounts:edit_profile")).content.decode()
        self.assertIn('data-key="B"', html)
        self.assertNotIn('data-key="A"', html)
        self.assertIn('id="archetypes-data"', html)

    def test_page_escapes_name_and_bio(self):
        self.u.full_name = "<script>alert(1)</script>"
        self.u.bio = "`; alert(1); //"
        self.u.save()
        html = self.client.get(reverse("accounts:edit_profile")).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)


@override_settings(RATE_LIMITS={**RL, "login_fail": (3, 900), "register": (2, 3600)})
class HardeningTests(TestCase):
    def test_login_locks_out_after_repeated_failures(self):
        User.objects.create_user("a@b.com", PW, full_name="A")
        bad = {"username": "a@b.com", "password": "wrong"}
        for _ in range(3):
            self.assertEqual(self.client.post(reverse("accounts:login"), bad).status_code, 200)
        self.assertEqual(self.client.post(reverse("accounts:login"), bad).status_code, 429)
        good = {"username": "a@b.com", "password": PW}
        self.assertEqual(self.client.post(reverse("accounts:login"), good).status_code, 429)

    def test_register_is_rate_limited_per_ip(self):
        for _ in range(2):
            self.client.post(reverse("accounts:register"), {"full_name": "x"})
        self.assertEqual(self.client.post(reverse("accounts:register"), {"full_name": "x"}).status_code, 429)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)


class PasswordResetTests(TestCase):
    def test_flow(self):
        User.objects.create_user("a@b.com", "Old-pass-12345", full_name="A")
        r = self.client.post(reverse("accounts:password_reset"), {"email": "a@b.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"http://testserver(\S+)", mail.outbox[0].body).group(1)
        r = self.client.get(link, follow=True)
        r = self.client.post(r.request["PATH_INFO"], {"new_password1": "Brand-new-pass-77", "new_password2": "Brand-new-pass-77"})
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))
        self.assertTrue(self.client.login(username="a@b.com", password="Brand-new-pass-77"))

    def test_unknown_email_does_not_leak(self):
        r = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@b.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_login_page_links_to_reset(self):
        self.assertContains(self.client.get(reverse("accounts:login")), reverse("accounts:password_reset"))
