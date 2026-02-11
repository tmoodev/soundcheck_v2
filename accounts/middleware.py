"""MFA enforcement middleware – every authenticated user must complete MFA."""
from django.shortcuts import redirect
from django.urls import reverse

# URLs that must remain accessible before MFA is completed
MFA_EXEMPT_PATHS = frozenset([
    "/auth/login/",
    "/auth/logout/",
    "/auth/mfa/setup/",
    "/auth/mfa/verify/",
    "/auth/password-reset/",
    "/auth/password-reset/confirm/",
    "/static/",
])


class MFAEnforcementMiddleware:
    """Redirect authenticated users to MFA setup/verify if not yet completed."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path
            # Allow exempt paths
            if any(path.startswith(p) for p in MFA_EXEMPT_PATHS):
                return self.get_response(request)

            # If MFA is not set up, redirect to setup
            if not request.user.mfa_enabled:
                return redirect(reverse("accounts:mfa_setup"))

            # If MFA is set up but session not verified
            if not request.session.get("mfa_verified", False):
                return redirect(reverse("accounts:mfa_verify"))

        return self.get_response(request)
