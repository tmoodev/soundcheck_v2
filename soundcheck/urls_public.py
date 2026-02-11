"""URL configuration for the public schema (no tenant).
Displays a simple landing/error page.
"""
from django.http import HttpResponse
from django.urls import path


def public_landing(request):
    return HttpResponse(
        "<h1>SoundCheck Financial</h1>"
        "<p>Please access your tenant dashboard via your organization's subdomain.</p>",
        content_type="text/html",
    )


urlpatterns = [
    path("", public_landing),
]
