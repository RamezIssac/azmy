from django.urls import path

from . import views

app_name = "bidding"

urlpatterns = [
    path("portal/", views.portal, name="portal"),
    path("portal/bid/<slug:slug>/", views.bid_editor, name="bid_editor"),
    path("projects/<slug:slug>/bids/", views.leveling, name="leveling"),
]
