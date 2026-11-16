from django.conf import settings
from django.db import models

TOPICS = [
    "general", "japanese", "food", "travel", "education",
    "pet", "entertainment", "technology", "health", "question",
]


class Post(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts")
    content = models.TextField(max_length=1000)
    original_content = models.TextField(blank=True, help_text="ข้อความเดิมก่อน AI แก้ไข")
    ai_moderated = models.BooleanField(default=False)
    needs_review = models.BooleanField(default=False, help_text="AI ตรวจไม่ได้ ให้แอดมินตรวจ")
    topic = models.CharField(max_length=40, default="general")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.content[:40]}"


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                               related_name="comments")
    body = models.CharField(max_length=500)
    is_ai = models.BooleanField(default=False)  # P'Ryu; author is NULL
    needs_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def avatar_url(self):
        from django.templatetags.static import static
        return self.author.avatar_url if self.author else static("img/Ryupro.png")

    @property
    def display_name(self):
        return "พี่ริว" if self.is_ai or not self.author else self.author.full_name


class _UserPost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="uniq_%(class)s_user_post")]


class Like(_UserPost):
    pass


class Bookmark(_UserPost):
    pass


class Repost(_UserPost):
    pass
