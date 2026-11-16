from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ConsentLog, User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "archetype", "is_staff", "date_joined")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("โปรไฟล์", {"fields": ("full_name", "bio", "archetype")}),
        ("สิทธิ์", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("วันที่", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),)


admin.site.register(ConsentLog)
