from django.contrib import admin
from django.urls import include, path

from chat.views import dashboard

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("dashboard/", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("chat/", include("chat.urls")),
    path("community/", include("community.urls")),
]
