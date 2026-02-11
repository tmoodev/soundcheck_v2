"""Tenant Admin views – user management, client management, audit log."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods

from accounts.forms import UserCreateForm, UserEditForm
from accounts.models import User
from auditlog.models import AuditEntry
from auditlog.services import log_event
from clients.forms import ClientForm, ClientAccountMappingForm
from clients.models import Client, ClientAccount
from .decorators import tenant_admin_required


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
def user_list_view(request):
    users = User.objects.all().order_by("email")
    return render(request, "admin_panel/user_list.html", {
        "users": users,
        "page_title": "Manage Users",
        "active_page": "users",
    })


@login_required
@tenant_admin_required
@require_http_methods(["GET", "POST"])
def user_create_view(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            log_event(request, "user_created", detail=f"Created user {user.email} with role {user.role}")
            messages.success(request, f"User {user.email} created.")
            return redirect("admin_panel:user_list")
    else:
        form = UserCreateForm()
    return render(request, "admin_panel/user_form.html", {
        "form": form,
        "page_title": "Create User",
        "active_page": "users",
    })


@login_required
@tenant_admin_required
@require_http_methods(["GET", "POST"])
def user_edit_view(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    old_role = user.role
    old_active = user.is_active

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            changes = []
            if old_role != user.role:
                changes.append(f"role: {old_role} → {user.role}")
            if old_active != user.is_active:
                changes.append(f"active: {old_active} → {user.is_active}")
            if changes:
                log_event(request, "user_updated", detail=f"Updated {user.email}: {', '.join(changes)}")
            messages.success(request, f"User {user.email} updated.")
            return redirect("admin_panel:user_list")
    else:
        form = UserEditForm(instance=user)

    return render(request, "admin_panel/user_form.html", {
        "form": form,
        "edit_user": user,
        "page_title": f"Edit User – {user.email}",
        "active_page": "users",
    })


@login_required
@tenant_admin_required
@require_http_methods(["POST"])
def user_reset_mfa_view(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    user.mfa_enabled = False
    user.mfa_confirmed = False
    user.mfa_secret = ""
    user.recovery_codes = []
    user.save(update_fields=["mfa_enabled", "mfa_confirmed", "mfa_secret", "recovery_codes"])
    user.trusted_devices.all().delete()
    log_event(request, "mfa_reset", user=user, detail=f"MFA reset for {user.email}")
    messages.success(request, f"MFA has been reset for {user.email}. They must set up MFA again.")
    return redirect("admin_panel:user_list")


@login_required
@tenant_admin_required
@require_http_methods(["POST"])
def user_regen_recovery_view(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    codes = user.generate_recovery_codes()
    log_event(request, "recovery_codes_regenerated", user=user,
              detail=f"Recovery codes regenerated for {user.email}")
    return render(request, "admin_panel/recovery_codes.html", {
        "target_user": user,
        "recovery_codes": codes,
        "page_title": f"Recovery Codes – {user.email}",
        "active_page": "users",
    })


# ---------------------------------------------------------------------------
# Client Management
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
def client_list_view(request):
    clients = Client.objects.all()
    return render(request, "admin_panel/client_list.html", {
        "clients": clients,
        "page_title": "Manage Clients",
        "active_page": "clients",
    })


@login_required
@tenant_admin_required
@require_http_methods(["GET", "POST"])
def client_create_view(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            log_event(request, "client_created", detail=f"Created client '{client.name}'")
            messages.success(request, f"Client '{client.name}' created.")
            return redirect("admin_panel:client_list")
    else:
        form = ClientForm()
    return render(request, "admin_panel/client_form.html", {
        "form": form,
        "page_title": "Create Client",
        "active_page": "clients",
    })


@login_required
@tenant_admin_required
@require_http_methods(["GET", "POST"])
def client_edit_view(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            log_event(request, "client_updated", detail=f"Updated client '{client.name}'")
            messages.success(request, f"Client '{client.name}' updated.")
            return redirect("admin_panel:client_list")
    else:
        form = ClientForm(instance=client)

    mappings = ClientAccount.objects.filter(client=client).order_by("account_id")

    return render(request, "admin_panel/client_form.html", {
        "form": form,
        "client": client,
        "mappings": mappings,
        "page_title": f"Edit Client – {client.name}",
        "active_page": "clients",
    })


@login_required
@tenant_admin_required
@require_http_methods(["GET", "POST"])
def client_mappings_view(request, client_id):
    client = get_object_or_404(Client, pk=client_id)

    if request.method == "POST":
        form = ClientAccountMappingForm(request.POST)
        if form.is_valid():
            new_ids = form.cleaned_data["account_ids"]
            created = 0
            for aid in new_ids:
                _, was_created = ClientAccount.objects.get_or_create(client=client, account_id=aid)
                if was_created:
                    created += 1
            log_event(request, "client_accounts_added",
                      detail=f"Added {created} account(s) to client '{client.name}'")
            messages.success(request, f"Added {created} account mapping(s).")
            return redirect("admin_panel:client_edit", client_id=client.pk)
    else:
        form = ClientAccountMappingForm()

    return render(request, "admin_panel/client_mappings.html", {
        "form": form,
        "client": client,
        "page_title": f"Add Accounts – {client.name}",
        "active_page": "clients",
    })


@login_required
@tenant_admin_required
@require_http_methods(["POST"])
def client_mapping_delete_view(request, client_id, mapping_id):
    mapping = get_object_or_404(ClientAccount, pk=mapping_id, client_id=client_id)
    account_id = mapping.account_id
    client_name = mapping.client.name
    mapping.delete()
    log_event(request, "client_account_removed",
              detail=f"Removed account {account_id} from client '{client_name}'")
    messages.success(request, f"Removed account mapping {account_id}.")
    return redirect("admin_panel:client_edit", client_id=client_id)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------
@login_required
@tenant_admin_required
def audit_log_view(request):
    entries = AuditEntry.objects.select_related("user").order_by("-timestamp")[:500]
    return render(request, "admin_panel/audit_log.html", {
        "entries": entries,
        "page_title": "Audit Log",
        "active_page": "audit",
    })
