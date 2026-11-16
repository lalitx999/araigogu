from django.contrib import admin

from .models import ChatSession, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "topic", "created_at")
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "language", "difficulty", "updated_at")
    list_filter = ("language", "difficulty")
    search_fields = ("user__email", "title")
    inlines = [MessageInline]
