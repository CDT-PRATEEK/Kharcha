from django.urls import path
from . import views

urlpatterns = [
    path("income/", views.income_list, name="income-list"),
    path("income/add/", views.income_add, name="income-add"),
    path("income/<int:pk>/edit/", views.income_edit, name="income-edit"),
    path("income/<int:pk>/delete/", views.income_delete, name="income-delete"),
    path("download/", views.income_download_csv, name="income-download"),
]
