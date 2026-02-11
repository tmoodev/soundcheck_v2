"""Custom User model with MFA support for multi-tenant dashboard."""
import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.TENANT_ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Tenant-scoped user with role-based access."""

    class Role(models.TextChoices):
        TENANT_ADMIN = "admin", "Tenant Admin"
        TENANT_USER = "user", "Tenant User"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TENANT_USER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    # MFA fields
    mfa_secret = models.CharField(max_length=64, blank=True, default="")
    mfa_enabled = models.BooleanField(default=False)
    mfa_confirmed = models.BooleanField(
        default=False, help_text="True once user has verified their TOTP setup"
    )
    recovery_codes = models.JSONField(default=list, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        app_label = "accounts"

    def __str__(self):
        return self.email

    @property
    def is_tenant_admin(self):
        return self.role == self.Role.TENANT_ADMIN

    @property
    def display_name(self):
        if self.first_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.email

    def generate_recovery_codes(self, count=10):
        """Generate a fresh set of hashed recovery codes. Returns plaintext codes."""
        codes = [secrets.token_hex(4).upper() for _ in range(count)]
        self.recovery_codes = [
            hashlib.sha256(c.encode()).hexdigest() for c in codes
        ]
        self.save(update_fields=["recovery_codes"])
        return codes

    def verify_recovery_code(self, code):
        """Consume a recovery code. Returns True if valid."""
        hashed = hashlib.sha256(code.strip().upper().encode()).hexdigest()
        if hashed in self.recovery_codes:
            self.recovery_codes.remove(hashed)
            self.save(update_fields=["recovery_codes"])
            return True
        return False


class TrustedDevice(models.Model):
    """Remember MFA for a device for N days."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trusted_devices")
    device_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        app_label = "accounts"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            days = getattr(settings, "MFA_REMEMBER_DEVICE_DAYS", 7)
            self.expires_at = timezone.now() + timedelta(days=days)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return timezone.now() < self.expires_at

    @classmethod
    def make_hash(cls, user_agent, user_id):
        """Create a device fingerprint hash."""
        raw = f"{user_id}:{user_agent}"
        return hashlib.sha256(raw.encode()).hexdigest()


class PasswordResetToken(models.Model):
    """Secure password-reset tokens."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_tokens")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        app_label = "accounts"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return not self.used and (timezone.now() - self.created_at) < timedelta(hours=1)
