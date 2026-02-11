"""URL configuration for tenant schemas."""
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


urlpatterns = [
    path("", lambda request: redirect("dashboard:summary")),
    path("auth/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("manage/", include("dashboard.admin_urls")),
    path("django-admin/", admin.site.urls),
]
