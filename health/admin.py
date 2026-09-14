from django.contrib import admin

from .models import Finding, HealthScore, Repository, Scan


class FindingInline(admin.TabularInline):
    model = Finding
    extra = 0


class HealthScoreInline(admin.StackedInline):
    model = HealthScore
    extra = 0


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("org_slug", "repo_slug", "language", "stars", "last_scanned_at")
    search_fields = ("org_slug", "repo_slug", "name")


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("repository", "status", "created_at", "finished_at")
    list_filter = ("status",)
    inlines = [HealthScoreInline, FindingInline]
