from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("projects/new/", views.project_create, name="create"),
    path("projects/<slug:slug>/", views.project_detail, name="detail"),
    path(
        "projects/<slug:slug>/upload/", views.upload_documents, name="upload"
    ),
    path(
        "projects/<slug:slug>/publish/", views.publish_project, name="publish"
    ),
    path(
        "projects/<slug:slug>/unpublish/",
        views.unpublish_project,
        name="unpublish",
    ),
    path(
        "documents/<int:pk>/process/",
        views.process_document,
        name="process_document",
    ),
    path("documents/<int:pk>/file/", views.document_file, name="document_file"),
    # public, token-gated
    path("p/<uuid:token>/", views.public_project, name="public"),
    path("api/v1/p/<uuid:token>/", views.public_project_api, name="public_api"),
]
