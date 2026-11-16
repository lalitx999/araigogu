from django.contrib import admin

from .models import Bookmark, Comment, Like, Post, Repost


@admin.action(description="ทำเครื่องหมายว่าตรวจแล้ว")
def mark_reviewed(modeladmin, request, queryset):
    queryset.update(needs_review=False)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "short", "ai_moderated", "needs_review", "created_at")
    list_filter = ("needs_review", "ai_moderated", "topic")
    search_fields = ("content", "author__email")
    actions = [mark_reviewed]

    @admin.display(description="เนื้อหา")
    def short(self, obj):
        return obj.content[:60]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "author", "is_ai", "needs_review", "created_at")
    list_filter = ("needs_review", "is_ai")
    actions = [mark_reviewed]


admin.site.register([Like, Bookmark, Repost])
