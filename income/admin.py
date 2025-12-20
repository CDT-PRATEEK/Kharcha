from django.contrib import admin
from .models import Income


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "amount", "source", "payment_type", "person", "created_at")
    list_filter = ("user", "source", "payment_type", "person", "date")
    search_fields = ("source", "person", "description")
