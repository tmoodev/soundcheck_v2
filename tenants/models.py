"""Tenant models for django-tenants schema-per-tenant isolation."""
import uuid
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    """Each tenant maps to one Postgres schema."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Display name for the tenant org")
    slug = models.SlugField(max_length=63, unique=True, help_text="Subdomain slug")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    auto_create_schema = True

    class Meta:
        app_label = "tenants"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """Domain → tenant mapping. Primary domain used for routing."""

    class Meta:
        app_label = "tenants"

    def __str__(self):
        return self.domain
