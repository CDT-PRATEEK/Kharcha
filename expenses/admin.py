
from django.contrib import admin
from .models import Category, Expense  


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    list_filter = ('user',)
    search_fields = ('name',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'date', 'is_borrowed', 'borrowed_from', 'created_at')
    list_filter = ('user', 'category', 'date', 'is_borrowed', 'borrowed_from')
    search_fields = ('description', 'borrowed_from')

