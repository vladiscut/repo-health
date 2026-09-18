"""HTML-страницы рейтинга и карточки репозитория."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, Prefetch, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from health.models import Repository, Scan
from health.scoring import present_scores
from health.tasks import task_scan_repository

PAGE_SIZE = 50
SORTS = {
    "stars": ("-stars", F("last_updated").desc(nulls_last=True)),
    "updated": (F("last_updated").desc(nulls_last=True), "-stars"),
    "name": ("org_slug", "repo_slug"),
}


def _score_map(scan: Scan | None) -> dict[str, int | None]:
    if scan is None:
        return {}
    return {row.category: row.total for row in scan.scores.all()}


def _present(scan: Scan | None) -> dict | None:
    totals = _score_map(scan)
    if not totals:
        return None
    presented = present_scores(totals)
    if presented["total"] is None:
        return None
    return presented


def repo_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "stars")
    order = SORTS.get(sort, SORTS["stars"])

    repos = Repository.objects.filter(
        visibility=Repository.VisibilityType.PUBLIC,
    )
    if query:
        repos = repos.filter(
            Q(org_slug__icontains=query)
            | Q(repo_slug__icontains=query)
            | Q(description__icontains=query)
            | Q(language__icontains=query)
        )
    repos = repos.order_by(*order).prefetch_related(
        Prefetch(
            "scans",
            queryset=(
                Scan.objects
                .filter(status__in=[Scan.Status.SUCCESS, Scan.Status.PARTIAL])
                .prefetch_related("scores")
                .order_by("-created_at")
            ),
        )
    )

    page = Paginator(repos, PAGE_SIZE).get_page(request.GET.get("page"))
    items = []
    for repo in page:
        scan = next(iter(repo.scans.all()), None)
        items.append(
            {
                "repo": repo,
                "scan": scan,
                "score": _present(scan),
            }
        )
    return render(
        request,
        "health/repo_list.html",
        {
            "items": items,
            "page": page,
            "query": query,
            "sort": sort if sort in SORTS else "stars",
            "total_count": page.paginator.count,
        },
    )


def repo_detail(request: HttpRequest, org_slug: str, repo_slug: str) -> HttpResponse:
    repo = get_object_or_404(
        Repository,
        org_slug=org_slug,
        repo_slug=repo_slug,
    )
    scan = repo.latest_scan()
    history = []
    for item in (
        repo.scans
        .filter(status__in=[Scan.Status.SUCCESS, Scan.Status.PARTIAL])
        .prefetch_related("scores")[:12]
    ):
        presented = _present(item)
        history.append(
            {
                "finished_at": item.finished_at,
                "total": presented["total"] if presented else None,
            }
        )
    return render(
        request,
        "health/repo_detail.html",
        {
            "repo": repo,
            "scan": scan,
            "score": _present(scan),
            "findings": scan.findings.all() if scan else [],
            "history": history,
        },
    )


@require_POST
def repo_rescan(request: HttpRequest, org_slug: str, repo_slug: str) -> HttpResponse:
    repo = get_object_or_404(Repository, org_slug=org_slug, repo_slug=repo_slug)
    task_scan_repository.delay(repo.id)
    messages.info(
        request,
        "Проверка поставлена в очередь. Расчёт Score пока не подключён.",
    )
    return redirect("health:repo-detail", org_slug=org_slug, repo_slug=repo_slug)
