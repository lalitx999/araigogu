from django.db import connection
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import redirect, render


def healthz(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "db_down"}, status=503)
    return JsonResponse({"status": "ok"})


def home(request):
    if request.user.is_authenticated:  # same as the original: logged-in users go to the dashboard
        return redirect("dashboard")
    return render(request, "home.html", {"total_users": get_user_model().objects.count()})
