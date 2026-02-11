from django.contrib import admin
from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "event_type", "user", "ip_address")
    list_filter = ("event_type",)
    readonly_fields = ("id", "timestamp", "user", "event_type", "detail", "ip_address", "user_agent")
