from rest_framework import viewsets

from health.api.serializers import RepositorySerializer
from health.models import Repository


class RepositoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Repository.objects.filter(
        visibility=Repository.VisibilityType.PUBLIC,
    ).order_by("-stars")
    serializer_class = RepositorySerializer
    lookup_field = "repo_slug"
