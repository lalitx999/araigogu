from django.urls import path

from . import views

app_name = "chat"
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.create, name="create"),
    path("send/", views.send_new, name="send_new"),
    path("guest/reset/", views.guest_reset, name="guest_reset"),
    path("action", views.action, name="action"),
    path("clear", views.clear, name="clear"),
    path("<int:pk>/", views.index, name="detail"),
    path("<int:pk>/send/", views.send, name="send"),
    path("<int:pk>/delete/", views.delete_session, name="delete"),
]
