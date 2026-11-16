from django.db import connection
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import render


def healthz(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "db_down"}, status=503)
    return JsonResponse({"status": "ok"})


def about(request):
    """The old marketing landing page; the site itself now opens on the chat."""
    return render(request, "home.html", {"total_users": get_user_model().objects.count()})
