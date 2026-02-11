from django.contrib import admin
from .models import Tenant, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "schema_name", "is_active", "created_at")
    inlines = [DomainInline]
