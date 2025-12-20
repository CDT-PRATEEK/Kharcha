from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='expenses-home'),
    path('my-expenses/', views.my_expenses, name='my-expenses'),
    path('add-expense/', views.add_expense, name='add-expense'),
    path("expense/<int:pk>/edit/", views.edit_expense, name="edit-expense"),
    path("expense/<int:pk>/delete/", views.delete_expense, name="delete-expense"),
    path("download/", views.expense_download_csv, name="expense-download"),

]