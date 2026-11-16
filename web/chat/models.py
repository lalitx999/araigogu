from django.conf import settings
from django.db import models

from .languages import LANGUAGE_NAMES


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=255)
    language = models.CharField(max_length=10, default="en")
    difficulty = models.CharField(max_length=20, default="beginner")  # beginner/intermediate/advanced or n5..n1
    learning_goal = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    @property
    def language_name(self):
        return LANGUAGE_NAMES.get(self.language, self.language)


class Message(models.Model):
    ROLES = [("user", "user"), ("assistant", "assistant")]
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLES)
    content = models.TextField()
    topic = models.CharField(max_length=40, blank=True)
    image = models.FileField(upload_to="chat_attachments/%Y/%m/", blank=True, null=True)
    model_provider = models.CharField(max_length=30, blank=True, default="")
    model_name = models.CharField(max_length=60, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["role", "created_at"])]

    @property
    def has_image(self):
        return bool(self.image)

    @property
    def image_url(self):
        return self.image.url if self.image else ""
