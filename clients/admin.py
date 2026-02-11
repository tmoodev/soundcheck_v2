from django.contrib import admin
from .models import Client, ClientAccount


class ClientAccountInline(admin.TabularInline):
    model = ClientAccount
    extra = 1


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "created_at")
    inlines = [ClientAccountInline]
