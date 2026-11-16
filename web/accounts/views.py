from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from config.ratelimit import client_ip, is_limited, rate_limited, record, too_many

from .archetypes import ARCHETYPE_DATA
from .forms import LoginForm, ProfileForm, RegisterForm
from .models import ConsentLog


class SignInView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if is_limited("login_fail", client_ip(request)):
            return too_many(request)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        record("login_fail", client_ip(self.request))
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)  # "remember me" unticked -> session ends with the browser
        return response


def sign_out(request):
    """Plain link in the original design, so GET is accepted as well as POST."""
    logout(request)
    return redirect("accounts:login")


@rate_limited("register", by="ip")
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        ConsentLog.objects.create(user=user, ip_address=client_ip(request))
        login(request, user)
        return redirect("dashboard")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def edit_profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("community:profile", user_id=request.user.pk)
    visible = {k: v for k, v in ARCHETYPE_DATA.items() if k != "A" or request.user.is_staff}
    return render(request, "accounts/edit_profile.html", {
        "form": form,
        "profile": request.user,
        "archetypes": [{"key": k, **v, "icon": f"img/archetypes/{k}.jpg"} for k, v in visible.items()],
        "archetypes_map": visible,
    })
