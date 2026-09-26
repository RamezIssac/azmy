from django.urls import path

from . import views

app_name = "extraction"

urlpatterns = [
    path("documents/<int:pk>/review/", views.review_document, name="review"),
    path(
        "documents/<int:pk>/approve/",
        views.approve_document,
        name="approve",
    ),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path(
        "items/<int:pk>/toggle-reviewed/",
        views.item_toggle_reviewed,
        name="item_toggle_reviewed",
    ),
]
