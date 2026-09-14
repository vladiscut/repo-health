from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Repository, Scan
from .tasks import scan_repository


def repo_list(request):
    repos = Repository.objects.all().prefetch_related("scans__score")
    items = []
    for repo in repos:
        scan = repo.latest_scan()
        items.append({"repo": repo, "scan": scan, "score": getattr(scan, "score", None)})
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
            "score": getattr(scan, "score", None),
            "findings": findings,
            "history": repo.scans.filter(status=Scan.Status.SUCCESS).select_related("score")[:12],
        },
    )


@require_POST
def repo_rescan(request, org_slug: str, repo_slug: str):
    repo = get_object_or_404(Repository, org_slug=org_slug, repo_slug=repo_slug)
    scan_repository.delay(repo.id)
    messages.info(request, "Проверка поставлена в очередь.")
    return redirect("repo-detail", org_slug=org_slug, repo_slug=repo_slug)
