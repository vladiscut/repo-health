"""Представления для HTML-интерфейса сервиса оценки репозиториев.

Модель :class:`health.models.HealthScore` хранит по одной записи
на категорию для каждого прогона, поэтому во всех местах используется
связь ``scan.scores`` (менеджер), а не одиночный объект.
"""

import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from health.models import Repository, Scan
from health.tasks import scan_repository

logger = logging.getLogger(__name__)


def _score_map(scan: Scan | None) -> dict[str, int | None]:
    """Возвращает словарь ``{категория: total}`` для прогона."""
    if scan is None:
        return {}
    return {
        row.category: row.total
        for row in scan.scores.all()
    }


def repo_list(request):
    repos = Repository.objects.all().prefetch_related("scans__scores")
    items = []
    for repo in repos:
        scan = repo.latest_scan()
        items.append(
            {
                "repo": repo,
                "scan": scan,
                "scores": _score_map(scan),
            }
        )
    return render(request, "health/repo_list.html", {"items": items})


def repo_detail(request, org_slug: str, repo_slug: str):
    repo = get_object_or_404(Repository, org_slug=org_slug, repo_slug=repo_slug)
    scan = repo.latest_scan()
    findings = scan.findings.all() if scan else []
    return render(
        request,
        "health/repo_detail.html",
        {
            "repo": repo,
            "scan": scan,
            "scores": _score_map(scan),
            "findings": findings,
            "history": (
                repo.scans
                .filter(status=Scan.Status.SUCCESS)
                .prefetch_related("scores")[:12]
            ),
        },
    )


@require_POST
def repo_rescan(request, org_slug: str, repo_slug: str):
    repo = get_object_or_404(Repository, org_slug=org_slug, repo_slug=repo_slug)

    # Брокер Celery может быть недоступен (например, в локальной среде).
    # В этом случае выполняем анализ синхронно, чтобы не отдавать 500.
    try:
        scan_repository.delay(repo.id)
        messages.info(request, "Проверка поставлена в очередь.")
    except Exception as exc:  # noqa: BLE001 - ловим любой сбой брокера
        logger.warning(
            "Celery broker unavailable (%s), running scan synchronously", exc
        )
        scan_repository.apply(args=[repo.id])
        messages.success(request, "Проверка выполнена.")

    return redirect("health:repo-detail", org_slug=org_slug, repo_slug=repo_slug)
