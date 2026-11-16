from django.urls import path

from . import views

app_name = "community"
urlpatterns = [
    path("", views.feed, name="feed"),
    path("search/", views.search, name="search"),
    path("post/new/", views.create_post, name="create_post"),
    path("post/review/decide/", views.review_decide, name="review_decide"),
    path("post/<int:pk>/", views.post_detail, name="detail"),
    path("post/<int:pk>/comment/", views.add_comment, name="add_comment"),
    path("post/<int:pk>/ryu/", views.ryu, name="ryu"),
    path("post/<int:pk>/<str:kind>/", views.toggle, name="toggle"),
    path("user/<int:user_id>/", views.profile, name="profile"),
]
