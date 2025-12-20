from django.contrib import admin
from .models import Person, PersonLedgerEntry


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "balance", "auto_suggest_enabled", "created_at")
    list_filter = ("user", "auto_suggest_enabled")
    search_fields = ("name", "user__username")


@admin.register(PersonLedgerEntry)
class PersonLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("person", "user", "amount", "source_type", "created_at")
    list_filter = ("source_type", "user")
    search_fields = ("person__name", "note")

