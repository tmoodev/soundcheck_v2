from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.summary_view, name="summary"),
    path("transactions/", views.transactions_view, name="transactions"),
    path("transactions/export/", views.export_csv_view, name="export_csv"),
    path("api/account-options/", views.account_options_view, name="account_options"),
]
