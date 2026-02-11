"""Client grouping models – tenant-scoped."""
import uuid
from django.db import models


class Client(models.Model):
    """A client within a tenant – groups accounts."""
    client_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "clients"
        db_table = "app_client"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClientAccount(models.Model):
    """Maps a client to an account_id from the analytics views."""
    id = models.BigAutoField(primary_key=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="account_mappings")
    account_id = models.TextField()

    class Meta:
        app_label = "clients"
        db_table = "app_client_account"
        unique_together = [("client", "account_id")]
        indexes = [
            models.Index(fields=["client"], name="idx_clientaccount_client"),
            models.Index(fields=["account_id"], name="idx_clientaccount_account"),
        ]

    def __str__(self):
        return f"{self.client.name} → {self.account_id}"
