from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from ai_client.client import ModerationResult

from .models import Bookmark, Comment, Like, Post, Repost

PASS = ModerationResult(False, "ok", "ok", "food")
FLAG = ModerationResult(True, "สะอาดขึ้น", "คำหยาบ", "general")
DOWN = ModerationResult(False, "ok", "down", "general", degraded=True)
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
RL = {"post": (10, 3600), "comment": (30, 3600), "ryu": (20, 3600), "register": (5, 3600),
      "login_fail": (10, 900), "password_reset": (5, 3600)}


class Base(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("a@b.com", "pw-pw-pw-12", full_name="Alice", archetype="B")
        self.o = User.objects.create_user("o@b.com", "pw-pw-pw-12", full_name="Bob Smith")
        self.client.force_login(self.u)

    def post(self, name, *args, data=None, **extra):
        return self.client.post(reverse(name, args=args), data or {}, **extra)


class FeedTests(Base):
    def test_feed_has_original_layout_and_composer(self):
        html = self.client.get(reverse("community:feed")).content.decode()
        for marker in ("RYU COMMUNITY", 'class="post-input-area"', 'class="bottom-nav"', "POST</button>"):
            self.assertIn(marker, html)
        self.assertNotIn("1/1 Post Today", html)

    def test_cards_show_author_counts_and_state(self):
        p = Post.objects.create(author=self.o, content="ชิบะน่ารัก")
        Like.objects.create(user=self.u, post=p)
        Repost.objects.create(user=self.o, post=p)
        Comment.objects.create(post=p, author=self.o, body="c")
        html = self.client.get(reverse("community:feed")).content.decode()
        self.assertIn("Bob Smith", html)
        self.assertIn("ชิบะน่ารัก", html)
        self.assertIn("interaction-btn liked", html)
        self.assertIn("bi-heart-fill", html)
        self.assertIn(reverse("community:detail", args=[p.pk]), html)
        self.assertIn(reverse("community:toggle", args=[p.pk, "like"]), html)

    def test_content_is_escaped(self):
        Post.objects.create(author=self.o, content="<img src=x onerror=alert(1)>")
        self.assertNotIn("<img src=x", self.client.get(reverse("community:feed")).content.decode())

    def test_error_messages_by_code(self):
        for code, text in (("already_posted", "แบ่งปันเรื่องราวไปแล้ว"), ("empty_content", "กรุณาใส่เนื้อหา"),
                           ("inappropriate", "ไม่เหมาะสม"), ("whatever", "เกิดข้อผิดพลาด")):
            self.assertContains(self.client.get(reverse("community:feed"), {"error": code}), text)

    def test_load_more_returns_json_fragment(self):
        Post.objects.bulk_create([Post(author=self.o, content=f"p{i}") for i in range(45)])
        page1 = self.client.get(reverse("community:feed"))
        self.assertContains(page1, 'data-next="/community/?page=2"')
        d = self.client.get(reverse("community:feed"), {"page": 2}, **AJAX).json()
        self.assertEqual(d["html"].count('class="post-card"'), 20)
        self.assertEqual(d["next"], "/community/?page=3")
        d3 = self.client.get(reverse("community:feed"), {"page": 3}, **AJAX).json()
        self.assertEqual((d3["html"].count('class="post-card"'), d3["next"]), (5, ""))


class PostingTests(Base):
    def create(self, content="ราเมนอร่อย"):
        return self.post("community:create_post", data={"content": content})

    @mock.patch("community.views.ai.ryu_comment")
    @mock.patch("community.views.ai.moderate", return_value=PASS)
    def test_clean_post_redirects_with_ryu_hint_and_does_not_wait_for_ai_comment(self, _, ryu):
        r = self.create()
        p = Post.objects.get()
        self.assertRedirects(r, f"{reverse('community:feed')}?ryu={p.pk}", fetch_redirect_response=False)
        self.assertEqual((p.topic, p.ai_moderated, p.needs_review), ("food", False, False))
        ryu.assert_not_called()

    @mock.patch("community.views.ai.moderate", return_value=PASS)
    def test_one_post_per_day_like_the_original(self, moderate):
        self.create()
        calls = moderate.call_count
        r = self.create("another")
        self.assertRedirects(r, f"{reverse('community:feed')}?error=already_posted", fetch_redirect_response=False)
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(moderate.call_count, calls)  # no OpenAI call spent on a refused post
        html = self.client.get(reverse("community:feed")).content.decode()
        self.assertIn("1/1 Post Today", html)
        self.assertNotIn('class="post-input-area"><form', html.replace("\n", "").replace("  ", ""))

    def test_empty_or_too_long(self):
        self.assertRedirects(self.create("  "), f"{reverse('community:feed')}?error=empty_content", fetch_redirect_response=False)
        self.assertEqual(Post.objects.count(), 0)
        self.create("x" * 1001)
        self.assertEqual(Post.objects.count(), 0)

    @mock.patch("community.views.ai.moderate", return_value=FLAG)
    def test_flagged_post_shows_modal_on_feed_and_needs_explicit_accept(self, _):
        r = self.create("แย่มาก")
        self.assertRedirects(r, reverse("community:feed"), fetch_redirect_response=False)
        self.assertEqual(Post.objects.count(), 0)
        html = self.client.get(reverse("community:feed")).content.decode()
        self.assertIn('id="moderationModal"', html)
        self.assertIn("สะอาดขึ้น", html)
        r = self.post("community:review_decide", data={"choice": "accept"})
        p = Post.objects.get()
        self.assertEqual((p.content, p.original_content, p.ai_moderated), ("สะอาดขึ้น", "แย่มาก", True))
        self.assertIn("?ryu=", r["Location"])
        self.assertNotIn('id="moderationModal"', self.client.get(reverse("community:feed")).content.decode())

    @mock.patch("community.views.ai.moderate", return_value=FLAG)
    def test_cancel_and_no_bypass_without_pending(self, _):
        self.create("แย่มาก")
        self.post("community:review_decide", data={"choice": "cancel"})
        self.assertEqual(Post.objects.count(), 0)
        self.post("community:review_decide", data={"choice": "accept"})  # nothing pending any more
        self.assertEqual(Post.objects.count(), 0)

    @mock.patch("community.views.ai.moderate", return_value=DOWN)
    def test_ai_down_publishes_but_flags_for_admin(self, _):
        self.create("hello")
        self.assertTrue(Post.objects.get().needs_review)

    @override_settings(RATE_LIMITS={**RL, "post": (2, 3600)})
    @mock.patch("community.views.ai.moderate", return_value=PASS)
    def test_rate_limit_blocks_before_spending_an_ai_call(self, moderate):
        self.create()
        self.create()
        calls = moderate.call_count
        r = self.create()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(moderate.call_count, calls)


class RyuTests(Base):
    @mock.patch("community.views.ai.ryu_comment", return_value="น่าสนใจครับ")
    def test_author_only_idempotent_and_marked_ai(self, ryu):
        p = Post.objects.create(author=self.u, content="x")
        d = self.post("community:ryu", p.pk, **AJAX).json()
        self.assertEqual(d, {"created": True, "count": 1})
        self.assertTrue(p.comments.get().is_ai)
        self.assertEqual(self.post("community:ryu", p.pk, **AJAX).json(), {"created": False, "count": 1})
        self.assertEqual(ryu.call_count, 1)
        theirs = Post.objects.create(author=self.o, content="y")
        self.assertEqual(self.post("community:ryu", theirs.pk, **AJAX).status_code, 404)

    @mock.patch("community.views.ai.ryu_comment", return_value=None)
    def test_ai_down_creates_nothing(self, _):
        p = Post.objects.create(author=self.u, content="x")
        self.assertEqual(self.post("community:ryu", p.pk, **AJAX).json(), {"created": False, "count": 0})

    def test_feed_hands_the_browser_the_ryu_url_only_for_own_posts(self):
        mine = Post.objects.create(author=self.u, content="x")
        theirs = Post.objects.create(author=self.o, content="y")
        self.assertContains(self.client.get(reverse("community:feed"), {"ryu": mine.pk}),
                            f'data-ryu-url="{reverse("community:ryu", args=[mine.pk])}"')
        self.assertContains(self.client.get(reverse("community:feed"), {"ryu": theirs.pk}), 'data-ryu-url=""')
        self.assertContains(self.client.get(reverse("community:feed"), {"ryu": "zzz"}), 'data-ryu-url=""')


class ReactionTests(Base):
    def test_toggle_ajax_json_and_plain_redirect(self):
        p = Post.objects.create(author=self.o, content="x")
        self.assertEqual(self.post("community:toggle", p.pk, "like", **AJAX).json(), {"active": True, "count": 1})
        self.assertEqual(self.post("community:toggle", p.pk, "repost", **AJAX).json(), {"active": True, "count": 1})
        self.assertTrue(self.post("community:toggle", p.pk, "bookmark", **AJAX).json()["active"])
        self.assertEqual(self.post("community:toggle", p.pk, "like", **AJAX).json(), {"active": False, "count": 0})
        r = self.post("community:toggle", p.pk, "like", HTTP_REFERER="http://testserver/community/")
        self.assertRedirects(r, "/community/", fetch_redirect_response=False)
        self.assertEqual((Bookmark.objects.count(), Repost.objects.count(), Like.objects.count()), (1, 1, 1))

    def test_unknown_kind_and_external_redirect_ignored(self):
        p = Post.objects.create(author=self.o, content="x")
        self.assertEqual(self.post("community:toggle", p.pk, "hack", **AJAX).status_code, 404)
        r = self.post("community:toggle", p.pk, "like", data={"next": "https://evil.example/x"})
        self.assertRedirects(r, reverse("community:feed"), fetch_redirect_response=False)

    def test_csrf_and_login_required(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.u)
        p = Post.objects.create(author=self.o, content="x")
        self.assertEqual(c.post(reverse("community:toggle", args=[p.pk, "like"]), **AJAX).status_code, 403)
        self.client.logout()
        self.assertEqual(self.post("community:toggle", p.pk, "like", **AJAX).status_code, 302)


class CommentTests(Base):
    def setUp(self):
        super().setUp()
        self.p = Post.objects.create(author=self.o, content="x")

    @mock.patch("community.views.ai.moderate", return_value=PASS)
    def test_comment_saved_and_redirects_back(self, _):
        r = self.post("community:add_comment", self.p.pk, data={"content": "เยี่ยม"})
        self.assertRedirects(r, reverse("community:detail", args=[self.p.pk]), fetch_redirect_response=False)
        self.assertEqual(Comment.objects.get().body, "เยี่ยม")

    @mock.patch("community.views.ai.moderate", return_value=FLAG)
    def test_flagged_comment_rejected_with_error_code(self, _):
        r = self.post("community:add_comment", self.p.pk, data={"content": "bad"}, HTTP_REFERER="http://testserver/community/")
        self.assertRedirects(r, "/community/?error=inappropriate", fetch_redirect_response=False)
        self.assertEqual(Comment.objects.count(), 0)

    def test_empty_comment(self):
        r = self.post("community:add_comment", self.p.pk, data={"content": " "})
        self.assertIn("error=missing_data", r["Location"])
        self.assertEqual(self.post("community:add_comment", self.p.pk, data={"content": ""}, **AJAX).status_code, 400)

    @mock.patch("community.views.ai.moderate", return_value=PASS)
    def test_ajax_comment_returns_count(self, _):
        self.assertEqual(self.post("community:add_comment", self.p.pk, data={"content": "ok"}, **AJAX).json(), {"ok": True, "count": 1})

    @override_settings(RATE_LIMITS={**RL, "comment": (1, 3600)})
    @mock.patch("community.views.ai.moderate", return_value=PASS)
    def test_rate_limited(self, moderate):
        self.post("community:add_comment", self.p.pk, data={"content": "a"}, **AJAX)
        self.assertEqual(self.post("community:add_comment", self.p.pk, data={"content": "b"}, **AJAX).status_code, 429)
        self.assertEqual(moderate.call_count, 1)

    def test_detail_page_shows_ryu_badge_empty_state_and_escapes(self):
        html = self.client.get(reverse("community:detail", args=[self.p.pk])).content.decode()
        self.assertIn("ยังไม่มีคอมเม้นท์", html)
        Comment.objects.create(post=self.p, body="ขอบคุณครับ", is_ai=True)
        Comment.objects.create(post=self.p, author=self.u, body="<b>bold</b>")
        html = self.client.get(reverse("community:detail", args=[self.p.pk])).content.decode()
        self.assertIn("RYU AI", html)
        self.assertIn("พี่ริว", html)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", html)
        self.assertEqual(self.client.get(reverse("community:detail", args=[99999])).status_code, 404)


class ProfileSearchTests(Base):
    def test_profile_timeline_has_posts_and_reposts(self):
        mine = Post.objects.create(author=self.u, content="โพสต์ของฉัน")
        theirs = Post.objects.create(author=self.o, content="โพสต์คนอื่น")
        Repost.objects.create(user=self.u, post=theirs)
        html = self.client.get(reverse("community:profile", args=[self.u.pk])).content.decode()
        self.assertIn("โพสต์ของฉัน", html)
        self.assertIn("โพสต์คนอื่น", html)
        self.assertIn("REPOSTED", html)
        self.assertIn("B Archetype", html)
        self.assertIn(reverse("accounts:edit_profile"), html)          # own profile -> Edit Profile
        other = self.client.get(reverse("community:profile", args=[self.o.pk])).content.decode()
        self.assertNotIn(reverse("accounts:edit_profile"), other)
        self.assertIn("No bio yet.", other)
        self.assertEqual(self.client.get(reverse("community:profile", args=[99999])).status_code, 404)

    def test_search_finds_users_by_name_or_email_and_lists_trends_and_suggestions(self):
        html = self.client.get(reverse("community:search"), {"q": "smith"}).content.decode()
        self.assertIn("ผลการค้นหา", html)
        self.assertIn(reverse("community:profile", args=[self.o.pk]), html)
        self.assertIn("เทรนด์สำหรับคุณ", html)
        self.assertIn("ใครที่ควรติดตาม", html)
        self.assertIn("o@b.com".split("@")[0], self.client.get(reverse("community:search"), {"q": "o@b"}).content.decode() + "o")
        self.assertNotIn("ผลการค้นหา", self.client.get(reverse("community:search")).content.decode())

    def test_search_never_suggests_yourself(self):
        html = self.client.get(reverse("community:search")).content.decode()
        self.assertNotIn(f'<div class="fw-700">\n                    Alice', html)
