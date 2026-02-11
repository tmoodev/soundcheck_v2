"""
Raw SQL queries against analytics views.
All queries use parameterized inputs – never string interpolation.
The search_path is set by django-tenants to the tenant schema.
"""
from django.db import connection

from clients.models import ClientAccount


def _get_account_ids_for_client(client_id):
    """Return list of account_ids mapped to a client, or None if no filter."""
    if not client_id:
        return None
    return list(
        ClientAccount.objects.filter(client_id=client_id).values_list("account_id", flat=True)
    )


def _account_filter_clause(account_ids, params, alias="a"):
    """Build a WHERE clause fragment for account filtering."""
    if account_ids is None:
        return "", params
    if not account_ids:
        # No accounts mapped → return impossible condition
        return f"AND {alias}.account_id = ANY(%(account_ids)s)", {**params, "account_ids": []}
    return f"AND {alias}.account_id = ANY(%(account_ids)s)", {**params, "account_ids": account_ids}


# ---------------------------------------------------------------------------
# Summary KPIs
# ---------------------------------------------------------------------------
def get_summary_kpis(client_id=None):
    """Return dict with total_balance, total_available, total_pending."""
    account_ids = _get_account_ids_for_client(client_id)

    params = {}
    acct_filter, params = _account_filter_clause(account_ids, params, alias="a")

    # Balance KPIs from accounts view
    sql_balance = f"""
        SELECT
            COALESCE(SUM(a.current_balance), 0) AS total_balance,
            COALESCE(SUM(a.available_balance), 0) AS total_available
        FROM analytics.vw_superset_accounts_current a
        WHERE 1=1 {acct_filter}
    """

    # Pending from transactions view (NO date filter)
    pending_filter, pending_params = _account_filter_clause(account_ids, {}, alias="t")
    sql_pending = f"""
        SELECT COALESCE(SUM(t.amount_abs), 0) AS total_pending
        FROM analytics.vw_superset_transactions t
        WHERE t.pending = true {pending_filter}
    """

    with connection.cursor() as cur:
        cur.execute(sql_balance, params)
        row = cur.fetchone()
        total_balance = row[0]
        total_available = row[1]

        cur.execute(sql_pending, pending_params)
        total_pending = cur.fetchone()[0]

    return {
        "total_balance": total_balance,
        "total_available": total_available,
        "total_pending": total_pending,
    }


# ---------------------------------------------------------------------------
# Accounts Table
# ---------------------------------------------------------------------------
ACCOUNTS_COLUMNS = [
    "account_name", "institution_name", "type", "subtype", "mask",
    "current_balance", "available_balance", "credit_limit",
    "utilization_pct", "is_overdrawn", "balance_as_of",
]

ACCOUNTS_SORTABLE = {
    "account_name", "institution_name", "type", "subtype", "mask",
    "current_balance", "available_balance", "credit_limit",
    "utilization_pct", "balance_as_of",
}

ACCOUNTS_SEARCH_FIELDS = ["account_name", "institution_name", "mask"]


