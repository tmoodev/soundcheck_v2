# SoundCheck Financial – Multi-Tenant Dashboard

Replaces the existing Superset dashboard with a secure, multi-tenant Django application.
Each tenant gets complete data isolation via Postgres schema-per-tenant (`django-tenants`).

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2 + Django REST Framework |
| Multi-tenancy | django-tenants (schema-per-tenant) |
| MFA | pyotp (TOTP) – Microsoft Authenticator compatible |
| Frontend | HTMX + Tailwind CSS (CDN) |
| Database | PostgreSQL (existing analytics views) |
| Deployment | Ubuntu + systemd + nginx + Cloudflare |

## Architecture

```
Cloudflare (TLS) → nginx (reverse proxy) → gunicorn → Django
                                                        │
                                              ┌─────────┼─────────┐
                                              │         │         │
                                          tenant_a  tenant_b  tenant_c  (PG schemas)
                                              │
                                    ┌─────────┼─────────┐
                                    │         │         │
                             analytics.*   app_client  audit_log
                             (existing     (new)       (new)
                              views)
```

## Local Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- pip / virtualenv

### Steps

```bash
# 1. Clone and enter repo
cd soundcheck_v2

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment file
cp .env.example .env
# Edit .env with your local Postgres credentials
# Set DJANGO_DEBUG=True for local dev

# 5. Create the database
createdb soundcheck

# 6. Run migrations (shared schema first, then tenant schemas)
python manage.py migrate_schemas --shared

# 7. Create a test tenant
python manage.py provision_tenant \
    --name "Dev Tenant" \
    --slug dev \
    --domain dev.localhost \
    --admin-email admin@dev.local \
    --admin-password "DevP@ssw0rd123"

# 8. Add dev.localhost to /etc/hosts
echo "127.0.0.1 dev.localhost" | sudo tee -a /etc/hosts

# 9. Run the development server
python manage.py runserver

# 10. Open http://dev.localhost:8000
```

### Quick verification commands

After provisioning a tenant (for example `demo.localhost` as shown above) you can quickly
confirm routing works with curl:

```bash
# Public schema should return the landing page (HTTP 200)

# Tenant schema should redirect unauthenticated users to /auth/login/

# Login page should be reachable
curl -I http://demo.localhost:8000/auth/login/
```

If you see `404 Not Found` for the tenant URLs, ensure that:

1. `/etc/hosts` maps `demo.localhost` → `127.0.0.1`
2. The domain exists in the `Domain` table (`python manage.py shell -c "from tenants.models import Domain; print(Domain.objects.all())"`)
3. `DJANGO_ALLOWED_HOSTS` includes `.localhost` so subdomains resolve during development.

### Important: Analytics Views

The dashboard reads from existing analytics views within each tenant schema:
- `analytics.vw_superset_accounts_current`
- `analytics.vw_superset_transactions`

For local development, you need these views to exist in the tenant schema.
You can create stub views with sample data for testing.

## Production Deployment (No Docker)

### 1. Server Preparation

```bash
# Ubuntu 22.04+
sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql nginx

# Create service user
sudo useradd -m -s /bin/bash soundcheck
sudo -u soundcheck bash
```

### 2. Application Setup

```bash
cd /home/soundcheck
git clone <repo-url> soundcheck_v2
cd soundcheck_v2
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with production values:
#   DJANGO_SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
#   DJANGO_DEBUG=False
#   DATABASE_* = production credentials
#   SMTP_* = Amazon SES credentials
#   CSRF_TRUSTED_ORIGINS=https://*.soundcheckfinancial.com

# Run migrations
python manage.py migrate_schemas --shared

# Collect static files
python manage.py collectstatic --noinput
```

### 3. Systemd Service

```bash
sudo cp deploy/soundcheck.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable soundcheck
sudo systemctl start soundcheck
```

### 4. Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/soundcheck
sudo ln -s /etc/nginx/sites-available/soundcheck /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 5. DNS & Cloudflare

For each tenant:

1. **Cloudflare DNS**: Add a CNAME record:
   - Name: `<tenant-slug>` (e.g., `acme`)
   - Target: your origin server hostname or IP
   - Proxy: **Enabled** (orange cloud)

2. **Cloudflare SSL/TLS**: Set to **Full (Strict)**
   - Optionally install a Cloudflare Origin Certificate on nginx

3. **Cloudflare Wildcard**: If using many tenants, add a wildcard:
   - Name: `*`
   - Target: origin server
   - Note: Wildcard proxying requires Cloudflare paid plan

## Tenant Creation

```bash
source /home/soundcheck/soundcheck_v2/venv/bin/activate
cd /home/soundcheck/soundcheck_v2

python manage.py provision_tenant \
    --name "Acme Corporation" \
    --slug acme \
    --domain acme.soundcheckfinancial.com \
    --admin-email admin@acme.com \
    --admin-first-name "Jane" \
    --admin-last-name "Admin"
# Password will be prompted interactively
```

After creation:
1. Add DNS record in Cloudflare (CNAME: `acme` → origin)
2. The admin user must set up MFA on first login
3. Ensure the `analytics` schema with views exists in the tenant's PG schema

## Environment Variables

See `.env.example` for all variables. Key ones:

