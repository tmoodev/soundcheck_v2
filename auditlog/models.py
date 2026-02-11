"""Audit log – one table per tenant schema."""
import uuid
from django.conf import settings
from django.db import models


class AuditEntry(models.Model):
    """Immutable audit trail entry."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    event_type = models.CharField(max_length=50, db_index=True)
    detail = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        app_label = "auditlog"
        db_table = "audit_log"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["event_type", "timestamp"], name="idx_audit_type_ts"),
        ]

    def __str__(self):
        return f"{self.timestamp} [{self.event_type}] {self.user}"
