from django.contrib import admin

from ACI_backend.ACIApp.models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
	list_display = ["full_name", "is_active", "updated_at"]
	search_fields = ["full_name", "owner", "name"]
	list_filter = ["is_active"]
