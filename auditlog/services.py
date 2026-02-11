"""Audit log helper – call from views to record events."""
from .models import AuditEntry


def get_client_ip(request):
    """Extract IP, respecting X-Forwarded-For from Cloudflare/nginx."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(request, event_type, user=None, detail=""):
    """Create an audit entry."""
    if user is None and hasattr(request, "user") and request.user.is_authenticated:
        user = request.user
    AuditEntry.objects.create(
        user=user if user and hasattr(user, "pk") else None,
        event_type=event_type,
        detail=str(detail),
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )
