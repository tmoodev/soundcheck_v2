"""Dashboard views – Summary and Transactions pages."""
import csv
import io
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from auditlog.services import log_event
from clients.models import Client
from . import queries


def _parse_int(value, default, minimum=1, maximum=None):
    try:
        v = int(value)
        v = max(v, minimum)
        if maximum:
            v = min(v, maximum)
        return v
    except (TypeError, ValueError):
        return default


def _is_mobile(request):
    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    return any(kw in ua for kw in ("mobile", "android", "iphone", "ipad"))


# ---------------------------------------------------------------------------
# Summary Page
# ---------------------------------------------------------------------------
@login_required
@require_GET
def summary_view(request):
    """Main summary page with KPIs and accounts table."""
    clients = Client.objects.filter(active=True)
    client_id = request.GET.get("client_id", "")

    # KPIs
    kpis = queries.get_summary_kpis(client_id=client_id or None)

    # Accounts table
    search = request.GET.get("search", "")
    sort = request.GET.get("sort", "account_name")
    order = request.GET.get("order", "asc")
    page = _parse_int(request.GET.get("page"), 1)
    page_size = _parse_int(request.GET.get("page_size"), settings.DEFAULT_PAGE_SIZE,
                           maximum=settings.MAX_PAGE_SIZE)

    accounts_data = queries.get_accounts_page(
        client_id=client_id or None, search=search,
        sort=sort, order=order, page=page, page_size=page_size,
    )

    context = {
        "clients": clients,
        "selected_client_id": client_id,
        "kpis": kpis,
        "accounts": accounts_data,
        "search": search,
        "sort": sort,
        "order": order,
        "page_title": "Summary",
        "active_page": "summary",
    }

    # HTMX partial rendering
    if request.headers.get("HX-Request"):
        return render(request, "partials/summary_content.html", context)

    return render(request, "dashboard/summary.html", context)


# ---------------------------------------------------------------------------
# Transactions Page
# ---------------------------------------------------------------------------
@login_required
@require_GET
def transactions_view(request):
    """Transactions page with filters."""
    clients = Client.objects.filter(active=True)
    client_id = request.GET.get("client_id", "")
    account_id = request.GET.get("account_id", "")

    # Date range defaults: last 30 days
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    if not date_from:
        date_from = str(date.today() - timedelta(days=30))
    if not date_to:
        date_to = str(date.today())

    pending_raw = request.GET.get("pending", "")
    pending = None
    if pending_raw == "true":
        pending = True
    elif pending_raw == "false":
        pending = False

    search = request.GET.get("search", "")
    sort = request.GET.get("sort", "transaction_date")
    order = request.GET.get("order", "desc")
    page = _parse_int(request.GET.get("page"), 1)
    page_size = _parse_int(request.GET.get("page_size"), settings.DEFAULT_PAGE_SIZE,
                           maximum=settings.MAX_PAGE_SIZE)

    txn_data = queries.get_transactions_page(
        client_id=client_id or None, account_id=account_id or None,
        date_from=date_from, date_to=date_to, pending=pending,
        search=search, sort=sort, order=order,
        page=page, page_size=page_size,
    )

    # Account options for filter
    account_options = queries.get_account_options(client_id=client_id or None)

    context = {
        "clients": clients,
        "selected_client_id": client_id,
        "selected_account_id": account_id,
        "account_options": account_options,
        "date_from": date_from,
        "date_to": date_to,
        "pending": pending_raw,
        "search": search,
        "transactions": txn_data,
        "sort": sort,
        "order": order,
        "page_title": "Transactions",
        "active_page": "transactions",
        "is_mobile": _is_mobile(request),
    }

    if request.headers.get("HX-Request"):
        return render(request, "partials/transactions_content.html", context)

    return render(request, "dashboard/transactions.html", context)


# ---------------------------------------------------------------------------
# Account options HTMX endpoint
# ---------------------------------------------------------------------------
@login_required
@require_GET
def account_options_view(request):
    """Return account <option> elements filtered by client."""
    client_id = request.GET.get("client_id", "")
    options = queries.get_account_options(client_id=client_id or None)
    return render(request, "partials/account_options.html", {"account_options": options})


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------
@login_required
@require_GET
def export_csv_view(request):
    """Export filtered transactions as CSV. Desktop only."""
    if _is_mobile(request):
        return HttpResponse("CSV export is not available on mobile devices.", status=403)

    client_id = request.GET.get("client_id", "") or None
    account_id = request.GET.get("account_id", "") or None
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    pending_raw = request.GET.get("pending", "")
    pending = None
    if pending_raw == "true":
        pending = True
    elif pending_raw == "false":
        pending = False
    search = request.GET.get("search", "")

    max_rows = settings.CSV_EXPORT_MAX_ROWS
    rows, total, exceeded = queries.get_transactions_for_export(
        client_id=client_id, account_id=account_id,
        date_from=date_from or None, date_to=date_to or None,
        pending=pending, search=search, max_rows=max_rows,
    )

    if exceeded:
        log_event(request, "csv_export_denied",
                  detail=f"Exceeded {max_rows} rows ({total} matched). User advised to narrow filters.")
        return HttpResponse(
            f"Export exceeds the {max_rows:,} row limit ({total:,} rows matched). "
            f"Please narrow your date range and/or select a specific account.",
            status=400,
            content_type="text/plain",
        )

    log_event(request, "csv_export_initiated", detail=f"{total} rows")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="transactions_{date_from}_{date_to}.csv"'

    writer = csv.writer(response)
    writer.writerow(queries.CSV_COLUMNS)
    for row in rows:
        writer.writerow(row)

    log_event(request, "csv_export_completed", detail=f"{total} rows")
    return response
