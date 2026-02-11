"""Global template context processors."""
from django.conf import settings


def global_context(request):
    """Inject global context into all templates."""
    tenant = getattr(request, "tenant", None)
    return {
        "tenant_name": tenant.name if tenant else "SoundCheck Financial",
        "debug": settings.DEBUG,
    }