| Variable | Description | Required |
|----------|------------|----------|
| `DJANGO_SECRET_KEY` | Cryptographic secret | Yes |
| `DJANGO_DEBUG` | Debug mode (False in prod) | Yes |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames | Yes |
| `DATABASE_*` | PostgreSQL connection | Yes |
| `SMTP_*` | Email/SMTP (SES recommended) | Yes |
| `FROM_EMAIL` | Sender address | Yes |
| `CSRF_TRUSTED_ORIGINS` | CSRF protection origins | Yes |
| `MFA_REMEMBER_DEVICE_DAYS` | Days to trust a device (default 7) | No |

## Application Structure

```
soundcheck_v2/
├── soundcheck/          # Django project settings & URLs
├── tenants/             # Tenant & Domain models, management commands
├── accounts/            # User model, MFA, auth views, middleware
├── clients/             # Client & ClientAccount models
├── dashboard/           # Summary, Transactions, CSV export views
├── auditlog/            # AuditEntry model & logging service
├── templates/           # All HTML templates (HTMX + Tailwind)
├── static/              # Static assets
├── deploy/              # nginx, systemd, gunicorn configs
└── manage.py
```

## Schema Per Tenant

Each tenant's Postgres schema contains:

### Existing (analytics views – read-only)
- `analytics.vw_superset_accounts_current`
- `analytics.vw_superset_transactions`

### Created by migrations
- `app_client` – Client groupings
- `app_client_account` – Account-to-client mappings
- `audit_log` – Immutable audit trail
- `accounts_user` – Tenant-scoped users
- `accounts_trusteddevice` – MFA device trust
- `accounts_passwordresettoken` – Password reset tokens
- Django session, auth, contenttypes tables

## Security Features

| Feature | Implementation |
|---------|---------------|
| Password hashing | Argon2id (primary), PBKDF2 (fallback) |
| MFA | TOTP (RFC 6238), Microsoft Authenticator compatible |
| Recovery codes | 10 codes, SHA-256 hashed at rest, single-use |
| Remember device | 7-day cookie, SHA-256 device fingerprint |
| CSRF | Django middleware + SameSite=Lax cookies |
| Session cookies | HttpOnly, Secure, SameSite=Lax |
| Rate limiting | 10 req/min on login, 10 req/min on MFA verify, 5 req/min on password reset |
| Query safety | All SQL uses parameterized queries (%(param)s) |
| Tenant isolation | django-tenants schema routing, no cross-schema access |
| Audit trail | All auth, user, client, and export events logged |
| HSTS | 1 year, includeSubDomains, preload |

## Acceptance Checklist

### Tenant Isolation
- [ ] User on tenant A cannot see tenant B data
- [ ] Subdomain routing correctly resolves tenants
- [ ] Public schema shows landing page, not tenant data
- [ ] Each tenant has its own `app_client`, `audit_log` tables

### MFA Required
- [ ] New user is forced to MFA setup on first login
- [ ] Cannot access dashboard without completing MFA verification
- [ ] TOTP codes from Microsoft Authenticator work
- [ ] Recovery codes work and are single-use
- [ ] "Remember this device" skips MFA for 7 days
- [ ] Admin can reset a user's MFA

### Admin-Only User/Client Management
- [ ] Tenant User role cannot access /manage/* URLs
- [ ] Tenant Admin can create/disable users
- [ ] Tenant Admin can change user roles
- [ ] Tenant Admin can create/edit clients
- [ ] Tenant Admin can add/remove account mappings
- [ ] Tenant Admin can view audit log

### KPI Calculations
- [ ] Total Balance = SUM(current_balance) for filtered accounts
- [ ] Total Available = SUM(available_balance) ignoring NULLs
- [ ] Total Pending = SUM(amount_abs) WHERE pending=true, NO date filter
- [ ] Client filter correctly scopes all KPIs and accounts table
- [ ] No date range filters on summary page

### Transactions Filtering
- [ ] Default view shows last 30 days
- [ ] Client filter constrains account dropdown options
- [ ] Account filter works independently and with client filter
- [ ] Date range filter works correctly
- [ ] Pending toggle filters correctly
- [ ] Free-text search matches transaction_name and merchant_name
- [ ] Server-side pagination works
- [ ] Column sorting works (default: date desc)

### CSV Export
- [ ] Export button visible on desktop only
- [ ] Export matches current filters
- [ ] Output has correct flat columns (no JSON)
- [ ] 250,000 row cap returns clear error message
- [ ] Export events are audit-logged
- [ ] Mobile requests are rejected with 403

### Security
- [ ] Rate limiting blocks brute-force login attempts
- [ ] Password reset email works via SMTP
- [ ] Audit log captures all specified event types
- [ ] Cookies have HttpOnly, Secure, SameSite flags
- [ ] CSRF protection active on all POST requests

## Recommended Performance Indexes

See `deploy/recommended_indexes.sql` for index recommendations.
Key indexes:
- `transactions(account_id, transaction_date DESC)` – primary query path
- `transactions(pending) WHERE pending = true` – partial index for pending KPI
- Trigram indexes on `transaction_name`, `merchant_name` for ILIKE search
- `app_client_account(client_id)` and `(account_id)` – join performance

## Troubleshooting

### Tenant not resolving
- Check `Domain` table: `python manage.py shell -c "from tenants.models import Domain; print(Domain.objects.all().values_list('domain', 'tenant__slug'))"`
- Verify DNS resolves to your server
- Check `ALLOWED_HOSTS` includes the domain

### MFA not working
- Ensure server time is synchronized (NTP)
- TOTP allows ±1 window (30s tolerance)
- Check user's `mfa_secret` is set

### CSV export timeout
- Increase `proxy_read_timeout` in nginx
- Add indexes per `recommended_indexes.sql`
- Narrow date range filters