def get_accounts_page(client_id=None, search="", sort="account_name", order="asc",
                      page=1, page_size=25):
    """Return paginated accounts with total count."""
    account_ids = _get_account_ids_for_client(client_id)
    params = {}
    acct_filter, params = _account_filter_clause(account_ids, params, alias="a")

    search_clause = ""
    if search:
        search_clause = """
            AND (
                a.account_name ILIKE %(search)s
                OR a.institution_name ILIKE %(search)s
                OR a.mask ILIKE %(search)s
            )
        """
        params["search"] = f"%{search}%"

    # Validate sort column
    if sort not in ACCOUNTS_SORTABLE:
        sort = "account_name"
    if order not in ("asc", "desc"):
        order = "asc"

    # We need safe column reference – validated above so safe to interpolate
    sort_clause = f"a.{sort} {order} NULLS LAST"

    count_sql = f"""
        SELECT COUNT(*)
        FROM analytics.vw_superset_accounts_current a
        WHERE 1=1 {acct_filter} {search_clause}
    """

    data_sql = f"""
        SELECT
            a.account_id, a.account_name, a.institution_name, a.type, a.subtype,
            a.mask, a.current_balance, a.available_balance, a.credit_limit,
            a.utilization_pct, a.is_overdrawn, a.balance_as_of
        FROM analytics.vw_superset_accounts_current a
        WHERE 1=1 {acct_filter} {search_clause}
        ORDER BY {sort_clause}
        LIMIT %(limit)s OFFSET %(offset)s
    """

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    with connection.cursor() as cur:
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]

        cur.execute(data_sql, params)
        columns = [col[0] for col in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


# ---------------------------------------------------------------------------
# Transactions Table
# ---------------------------------------------------------------------------
TRANSACTIONS_SORTABLE = {
    "transaction_date", "transaction_name", "merchant_name", "amount",
    "account_name", "institution_name", "payment_channel", "transaction_type",
    "flow_direction", "pending",
}


def get_transactions_page(client_id=None, account_id=None, date_from=None,
                          date_to=None, pending=None, search="",
                          sort="transaction_date", order="desc",
                          page=1, page_size=25):
    """Return paginated transactions with total count."""
    account_ids = _get_account_ids_for_client(client_id)
    # If a specific account_id is given, intersect
    if account_id:
        if account_ids is not None:
            if account_id in account_ids:
                account_ids = [account_id]
            else:
                account_ids = []  # No access
        else:
            account_ids = [account_id]

    params = {}
    acct_filter, params = _account_filter_clause(account_ids, params, alias="t")

    date_clause = ""
    if date_from:
        date_clause += " AND t.transaction_date >= %(date_from)s"
        params["date_from"] = date_from
    if date_to:
        date_clause += " AND t.transaction_date <= %(date_to)s"
        params["date_to"] = date_to

    pending_clause = ""
    if pending is not None:
        pending_clause = " AND t.pending = %(pending_val)s"
        params["pending_val"] = pending

    search_clause = ""
    if search:
        search_clause = """
            AND (
                t.transaction_name ILIKE %(search)s
                OR t.merchant_name ILIKE %(search)s
            )
        """
        params["search"] = f"%{search}%"

    if sort not in TRANSACTIONS_SORTABLE:
        sort = "transaction_date"
    if order not in ("asc", "desc"):
        order = "desc"

    sort_clause = f"t.{sort} {order} NULLS LAST"

    where = f"WHERE 1=1 {acct_filter} {date_clause} {pending_clause} {search_clause}"

    count_sql = f"""
        SELECT COUNT(*)
        FROM analytics.vw_superset_transactions t
        {where}
    """

    data_sql = f"""
        SELECT
            t.transaction_id, t.transaction_date, t.transaction_name, t.merchant_name,
            t.amount, t.amount_abs, t.pending, t.account_name, t.account_id,
            t.institution_name, t.payment_channel, t.transaction_type,
            t.category_id, t.flow_direction, t.iso_currency_code
        FROM analytics.vw_superset_transactions t
        {where}
        ORDER BY {sort_clause}
        LIMIT %(limit)s OFFSET %(offset)s
    """

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    with connection.cursor() as cur:
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]

        cur.execute(data_sql, params)
        columns = [col[0] for col in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


# ---------------------------------------------------------------------------
# CSV Export (transactions)
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "transaction_date", "transaction_name", "merchant_name", "amount", "pending",
    "account_name", "institution_name", "payment_channel", "transaction_type",
    "category_id", "flow_direction",
]


def get_transactions_for_export(client_id=None, account_id=None, date_from=None,
                                date_to=None, pending=None, search="",
                                max_rows=250_000):
    """Return (rows, total_count, exceeded). If exceeded, rows is empty."""
    account_ids = _get_account_ids_for_client(client_id)
    if account_id:
        if account_ids is not None:
            if account_id in account_ids:
                account_ids = [account_id]
            else:
                account_ids = []
        else:
            account_ids = [account_id]

    params = {}
    acct_filter, params = _account_filter_clause(account_ids, params, alias="t")

    date_clause = ""
    if date_from:
        date_clause += " AND t.transaction_date >= %(date_from)s"
        params["date_from"] = date_from
    if date_to:
        date_clause += " AND t.transaction_date <= %(date_to)s"
        params["date_to"] = date_to

    pending_clause = ""
    if pending is not None:
        pending_clause = " AND t.pending = %(pending_val)s"
        params["pending_val"] = pending

    search_clause = ""
    if search:
        search_clause = """
            AND (
                t.transaction_name ILIKE %(search)s
                OR t.merchant_name ILIKE %(search)s
            )
        """
        params["search"] = f"%{search}%"

    where = f"WHERE 1=1 {acct_filter} {date_clause} {pending_clause} {search_clause}"

    count_sql = f"SELECT COUNT(*) FROM analytics.vw_superset_transactions t {where}"

    cols = ", ".join(f"t.{c}" for c in CSV_COLUMNS)
    data_sql = f"""
        SELECT {cols}
        FROM analytics.vw_superset_transactions t
        {where}
        ORDER BY t.transaction_date DESC
        LIMIT %(export_limit)s
    """
    params["export_limit"] = max_rows

    with connection.cursor() as cur:
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]

        if total > max_rows:
            return [], total, True

        cur.execute(data_sql, params)
        rows = cur.fetchall()

    return rows, total, False


def get_account_options(client_id=None):
    """Return list of (account_id, label) for filter dropdowns."""
    account_ids = _get_account_ids_for_client(client_id)
    params = {}
    acct_filter, params = _account_filter_clause(account_ids, params, alias="a")

    sql = f"""
        SELECT a.account_id, a.account_name || ' (' || a.mask || ')' AS label
        FROM analytics.vw_superset_accounts_current a
        WHERE 1=1 {acct_filter}
        ORDER BY a.account_name
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
