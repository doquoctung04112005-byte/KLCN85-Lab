from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "result")
    list_filter = ("action", "object_type", "result", "created_at")
    search_fields = (
        "actor__username",
        "action",
        "object_type",
        "object_id",
        "result",
    )
    readonly_fields = ("created_at",)
