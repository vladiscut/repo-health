"""Celery-задача анализа репозитория.

Задача создаёт снимок :class:`health.models.Scan`, собирает метрики,
считает оценки по категориям и формирует находки. Контракт совпадает
с моделями приложения:
- :class:`health.models.MetricSample` — по одной записи на метрику;
- :class:`health.models.HealthScore` — по одной записи на категорию;
- :class:`health.models.Finding` — severity из допустимых choices.
"""

from django.db import transaction
from django.utils import timezone

from celery import shared_task

from health.models import (
    Finding,
    HealthScore,
    MetricSample,
    Repository,
    Scan,
)
from health.scoring import score_from_raw


# Соответствие ключей сырых метрик и категорий MetricSample.
_METRIC_DEFINITIONS = [
    # (category, metric_key, raw_key, unit, source_reference)
    (
        MetricSample.Category.DOCS,
        "readme_present",
        "has_readme",
        "bool",
        "README.md",
    ),
    (
        MetricSample.Category.CI_CD,
        "ci_present",
        "has_ci",
        "bool",
        ".sourcecraft/ci.yaml",
    ),
    (
        MetricSample.Category.CI_CD,
        "release_count",
        "releases",
        "count",
        "releases",
    ),
    (
        MetricSample.Category.SECURITY,
        "open_alerts",
        "open_alerts",
        "count",
        "security/alerts",
    ),
    (
        MetricSample.Category.ACTIVITY,
        "days_since_commit",
        "days_since_commit",
        "days",
        "commits/HEAD",
    ),
    (
        MetricSample.Category.ISSUES,
        "open_issues",
        "open_issues",
        "count",
        "issues?state=open",
    ),
    (
        MetricSample.Category.CODE_HEALTH,
        "todo_count",
        "todo_count",
        "count",
        "grep TODO",
    ),
]


def _collect_raw(repo: Repository) -> dict:
    """Собирает сырые метрики репозитория.

    Источник данных для демонстрации — детерминированные правила по полям
    :class:`health.models.Repository`. В продакшене здесь будет обращение
    к API SourceCraft.
    """
    has_ci = repo.repo_slug != "legacy-parser"
    open_alerts = 2 if repo.repo_slug == "legacy-parser" else 0
    days_since_commit = 4 if repo.language == "Python" else 40
    releases = 3 if repo.stars > 10 else 0

    return {
        "stars": repo.stars,
        "forks": repo.forks,
        "language": repo.language,
        "has_readme": True,
        "has_ci": has_ci,
        "open_alerts": open_alerts,
        "days_since_commit": days_since_commit,
        "contributors": 8 if repo.stars > 20 else 2,
        "releases": releases,
        "open_issues": 4,
        "todo_count": 3,
    }


def _build_metric_samples(scan: Scan, raw: dict) -> list[MetricSample]:
    """Создаёт MetricSample-записи, согласованные с моделями."""
    samples: list[MetricSample] = []
    for (category, metric_key, raw_key, unit,
         source_reference) in _METRIC_DEFINITIONS:
        value = raw.get(raw_key)
        is_available = value is not None
        samples.append(
            MetricSample(
                scan=scan,
                category=category,
                metric_key=metric_key,
                value=value,
                unit=unit,
                is_available=is_available,
                error_reason="" if is_available else "Данные недоступны",
                source_reference=source_reference,
            )
        )
    return samples


def _build_scores(scan: Scan, score_data: dict) -> list[HealthScore]:
    """Создаёт HealthScore-записи по категориям."""
    scores: list[HealthScore] = []
    for category, payload in score_data.items():
        scores.append(
            HealthScore(
                scan=scan,
                category=category,
                total=payload["total"],
                weight_used=payload["weight_used"],
                data_completeness=payload["data_completeness"],
                raw_metrics=payload["raw_metrics"],
            )
        )
    return scores


@shared_task
def scan_repository(repository_id: int) -> int:
    """Запускает анализ репозитория и сохраняет результат.

    Возвращает идентификатор созданного :class:`health.models.Scan`.
    """
    repo = Repository.objects.get(pk=repository_id)
    scan = Scan.objects.create(
        repository=repo,
        status=Scan.Status.RUNNING,
        triggered_by=Scan.TriggeredBy.SCHEDULE,
    )

    raw = _collect_raw(repo)
    score_data, findings = score_from_raw(raw)

    with transaction.atomic():
        scan.raw = raw
        scan.status = Scan.Status.SUCCESS
        scan.finished_at = timezone.now()
        scan.save(update_fields=["raw", "status", "finished_at"])

        MetricSample.objects.bulk_create(
            _build_metric_samples(scan, raw)
        )
        HealthScore.objects.bulk_create(
            _build_scores(scan, score_data)
        )
        if findings:
            Finding.objects.bulk_create(
                [Finding(scan=scan, **item) for item in findings]
            )

        repo.last_scanned_at = scan.finished_at
        repo.save(update_fields=["last_scanned_at"])

    return scan.id
