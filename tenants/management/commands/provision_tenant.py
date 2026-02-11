"""
Management command to provision a new tenant.

Usage:
    python manage.py provision_tenant \\
        --name "Acme Corp" \\
        --slug acme \\
        --domain acme.soundcheckfinancial.com \\
        --admin-email admin@acme.com \\
        --admin-password "SecureP@ss123"

This will:
1. Create the tenant record + Postgres schema
2. Create the Domain record
3. Run migrations in the new schema
4. Create the initial admin user inside the tenant schema
"""
import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenants.models import Tenant, Domain


class Command(BaseCommand):
    help = "Provision a new tenant with schema, domain, and initial admin user."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Tenant display name")
        parser.add_argument("--slug", required=True, help="Subdomain slug (e.g. 'acme')")
        parser.add_argument("--domain", required=True, help="Full domain (e.g. acme.soundcheckfinancial.com)")
        parser.add_argument("--admin-email", required=True, help="Initial admin user email")
        parser.add_argument("--admin-password", required=False, help="Admin password (prompted if omitted)")
        parser.add_argument("--admin-first-name", default="Admin", help="Admin first name")
        parser.add_argument("--admin-last-name", default="User", help="Admin last name")

    def handle(self, *args, **options):
        slug = options["slug"].lower().strip()
        name = options["name"].strip()
        domain_str = options["domain"].lower().strip()
        admin_email = options["admin_email"].lower().strip()
        admin_password = options.get("admin_password")

        if not admin_password:
            admin_password = getpass.getpass("Enter admin password: ")
            confirm = getpass.getpass("Confirm admin password: ")
            if admin_password != confirm:
                raise CommandError("Passwords do not match.")

        # Validate slug
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"Tenant with slug '{slug}' already exists.")

        # Create tenant (this creates the schema and runs migrations)
        self.stdout.write(f"Creating tenant '{name}' (schema: {slug})...")
        tenant = Tenant(
            name=name,
            slug=slug,
            schema_name=slug,
        )
        tenant.save()

        # Create domain
        Domain.objects.create(domain=domain_str, tenant=tenant, is_primary=True)
        self.stdout.write(self.style.SUCCESS(f"Domain {domain_str} → schema '{slug}' created."))

        # Create admin user inside tenant schema
        connection.set_tenant(tenant)

        from accounts.models import User
        user = User.objects.create_user(
            email=admin_email,
            password=admin_password,
            first_name=options["admin_first_name"],
            last_name=options["admin_last_name"],
            role=User.Role.TENANT_ADMIN,
            is_staff=True,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Admin user {admin_email} created in tenant '{name}'.\n"
            f"\n"
            f"NEXT STEPS:\n"
            f"  1. DNS: Add a CNAME record for {slug}.soundcheckfinancial.com → your server\n"
            f"  2. Cloudflare: Ensure the subdomain is proxied (orange cloud)\n"
            f"  3. SSL: Cloudflare handles TLS termination\n"
            f"  4. The user must set up MFA on first login.\n"
        ))
