from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from chat.views import dashboard, index as chat_home

from . import views

urlpatterns = [
    path("", chat_home, name="home"),  # open the site, land in the chat
    path("", include("public.urls")),
    path("healthz", views.healthz, name="healthz"),
    path("dashboard/", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("chat/", include("chat.urls")),
    path("community/", include("community.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
