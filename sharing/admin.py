from django.contrib import admin

from .models import DocumentShare


@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "granted_by",
        "recipient",
        "permission",
        "expires_at",
        "created_at",
        "revoked_at",
    )
    list_filter = ("permission", "created_at", "expires_at", "revoked_at")
    search_fields = (
        "document__title",
        "granted_by__username",
        "recipient__username",
    )
    readonly_fields = ("created_at",)
