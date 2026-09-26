from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("extraction/", include("extraction.urls")),
    path("", include("projects.urls")),
]
