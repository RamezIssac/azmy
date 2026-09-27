from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path("manual/", TemplateView.as_view(template_name="manual/index.html"), name="manual"),
    path(
        "manual/projekt/",
        TemplateView.as_view(template_name="manual/projekt.html"),
        name="manual_projekt",
    ),
    path(
        "manual/bidding/",
        TemplateView.as_view(template_name="manual/bidding.html"),
        name="manual_bidding",
    ),
    path(
        "manual/sprint/",
        TemplateView.as_view(template_name="manual/sprint.html"),
        name="manual_sprint",
    ),
]
