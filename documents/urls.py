from django.urls import path

from . import folder_views, views


urlpatterns = [
    path("", views.document_list, name="document_list"),
    path("new/", views.document_create, name="document_create"),
    path("folders/", folder_views.folder_list, name="folder_list"),
    path("folders/new/", folder_views.folder_create, name="folder_create"),
    path(
        "folders/<uuid:folder_pk>/manage/",
        folder_views.folder_manage,
        name="folder_manage",
    ),
    path(
        "folders/<uuid:folder_pk>/",
        folder_views.folder_detail,
        name="folder_detail",
    ),
    path("<uuid:pk>/download/", views.document_download, name="document_download"),
    path("<uuid:pk>/preview/", views.document_preview, name="document_preview"),
    path("<uuid:pk>/", views.document_detail, name="document_detail"),
    path("<uuid:pk>/edit/", views.document_edit, name="document_edit"),
    path("<uuid:pk>/delete/", views.document_delete, name="document_delete"),
]
