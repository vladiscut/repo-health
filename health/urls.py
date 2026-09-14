from django.urls import path

from . import views

urlpatterns = [
    path("", views.repo_list, name="repo-list"),
    path("repos/<slug:org_slug>/<slug:repo_slug>/", views.repo_detail, name="repo-detail"),
    path("repos/<slug:org_slug>/<slug:repo_slug>/rescan/", views.repo_rescan, name="repo-rescan"),
]
