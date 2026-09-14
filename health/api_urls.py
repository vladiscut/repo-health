from rest_framework import serializers, viewsets
from rest_framework.routers import DefaultRouter

from .models import Repository


class RepositorySerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = Repository
        fields = (
            "id",
            "org_slug",
            "repo_slug",
            "name",
            "description",
            "language",
            "stars",
            "forks",
            "last_scanned_at",
            "score",
        )

    def get_score(self, obj):
        scan = obj.latest_scan()
        if not scan or not hasattr(scan, "score"):
            return None
        return {
            "total": scan.score.total,
            "activity": scan.score.activity,
            "community": scan.score.community,
            "maintenance": scan.score.maintenance,
            "documentation": scan.score.documentation,
            "security": scan.score.security,
        }


class RepositoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer


router = DefaultRouter()
router.register("repos", RepositoryViewSet)

urlpatterns = router.urls
