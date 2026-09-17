"""Демо-данные для проверки работы сервиса оценки здоровья репозиториев.

Модуль создаёт несколько тестовых репозиториев, прогонов анализа, метрик,
оценок по категориям и находок. Данные согласованы с моделями приложения:
- Repository требует org_slug, repo_slug, sourcecraft_id, url, logo_url,
  last_updated, visibility.
- Scan требует triggered_by.
- MetricSample описывает одну метрику внутри категории.
- HealthScore привязан к Scan как OneToOne и хранит category, total,
  weight_used, data_completeness, raw_metrics.
- Finding severity ограничен значениями low/medium/high/critical.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from health.models import Finding, HealthScore, MetricSample, Repository, Scan


CATEGORY_WEIGHTS = {
    MetricSample.Category.DOCS: 0.15,
    MetricSample.Category.CI_CD: 0.25,
    MetricSample.Category.SECURITY: 0.20,
    MetricSample.Category.ACTIVITY: 0.25,
    MetricSample.Category.ISSUES: 0.10,
    MetricSample.Category.CODE_HEALTH: 0.05,
}


DEMO_REPOS = [
    {
        "org_slug": "sourcecraft",
        "repo_slug": "sdk-python",
        "description": "Официальный SDK для работы с API SourceCraft.",
        "language": "Python",
        "stars": 48,
        "forks": 7,
        "sourcecraft_id": "sc-sourcecraft-sdk-python",
        "url": "https://sourcecraft.dev/sourcecraft/sdk-python",
        "logo_url": "https://sourcecraft.dev/static/logos/sdk-python.png",
        "is_empty": False,
        "visibility": Repository.VisibilityType.PUBLIC,
        "days_since_commit": 2,
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
        "description": "Сервис оценки здоровья открытых репозиториев.",
        "language": "Python",
        "stars": 12,
        "forks": 1,
        "sourcecraft_id": "sc-nextdev-repo-health",
        "url": "https://sourcecraft.dev/nextdev/repo-health",
        "logo_url": "https://sourcecraft.dev/static/logos/repo-health.png",
        "is_empty": False,
        "visibility": Repository.VisibilityType.INTERNAL,
        "days_since_commit": 1,
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
        "description": "Старый парсер без CI и с открытыми алертами.",
        "language": "Go",
        "stars": 3,
        "forks": 0,
        "sourcecraft_id": "sc-archive-legacy-parser",
        "url": "https://sourcecraft.dev/archive/legacy-parser",
        "logo_url": "https://sourcecraft.dev/static/logos/legacy-parser.png",
        "is_empty": False,
        "visibility": Repository.VisibilityType.PUBLIC,
        "days_since_commit": 120,
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


# Соответствие категорий моделей и наборов метрик для демо-данных.
METRIC_DEFINITIONS = [
    # (category, metric_key, value, unit, is_available, error_reason, source_reference)
    (
        MetricSample.Category.DOCS,
        "readme_present",
        True,
        "bool",
        True,
        "",
        "README.md",
    ),
    (
        MetricSample.Category.DOCS,
        "contributing_present",
        True,
        "bool",
        True,
        "",
        "CONTRIBUTING.md",
    ),
    (
        MetricSample.Category.CI_CD,
        "ci_success_rate_90d",
        0.96,
        "ratio",
        True,
        "",
        ".sourcecraft/ci.yaml",
    ),
    (
        MetricSample.Category.SECURITY,
        "open_alerts",
        0,
        "count",
        True,
        "",
        "security/alerts",
    ),
    (
        MetricSample.Category.ACTIVITY,
        "days_since_commit",
        2,
        "days",
        True,
        "",
        "commits/HEAD",
    ),
    (
        MetricSample.Category.ISSUES,
        "open_issues",
        4,
        "count",
        True,
        "",
        "issues?state=open",
    ),
    (
        MetricSample.Category.CODE_HEALTH,
        "todo_count",
        3,
        "count",
        True,
        "",
        "grep TODO",
    ),
]


class Command(BaseCommand):
    help = "Создаёт демо-репозитории и сразу считает score."

    def handle(self, *args, **options):
        created = 0
        for item in DEMO_REPOS:
            raw = item["raw"]
            repo, _ = Repository.objects.get_or_create(
                org_slug=item["org_slug"],
                repo_slug=item["repo_slug"],
                defaults={
                    "description": item["description"],
                    "language": item["language"],
                    "stars": item["stars"],
                    "forks": item["forks"],
                    "sourcecraft_id": item["sourcecraft_id"],
                    "url": item["url"],
                    "logo_url": item["logo_url"],
                    "is_empty": item["is_empty"],
                    "last_updated": timezone.now()
                    - timedelta(days=item["days_since_commit"]),
                    "visibility": item["visibility"],
                },
            )
            if repo.scans.exists():
                continue

            scan = Scan.objects.create(
                repository=repo,
                status=Scan.Status.SUCCESS,
                raw=raw,
                finished_at=timezone.now(),
                triggered_by=Scan.TriggeredBy.MANUAL,
            )

            self._create_metrics(scan, raw)
            self._create_scores(scan, raw)
            self._create_findings(scan, raw)

            repo.last_scanned_at = scan.finished_at
            repo.save(update_fields=["last_scanned_at"])
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Готово, новых сканов: {created}"))

    def _create_metrics(self, scan: Scan, raw: dict) -> None:
        """Создаёт MetricSample-записи, согласованные с моделями."""
        samples = []
        for (category, metric_key, value, unit, is_available,
             error_reason, source_reference) in METRIC_DEFINITIONS:
            samples.append(
                MetricSample(
                    scan=scan,
                    category=category,
                    metric_key=metric_key,
                    value=value,
                    unit=unit,
                    is_available=is_available,
                    error_reason=error_reason,
                    source_reference=source_reference,
                )
            )

        # Пример недоступной метрики: данные по релизам отсутствуют.
        if not raw.get("releases"):
            samples.append(
                MetricSample(
                    scan=scan,
                    category=MetricSample.Category.CI_CD,
                    metric_key="release_count",
                    value=None,
                    unit="count",
                    is_available=False,
                    error_reason="Релизы отсутствуют или недоступны",
                    source_reference="releases",
                )
            )

        MetricSample.objects.bulk_create(samples)

    def _create_scores(self, scan: Scan, raw: dict) -> None:
        """Создаёт HealthScore по категориям согласно весам и метрикам."""
        category_values = {
            MetricSample.Category.DOCS: 80 if raw.get("has_readme") else 20,
            MetricSample.Category.CI_CD: (
                85 if raw.get("has_ci") and raw.get("releases") else 40
            ),
            MetricSample.Category.SECURITY: (
                90 if raw.get("open_alerts", 0) == 0 else 35
            ),
            MetricSample.Category.ACTIVITY: (
                90 if raw.get("days_since_commit", 99) < 14 else 45
            ),
            MetricSample.Category.ISSUES: 70,
            MetricSample.Category.CODE_HEALTH: 65,
        }

        scores = []
        for category, weight in CATEGORY_WEIGHTS.items():
            total = category_values.get(category)
            raw_snapshot = {k: v for k, v in raw.items()}
            scores.append(
                HealthScore(
                    scan=scan,
                    category=category,
                    total=total,
                    weight_used=weight,
                    data_completeness=1.0 if total is not None else 0.0,
                    raw_metrics=raw_snapshot,
                )
            )
        HealthScore.objects.bulk_create(scores)

    def _create_findings(self, scan: Scan, raw: dict) -> None:
        """Создаёт Finding с severity, допустимой моделью."""
        findings = []

        if not raw.get("has_ci"):
            findings.append(
                Finding(
                    scan=scan,
                    category=MetricSample.Category.CI_CD,
                    severity=Finding.Severity.HIGH,
                    title="Нет CI-конфига",
                    detail="В репозитории не найден пайплайн SourceCraft CI.",
                    recommendation="Добавьте .sourcecraft/ci.yaml с базовой проверкой сборки.",
                    evidence_refs=[".sourcecraft/ci.yaml"],
                    estimated_score_impact=10,
                )
            )
        if raw.get("open_alerts", 0):
            findings.append(
                Finding(
                    scan=scan,
                    category=MetricSample.Category.SECURITY,
                    severity=Finding.Severity.CRITICAL,
                    title="Открытые AppSec-алерты",
                    detail=f"Найдено алертов: {raw['open_alerts']}.",
                    recommendation=(
                        "Закройте уязвимости зависимостей "
                        "или зафиксируйте ложные срабатывания."
                    ),
                    evidence_refs=["security/alerts"],
                    estimated_score_impact=20,
                )
            )
        if raw.get("days_since_commit", 0) > 30:
            findings.append(
                Finding(
                    scan=scan,
                    category=MetricSample.Category.ACTIVITY,
                    severity=Finding.Severity.MEDIUM,
                    title="Давно не было коммитов",
                    detail=(
                        f"Последняя активность {raw['days_since_commit']} дн. назад."
                    ),
                    recommendation=(
                        "Проверьте, не заброшен ли проект, "
                        "и обновите статус в README."
                    ),
                    evidence_refs=["commits/HEAD"],
                    estimated_score_impact=15,
                )
            )
        if not raw.get("releases"):
            findings.append(
                Finding(
                    scan=scan,
                    category=MetricSample.Category.CI_CD,
                    severity=Finding.Severity.LOW,
                    title="Нет релизов",
                    detail="Теги и релизы не найдены.",
                    recommendation=(
                        "Опубликуйте хотя бы один релиз, "
                        "чтобы потребители видели стабильную версию."
                    ),
                    evidence_refs=["releases"],
                    estimated_score_impact=5,
                )
            )
        if not raw.get("has_readme"):
            findings.append(
                Finding(
                    scan=scan,
                    category=MetricSample.Category.DOCS,
                    severity=Finding.Severity.MEDIUM,
                    title="Отсутствует README",
                    detail="В репозитории не найден файл README.",
                    recommendation=(
                        "Добавьте README.md с описанием проекта "
                        "и инструкцией по запуску."
                    ),
                    evidence_refs=["README.md"],
                    estimated_score_impact=8,
                )
            )

        if findings:
            Finding.objects.bulk_create(findings)
