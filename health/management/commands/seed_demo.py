from django.core.management.base import BaseCommand
from django.utils import timezone

from health.models import Finding, HealthScore, Repository, Scan
from health.scoring import score_from_raw


DEMO_REPOS = [
    {
        "org_slug": "sourcecraft",
        "repo_slug": "sdk-python",
        "name": "sdk-python",
        "description": "Официальный SDK для работы с API SourceCraft.",
        "language": "Python",
        "stars": 48,
        "forks": 7,
        "raw": {
            "stars": 48,
            "forks": 7,
            "language": "Python",
            "has_readme": True,
            "has_ci": True,
            "open_alerts": 0,
            "days_since_commit": 2,
            "contributors": 11,
            "releases": 6,
        },
    },
    {
        "org_slug": "nextdev",
        "repo_slug": "repo-health",
        "name": "repo-health",
        "description": "Сервис оценки здоровья открытых репозиториев.",
        "language": "Python",
        "stars": 12,
        "forks": 1,
        "raw": {
            "stars": 12,
            "forks": 1,
            "language": "Python",
            "has_readme": True,
            "has_ci": True,
            "open_alerts": 0,
            "days_since_commit": 1,
            "contributors": 2,
            "releases": 0,
        },
    },
    {
        "org_slug": "archive",
        "repo_slug": "legacy-parser",
        "name": "legacy-parser",
        "description": "Старый парсер без CI и с открытыми алертами.",
        "language": "Go",
        "stars": 3,
        "forks": 0,
        "raw": {
            "stars": 3,
            "forks": 0,
            "language": "Go",
            "has_readme": False,
            "has_ci": False,
            "open_alerts": 3,
            "days_since_commit": 120,
            "contributors": 1,
            "releases": 0,
        },
    },
]


class Command(BaseCommand):
    help = "Создаёт демо-репозитории и сразу считает score."

    def handle(self, *args, **options):
        created = 0
        for item in DEMO_REPOS:
            payload = {k: v for k, v in item.items() if k != "raw"}
            raw = item["raw"]
            repo, is_new = Repository.objects.get_or_create(
                org_slug=payload["org_slug"],
                repo_slug=payload["repo_slug"],
                defaults=payload,
            )
            if repo.scans.exists():
                continue
            scan = Scan.objects.create(
                repository=repo,
                status=Scan.Status.SUCCESS,
                raw=raw,
                finished_at=timezone.now(),
            )
            score_data, findings = score_from_raw(raw)
            HealthScore.objects.create(scan=scan, **score_data)
            Finding.objects.bulk_create([Finding(scan=scan, **row) for row in findings])
            repo.last_scanned_at = scan.finished_at
            repo.save(update_fields=["last_scanned_at"])
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Готово, новых сканов: {created}"))
