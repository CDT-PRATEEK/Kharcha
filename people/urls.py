
from django.urls import path
from . import views

urlpatterns = [

    # PEOPLE LIST + CREATE
    path("people/", views.people_list, name="people-list"),
    path("people/add/", views.person_create, name="person-add"),
    path("people/<int:pk>/", views.person_detail, name="person-detail"),

    # --- APPLY income to ledger ---
    path(
        "apply-income/<int:person_id>/<int:income_id>/",
        views.apply_income_to_people,
        name="apply-income-to-people",
    ),

    # --- APPLY expense (ASK banner buttons) ---
    # These EXACT names are required by add_expense()
    path(
        "<int:person_id>/<int:expense_id>/apply-and-track/",
        views.apply_expense_and_track,
        name="people-apply-expense-and-track",
    ),

    path(
        "<int:person_id>/<int:expense_id>/apply-once/",
        views.apply_expense_once,
        name="people-apply-expense-once",
    ),

    # --- ASK Banner: Set tracking prefs (add_expense expects these names) ---
    path(
        "<int:person_id>/set-no-track/",
        views.set_person_no_track,
        name="people-set-no-track",
    ),

    path(
        "<int:person_id>/set-track/",
        views.set_person_track,
        name="people-set-track",
    ),

    path(
        "<int:person_id>/set-ask/",
        views.set_person_ask,
        name="people-set-ask",
    ),

    # --- Change Tracking Preference Page ---
    path(
        "<int:person_id>/change-tracking/",
        views.person_change_tracking,
        name="person-change-tracking",
    ),
    path("<int:person_id>/restore/", views.restore_person_tracking, name="person-restore"),

    path(
    'apply-income-and-track/<int:person_id>/<int:income_id>/',
    views.apply_income_and_track,
    name='people-apply-income-and-track'
    ),
    path(
        'apply-income-once/<int:person_id>/<int:income_id>/',
        views.apply_income_once,
        name='people-apply-income-once'
    ),
    path("clear-banner/", views.clear_pending_banner, name="clear-pending-banner"),

    path(
    "person/<int:pk>/delete/",
    views.person_delete,
    name="person-delete",
),




]

