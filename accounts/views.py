"""Authentication views: login, MFA, password reset."""
import io
import base64
import pyotp
import qrcode
import qrcode.image.svg

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from django_ratelimit.decorators import ratelimit

from auditlog.services import log_event
from .forms import (
    LoginForm, MFAVerifyForm, MFASetupForm,
    PasswordResetRequestForm, PasswordResetConfirmForm,
)
from .models import User, TrustedDevice, PasswordResetToken


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            log_event(request, "login_success", user=user)

            # Check for trusted device
            if user.mfa_enabled and user.mfa_confirmed:
                device_hash = TrustedDevice.make_hash(
                    request.META.get("HTTP_USER_AGENT", ""), str(user.id)
                )
                trusted = TrustedDevice.objects.filter(
                    user=user, device_hash=device_hash, expires_at__gt=timezone.now()
                ).first()
                if trusted:
                    request.session["mfa_verified"] = True
                    return redirect(settings.LOGIN_REDIRECT_URL)

            return redirect(settings.LOGIN_REDIRECT_URL)
        else:
            # Log failed attempt
            email = request.POST.get("email", "")
            log_event(request, "login_failure", detail=f"Failed login for {email}")
    else:
        form = LoginForm()
    return render(request, "registration/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("accounts:login")
    return render(request, "registration/logout_confirm.html")


# ---------------------------------------------------------------------------
# MFA Setup
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def mfa_setup_view(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    user = request.user
    # Generate secret if not present
    if not user.mfa_secret:
        user.mfa_secret = pyotp.random_base32()
        user.save(update_fields=["mfa_secret"])

    totp = pyotp.TOTP(user.mfa_secret)
    issuer = "SoundCheckFinancial"
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name=issuer)

    # Generate QR code as base64 PNG
    img = qrcode.make(provisioning_uri, image_factory=qrcode.image.pil.PilImage)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    recovery_codes = None

    if request.method == "POST":
        form = MFASetupForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            if totp.verify(code, valid_window=1):
                user.mfa_enabled = True
                user.mfa_confirmed = True
                user.save(update_fields=["mfa_enabled", "mfa_confirmed"])
                recovery_codes = user.generate_recovery_codes()
                request.session["mfa_verified"] = True
                log_event(request, "mfa_setup_complete", user=user)
                return render(request, "registration/mfa_recovery_codes.html", {
                    "recovery_codes": recovery_codes,
                })
            else:
                form.add_error("code", "Invalid code. Please try again.")
    else:
        form = MFASetupForm()

    return render(request, "registration/mfa_setup.html", {
        "form": form,
        "qr_b64": qr_b64,
        "secret": user.mfa_secret,
    })


# ---------------------------------------------------------------------------
# MFA Verify
# ---------------------------------------------------------------------------
@ratelimit(key="user", rate="10/m", method="POST", block=True)
@require_http_methods(["GET", "POST"])
def mfa_verify_view(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    if request.session.get("mfa_verified"):
        return redirect(settings.LOGIN_REDIRECT_URL)

    user = request.user
    if not user.mfa_enabled:
        return redirect("accounts:mfa_setup")

    if request.method == "POST":
        form = MFAVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"].strip()
            totp = pyotp.TOTP(user.mfa_secret)

            valid = False
            used_recovery = False

            # Try TOTP first (6 digits)
            if code.isdigit() and len(code) == 6:
                valid = totp.verify(code, valid_window=1)
            else:
                # Try recovery code
                valid = user.verify_recovery_code(code)
                used_recovery = True

            if valid:
                request.session["mfa_verified"] = True
                log_event(request, "mfa_verify_success", user=user,
                          detail="recovery_code" if used_recovery else "totp")

                # Remember device if requested
                if form.cleaned_data.get("remember_device"):
                    device_hash = TrustedDevice.make_hash(
                        request.META.get("HTTP_USER_AGENT", ""), str(user.id)
                    )
                    TrustedDevice.objects.create(user=user, device_hash=device_hash)

                return redirect(settings.LOGIN_REDIRECT_URL)
            else:
                log_event(request, "mfa_verify_failure", user=user)
                form.add_error("code", "Invalid code. Please try again.")
    else:
        form = MFAVerifyForm()

    return render(request, "registration/mfa_verify.html", {"form": form})


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@require_http_methods(["GET", "POST"])
def password_reset_request_view(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            try:
                user = User.objects.get(email=email, is_active=True)
                token_obj = PasswordResetToken(user=user)
                token_obj.save()
                # Send email
                _send_reset_email(request, user, token_obj.token)
            except User.DoesNotExist:
                pass  # Do not reveal whether email exists
            messages.success(request, "If an account exists with that email, a reset link has been sent.")
            return redirect("accounts:login")
    else:
        form = PasswordResetRequestForm()
    return render(request, "registration/password_reset_request.html", {"form": form})


@require_http_methods(["GET", "POST"])
def password_reset_confirm_view(request, token):
    token_obj = get_object_or_404(PasswordResetToken, token=token)
    if not token_obj.is_valid:
        messages.error(request, "This reset link has expired or already been used.")
        return redirect("accounts:login")

    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            user = token_obj.user
            user.set_password(form.cleaned_data["password"])
            user.save(update_fields=["password"])
            token_obj.used = True
            token_obj.save(update_fields=["used"])
            log_event(request, "password_reset_complete", user=user)
            messages.success(request, "Password has been reset. Please log in.")
            return redirect("accounts:login")
    else:
        form = PasswordResetConfirmForm()

    return render(request, "registration/password_reset_confirm.html", {"form": form, "token": token})


def _send_reset_email(request, user, token):
    """Send password reset email via configured SMTP."""
    from django.core.mail import send_mail

    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    link = f"{scheme}://{host}/auth/password-reset/confirm/{token}/"
    send_mail(
        subject="SoundCheck Financial – Password Reset",
        message=(
            f"Hi {user.display_name},\n\n"
            f"Click the link below to reset your password:\n{link}\n\n"
            f"This link expires in 1 hour.\n\n"
            f"If you didn't request this, ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
