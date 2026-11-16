import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .languages import LANGUAGES
from .models import ChatSession, Message

OK = {"reply": "こんにちは", "topic": "general", "degraded": False}


class Base(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("a@b.com", "pw-pw-pw-12", full_name="Alice")
        self.o = User.objects.create_user("o@b.com", "pw-pw-pw-12", full_name="O")
        self.client.force_login(self.u)
        self.s = ChatSession.objects.create(user=self.u, title="t", language="ja", difficulty="n5")

    def act(self, text="hi", session=None, action="send_message"):
        return self.client.post(reverse("chat:action"), {
            "action": action, "message": text, "session_id": (session or self.s).pk})


class DashboardTests(Base):
    def test_lists_recent_chats_with_counts_and_all_languages(self):
        Message.objects.create(session=self.s, role="user", content="x")
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(f"/chat/{self.s.pk}/", html)
        self.assertIn("1 ข้อความ", html)
        self.assertEqual(html.count('class="language-item"'), len(LANGUAGES))
        self.assertGreaterEqual(len(LANGUAGES), 100)
        self.assertIn("Alice", html)

    def test_empty_state_and_other_users_chats_hidden(self):
        ChatSession.objects.all().delete()
        ChatSession.objects.create(user=self.o, title="secret")
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("ยังไม่มีการสนทนา", html)
        self.assertNotIn("secret", html)

    def test_greeting_does_not_inject_the_name_into_script(self):
        self.u.full_name = "`;alert(1);//${x}"
        self.u.save()
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn("`;alert(1)", html.split("<script>")[-1])


class ProgressTests(Base):
    def test_streak_activity_and_language_stats(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        for days_ago in (0, 1, 2, 5):  # streak = 3 (today, yesterday, day before), day 5 breaks it
            m = Message.objects.create(session=self.s, role="user", content="x")
            Message.objects.filter(pk=m.pk).update(created_at=now - timedelta(days=days_ago))
        Message.objects.create(session=self.s, role="assistant", content="not counted")
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["streak"], 3)
        self.assertEqual(r.context["totals"], {"chats": 1, "messages": 4, "languages": 1})
        activity = r.context["activity"]
        self.assertEqual(len(activity), 7)
        self.assertEqual(sum(d["count"] for d in activity), 4)
        self.assertTrue(activity[-1]["is_today"])
        self.assertEqual(r.context["language_stats"][0]["name"], "ภาษาญี่ปุ่น")

    def test_no_activity_means_no_streak(self):
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["streak"], 0)
        self.assertContains(r, "ยังไม่มีข้อมูล")


class CreateTests(Base):
    def create(self, **data):
        return self.client.post(reverse("chat:create"), data)

    def test_create_with_title_language_goal_and_level(self):
        r = self.create(title="ฝึกอังกฤษ", language="en", difficulty="advanced", learning_goal="สอบ IELTS")
        s = ChatSession.objects.latest("pk")
        self.assertRedirects(r, reverse("chat:detail", args=[s.pk]), fetch_redirect_response=False)
        self.assertEqual((s.title, s.language, s.difficulty, s.learning_goal), ("ฝึกอังกฤษ", "en", "advanced", "สอบ IELTS"))

    def test_japanese_uses_jlpt_level(self):
        self.create(title="x", language="ja", difficulty="beginner", jp_level="n3")
        self.assertEqual(ChatSession.objects.latest("pk").difficulty, "n3")
        self.create(title="x", language="en", difficulty="beginner", jp_level="n3")  # jp_level ignored for other languages
        self.assertEqual(ChatSession.objects.latest("pk").difficulty, "beginner")

    def test_invalid_values_fall_back_and_title_defaults(self):
        self.create(title=" ", language="zz", difficulty="godmode")
        s = ChatSession.objects.latest("pk")
        self.assertEqual((s.language, s.difficulty), ("ja", "beginner"))
        self.assertTrue(s.title.startswith("แชทกับพี่ริว - "))

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("chat:create")).status_code, 405)


