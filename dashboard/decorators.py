"""Access control decorators."""
from functools import wraps
from django.http import HttpResponseForbidden


def tenant_admin_required(view_func):
    """Restrict view to tenant admins only."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_tenant_admin:
            return HttpResponseForbidden("Access denied. Tenant admin privileges required.")
        return view_func(request, *args, **kwargs)
    return _wrapped
