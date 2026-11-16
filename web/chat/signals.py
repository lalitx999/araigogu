from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .services import chat_service

IMPORTED_CHAT_KEY = "imported_chat_id"


@receiver(user_logged_in)
def import_trial_chat(sender, request, user, **kwargs):
    """A guest who signs up or logs in keeps the conversation they had during the free trial."""
    if request is None or not hasattr(request, "session"):
        return
    session = chat_service.import_guest_conversation(user, request.session)
    if session:
        request.session[IMPORTED_CHAT_KEY] = session.pk
