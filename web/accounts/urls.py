from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from config.ratelimit import rate_limited

from . import views
from .forms import NewPasswordForm, ResetRequestForm

app_name = "accounts"
urlpatterns = [
    path("login/", views.SignInView.as_view(), name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.sign_out, name="logout"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    # password reset (e-mail goes to the console backend unless EMAIL_* env is set)
    path("password-reset/", rate_limited("password_reset", by="ip")(auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        email_template_name="accounts/password_reset_email.txt",
        subject_template_name="accounts/password_reset_subject.txt",
        form_class=ResetRequestForm,
        success_url=reverse_lazy("accounts:password_reset_done"),
    )), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html",
        form_class=NewPasswordForm,
        success_url=reverse_lazy("accounts:password_reset_complete"),
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
