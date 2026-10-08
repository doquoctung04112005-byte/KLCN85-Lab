from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "department", "created_at", "updated_at")
    list_filter = ("department", "created_at", "updated_at")
    search_fields = ("title", "content", "owner__username", "department__name")
    readonly_fields = ("id", "created_at", "updated_at")
