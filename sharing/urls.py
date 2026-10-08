from django.urls import path

from . import views


urlpatterns = [
    path(
        "documents/<uuid:document_pk>/",
        views.manage_document_shares,
        name="document_share_manage",
    ),
    path(
        "<int:share_pk>/revoke/",
        views.revoke_document_share,
        name="document_share_revoke",
    ),
]
