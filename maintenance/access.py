from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


READ_ONLY_GROUP = "Тільки перегляд"


def is_read_only(user):
    if not user.is_authenticated:
        return False
    if not hasattr(user, "_is_read_only"):
        user._is_read_only = user.groups.filter(name=READ_ONLY_GROUP).exists()
    return user._is_read_only


def readable(view):
    """Маршрут перегляду: доступний усім користувачам, що увійшли."""
    return login_required(view)


def protected(view):
    """Маршрут за замовчуванням: закритий для групи «Тільки перегляд»."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if is_read_only(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)


def access_context(request):
    return {"can_edit": not is_read_only(request.user)}