class PageTests(Base):
    def test_open_by_query_string_like_the_original_links(self):
        Message.objects.create(session=self.s, role="user", content="สวัสดี")
        Message.objects.create(session=self.s, role="assistant", content="ยินดีครับ")
        for url in (f"{reverse('chat:index')}?session={self.s.pk}", reverse("chat:detail", args=[self.s.pk])):
            html = self.client.get(url).content.decode()
            self.assertIn("สวัสดี", html)
            self.assertIn("ยินดีครับ", html)
            self.assertIn('data-session-id="%d"' % self.s.pk, html)

    def test_no_session_shows_welcome_and_garbage_param_is_ignored(self):
        html = self.client.get(reverse("chat:index") + "?session=abc").content.decode()
        self.assertIn('id="welcome"', html)
        self.assertNotIn('id="welcome" hidden', html)

    def test_other_users_session_is_404(self):
        other = ChatSession.objects.create(user=self.o, title="x")
        self.assertEqual(self.client.get(reverse("chat:detail", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get(f"{reverse('chat:index')}?session={other.pk}").status_code, 404)

    def test_history_is_html_escaped_and_title_not_injected_into_script(self):
        self.s.title = "</script><script>alert(1)</script>"
        self.s.save()
        Message.objects.create(session=self.s, role="assistant", content="<img src=x onerror=alert(1)>")
        html = self.client.get(reverse("chat:detail", args=[self.s.pk])).content.decode()
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertIn("js/chat_app.js", html)
        from django.contrib.staticfiles import finders
        with open(finders.find("js/chat_app.js"), encoding="utf-8") as f:
            self.assertIn("function escapeHtml", f.read())  # the client-side renderer escapes too


class ActionTests(Base):
    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_send_message_saves_both_sides_and_passes_context(self, chat):
        self.s.learning_goal = "สอบ N3"
        self.s.save()
        self.act("one")
        r = self.act("two")
        self.assertEqual(r.json(), {"success": True, "ai_response": "こんにちは"})
        self.assertEqual(self.s.messages.count(), 4)
        args, kwargs = chat.call_args
        self.assertEqual([m["role"] for m in args[3]], ["user", "assistant"])
        self.assertEqual((kwargs["language_name"], kwargs["learning_goal"]), ("ภาษาญี่ปุ่น", "สอบ N3"))

    @mock.patch("ai_client.client.chat", return_value={"reply": "down", "topic": "general", "degraded": True})
    def test_ai_down_persists_nothing(self, _):
        r = self.act()
        self.assertFalse(r.json()["success"])
        self.assertEqual(self.s.messages.count(), 0)

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_cannot_use_someone_elses_session_or_bad_input(self, chat):
        other = ChatSession.objects.create(user=self.o, title="x")
        self.assertEqual(self.act(session=other).json(), {"success": False, "error": "session_not_found"})
        self.assertEqual(self.act(action="drop_tables").json()["error"], "invalid_action")
        self.assertFalse(self.act("   ").json()["success"])
        self.assertFalse(self.act("x" * 2001).json()["success"])
        chat.assert_not_called()

    @override_settings(AI_DAILY_CHAT_LIMIT=1)
    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_daily_limit_has_a_thai_message(self, chat):
        self.assertTrue(self.act().json()["success"])
        r = self.act().json()
        self.assertFalse(r["success"])
        self.assertIn("โควตา", r["error"])
        self.assertEqual(chat.call_count, 1)

    def test_csrf_is_enforced(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.u)
        self.assertEqual(c.post(reverse("chat:action"), {"action": "send_message"}).status_code, 403)

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_json_endpoint_still_works(self, _):
        r = self.client.post(reverse("chat:send", args=[self.s.pk]), json.dumps({"message": "hi"}), content_type="application/json")
        self.assertEqual(r.json()["reply"], "こんにちは")


class ClearTests(Base):
    def clear(self, session):
        return self.client.post(reverse("chat:clear"), json.dumps({"session_id": session.pk}), content_type="application/json")

    def test_clear_deletes_own_messages_only(self):
        Message.objects.create(session=self.s, role="user", content="x")
        other = ChatSession.objects.create(user=self.o, title="x")
        Message.objects.create(session=other, role="user", content="keep")
        self.assertTrue(self.clear(self.s).json()["success"])
        self.assertEqual(self.s.messages.count(), 0)
        self.assertEqual(self.clear(other).status_code, 404)
        self.assertEqual(other.messages.count(), 1)

    def test_bad_payload_and_get(self):
        self.assertEqual(self.client.post(reverse("chat:clear"), "nope", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get(reverse("chat:clear")).status_code, 405)


@override_settings(GUEST_DAILY_CHAT_LIMIT=3, GUEST_DAILY_IP_LIMIT=5)
class GuestTrialTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def send(self, text="hi", client=None, **extra):
        return (client or self.client).post(reverse("chat:send_new"), {"message": text, **extra})

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_guest_can_chat_without_an_account_and_nothing_is_saved(self, chat):
        r = self.send("สวัสดี", language="en", difficulty="advanced")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["quota"], {"used": 1, "limit": 3, "remaining": 2})
        self.assertNotIn("session", r.json())
        self.assertEqual(ChatSession.objects.count(), 0)
        args, kwargs = chat.call_args
        self.assertEqual((args[1], args[2], kwargs["model_provider"]), ("en", "advanced", "groq"))
        # the conversation survives a reload and is sent back as history
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("สวัสดี", html)
        self.assertIn('data-locked="1"', html)
        self.send("again", language="ja")
        args, _ = chat.call_args
        self.assertEqual(args[1], "en")  # language is fixed once the trial chat started
        self.assertEqual([m["role"] for m in args[3]], ["user", "assistant"])

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_limit_per_day_then_sign_up_prompt(self, chat):
        for _ in range(3):
            self.assertEqual(self.send().status_code, 200)
        r = self.send()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["error"], "guest_limit")
        self.assertEqual(chat.call_count, 3)
        html = self.client.get(reverse("home")).content.decode()
        self.assertNotIn('id="limitPanel" hidden', html)  # sign-up panel shown
        self.assertIn('id="composer" hidden', html)

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_new_chat_does_not_reset_the_quota_and_ip_cap_blocks_cookie_clearing(self, chat):
        from django.test import Client
        for _ in range(3):
            self.send()
        self.client.post(reverse("chat:guest_reset"))
        self.assertEqual(self.send().status_code, 429)
        fresh = Client()  # same IP, new cookies
        self.assertEqual(self.send(client=fresh).status_code, 200)
        self.assertEqual(self.send(client=fresh).status_code, 200)
        self.assertEqual(self.send(client=Client()).status_code, 429)  # IP cap (5) reached

    @mock.patch("ai_client.client.chat", return_value={"reply": "down", "topic": "general", "degraded": True})
    def test_ai_down_does_not_use_the_quota(self, _):
        self.assertEqual(self.send().status_code, 503)
        r = self.client.get(reverse("home"))
        self.assertEqual(r.context["quota"].used, 0)

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_images_and_saved_chats_need_an_account(self, chat):
        from django.core.files.uploadedfile import SimpleUploadedFile
        img = SimpleUploadedFile("a.png", b"\x89PNG....", content_type="image/png")
        r = self.send("ดูรูปนี้", image=img)
        self.assertEqual((r.status_code, r.json()["error"]), (403, "login_required"))
        chat.assert_not_called()
        self.assertEqual(self.client.get(reverse("chat:detail", args=[1])).status_code, 302)
        self.assertEqual(self.client.post(reverse("chat:send", args=[1]), {"message": "x"}).status_code, 302)

    def test_csrf_is_enforced_for_guests(self):
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse("chat:send_new"), {"message": "x"}).status_code, 403)

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_trial_conversation_moves_into_the_new_account(self, _):
        self.send("อยากเรียนภาษาอังกฤษ", language="en", difficulty="beginner")
        r = self.client.post(reverse("accounts:register"), {
            "full_name": "New", "email": "new@b.com", "password1": "pw-pw-pw-12345",
            "password2": "pw-pw-pw-12345", "accept_terms": "on"})
        self.assertRedirects(r, reverse("home"), fetch_redirect_response=False)
        session = ChatSession.objects.get(user__email="new@b.com")
        self.assertEqual((session.title, session.language), ("อยากเรียนภาษาอังกฤษ", "en"))
        self.assertEqual(list(session.messages.values_list("role", flat=True)), ["user", "assistant"])
        # landing on the chat opens the imported conversation once
        self.assertRedirects(self.client.get(reverse("home")), reverse("chat:detail", args=[session.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)


class MemberNewChatTests(Base):
    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_first_message_creates_the_chat(self, chat):
        r = self.client.post(reverse("chat:send_new"), {"message": "Hello there\nsecond line",
                                                         "language": "ko", "difficulty": "intermediate"})
        data = r.json()
        self.assertTrue(data["session"]["created"])
        s = ChatSession.objects.get(pk=data["session"]["id"], user=self.u)
        self.assertEqual((s.title, s.language, s.difficulty), ("Hello there", "ko", "intermediate"))
        self.assertEqual(data["session"]["url"], reverse("chat:detail", args=[s.pk]))
        self.assertEqual(s.messages.count(), 2)

    @mock.patch("ai_client.client.chat", return_value={"reply": "down", "topic": "general", "degraded": True})
    def test_no_empty_chat_when_ai_is_down(self, _):
        before = ChatSession.objects.count()
        self.assertEqual(self.client.post(reverse("chat:send_new"), {"message": "hi"}).status_code, 503)
        self.assertEqual(ChatSession.objects.count(), before)

    @mock.patch("ai_client.client.chat", return_value=OK)
    def test_bad_language_and_level_fall_back(self, chat):
        self.client.post(reverse("chat:send_new"), {"message": "hi", "language": "xx", "difficulty": "god"})
        args, _ = chat.call_args
        self.assertEqual((args[1], args[2]), ("ja", "n5"))

    def test_page_has_no_emoji(self):
        import re
        html = self.client.get(reverse("home")).content.decode()
        self.assertIsNone(re.search("[\U0001F000-\U0001FAFF☀-➿]", html))
