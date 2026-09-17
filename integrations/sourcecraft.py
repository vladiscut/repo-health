"""Клиент публичного API SourceCraft.

Модуль инкапсулирует HTTP-доступ к API SourceCraft (``https://api.sourcecraft.tech``).
Спецификация: ``https://api.sourcecraft.tech/sourcecraft.swagger.json`` (Swagger 2.0).

Особенности API, учтённые в клиенте:

* База и префикс задаются вручную: в спецификации нет ``host``/``basePath``/``servers``.
* Пагинация курсорная: параметры ``page_size`` и ``page_token``, ответ содержит
  ``next_page_token``.
* Аутентификация в спецификации не объявлена, поэтому токен передаётся в заголовке
  ``Authorization: Bearer <token>`` только если он задан.
* Отдельных эндпоинтов ``/commits`` и ``/appsec`` в спецификации нет. Коммиты
  получаются через ``/repos/{org}/{repo}/trees``; находки AppSec формируются из
  запусков CI/CD (``/repos/{org}/{repo}/cicd/runs``).
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from django.conf import settings

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.sourcecraft.tech"
DEFAULT_TIMEOUT = 15.0
DEFAULT_PAGE_SIZE = 100
MAX_PAGES = 100

# Коды ответов, при которых имеет смысл повторять запрос.
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


class SourceCraftError(RuntimeError):
    """Базовая ошибка при обращении к API SourceCraft."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 payload: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class SourceCraftClient:
    """Клиент API SourceCraft.

    :param access_token: OAuth access token. Может быть ``None`` для
        анонимных запросов к публичным эндпоинтам.
    :param base_url: База API. По умолчанию ``https://api.sourcecraft.tech``.
    :param timeout: Таймаут одного запроса в секундах.
    :param retries: Число повторов при сетевых сбоях и кодах из
        :data:`RETRY_STATUS_CODES`.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.access_token = settings.SOURCECRAFT_API_TOKEN
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or self._build_session(retries)

    # ------------------------------------------------------------------ #
    # Инфраструктура
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_session(retries: int) -> requests.Session:
        """Создаёт ``requests.Session`` с retry и пулом соединений."""
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.5,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=20,
        )
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "repo-health-sourcecraft-client/1.0",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Выполняет запрос и возвращает разобранный JSON."""
        url = f"{self.base_url}{path}"
        clean_params = {
            key: value for key, value in (params or {}).items()
            if value is not None
        }
        try:
            response = self.session.request(
                method,
                url,
                params=clean_params or None,
                json=json_body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SourceCraftError(f"Ошибка сети при запросе {url}: {exc}") from exc

        if response.status_code >= 400:
            payload: Any
            try:
                payload = response.json()
            except ValueError:
                payload = response.text[:500]
            raise SourceCraftError(
                f"SourceCraft вернул {response.status_code} для {url}",
                status_code=response.status_code,
                payload=payload,
            )

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise SourceCraftError(f"Некорректный JSON в ответе {url}") from exc

    def _paginate(
        self,
        path: str,
        *,
        collection_key: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = MAX_PAGES,
    ) -> Iterator[dict[str, Any]]:
        """Итерирует элементы курсорной пагинации."""
        page_token: str | None = None
        for _ in range(max_pages):
            query = dict(params or {})
            query["page_size"] = page_size
            if page_token:
                query["page_token"] = page_token

            data = self._request("GET", path, params=query) or {}
            items = data.get(collection_key) or []
            yield from items

            page_token = data.get("next_page_token")
            if not page_token:
                return

    # ------------------------------------------------------------------ #
    # Репозитории
    # ------------------------------------------------------------------ #
    def list_public_repositories(
        self,
        *,
        filter_query: str | None = None,
        sort_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Возвращает список публичных репозиториев (``GET /repos``)."""
        params: dict[str, Any] = {}
        if filter_query:
            params["filter"] = filter_query
        if sort_by:
            params["sort_by"] = sort_by
        return list(
            self._paginate("/repos", collection_key="repositories", params=params)
        )

    def get_repository(self, repo_id: str) -> dict[str, Any]:
        """Возвращает репозиторий по строке ``org_slug/repo_slug``.

        :param repo_id: Идентификатор вида ``org_slug/repo_slug`` либо просто
            ``repo_slug``.
        """
        org_slug, repo_slug = self._split_repo_id(repo_id)
        data = self._request("GET", f"/repos/{org_slug}/{repo_slug}")
        return data or {}

    # ------------------------------------------------------------------ #
    # Коммиты
    # ------------------------------------------------------------------ #
    def get_commits(
        self,
        repo_id: str,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Возвращает список коммитов (элементов дерева) репозитория.

        Отдельного эндпоинта коммитов в API нет. Используется ``GET
        /repos/{org}/{repo}/trees`` по ревизии ``since`` (или ``HEAD``, если
        ``since`` не задан).

        :param since: Ревизия (SHA, имя ветки или тега), с которой начинается
            обход. Параметр API ``since`` как фильтр по дате отсутствует.
        """
        org_slug, repo_slug = self._split_repo_id(repo_id)
        params: dict[str, Any] = {"revision": since or "HEAD"}
        return list(
            self._paginate(
                f"/repos/{org_slug}/{repo_slug}/trees",
                collection_key="trees",
                params=params,
            )
        )

    # ------------------------------------------------------------------ #
    # CI/CD
    # ------------------------------------------------------------------ #
    def get_ci_pipelines(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает запуски CI/CD (``GET /repos/{org}/{repo}/cicd/runs``)."""
        org_slug, repo_slug = self._split_repo_id(repo_id)
        return list(
            self._paginate(
                f"/repos/{org_slug}/{repo_slug}/cicd/runs",
                collection_key="runs",
            )
        )

    def get_appsec_findings(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает находки AppSec.

        В спецификации SourceCraft нет отдельного эндпоинта AppSec. Находки
        выводятся из артефактов и логов CI/CD-запусков, поэтому метод собирает
        запуски CI/CD и оставляет только те, что помечены как относящиеся к
        безопасности.

        :returns: Список словарей с запусками CI/CD, имеющими отношение к
            безопасности. Если таких нет — пустой список.
        """
        findings: list[dict[str, Any]] = []
        for run in self.get_ci_pipelines(repo_id):
            haystack = " ".join(
                str(run.get(key, "")).lower()
                for key in ("slug", "name", "workflow_slug", "status")
            )
            if any(
                marker in haystack
                for marker in ("sec", "sast", "dast", "vuln", "appsec")
            ):
                findings.append(run)
        return findings

    # ------------------------------------------------------------------ #
    # Issues, pull requests, участники, релизы
    # ------------------------------------------------------------------ #
    def get_issues(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает задачи репозитория (``/repos/{org}/{repo}/issues``)."""
        org_slug, repo_slug = self._split_repo_id(repo_id)
        return list(
            self._paginate(
                f"/repos/{org_slug}/{repo_slug}/issues",
                collection_key="issues",
            )
        )

    def get_merge_requests(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает pull requests (``/repos/{org}/{repo}/pulls``).

        В SourceCraft pull request — аналог merge request.
        """
        org_slug, repo_slug = self._split_repo_id(repo_id)
        return list(
            self._paginate(
                f"/repos/{org_slug}/{repo_slug}/pulls",
                collection_key="pulls",
            )
        )

    def get_contributors(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает участников репозитория (``/contributors``)."""
        org_slug, repo_slug = self._split_repo_id(repo_id)
        return list(
            self._paginate(
                f"/repos/{org_slug}/{repo_slug}/contributors",
                collection_key="contributors",
            )
        )

    def get_releases(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает релизы репозитория (``/repos/{org}/{repo}/releases``)."""
        org_slug, repo_slug = self._split_repo_id(repo_id)
        return list(
            self._paginate(
                f"/repos/{org_slug}/{repo_slug}/releases",
                collection_key="releases",
            )
        )

    # ------------------------------------------------------------------ #
    # Утилиты
    # ------------------------------------------------------------------ #
    @staticmethod
    def _split_repo_id(repo_id: str) -> tuple[str, str]:
        """Разбирает ``repo_id`` на ``(org_slug, repo_slug)``.

        Принимает ``org_slug/repo_slug``, ``id:<repo_id>`` или одиночный slug.
        """
        value = (repo_id or "").strip().strip("/")
        if not value:
            raise ValueError("repo_id не может быть пустым")
        if value.startswith("id:"):
            raise ValueError(
                "repo_id вида 'id:<id>' не поддерживается: используйте "
                "'org_slug/repo_slug'"
            )
        if "/" in value:
            org_slug, repo_slug = value.split("/", 1)
            if org_slug and repo_slug:
                return org_slug, repo_slug
        raise ValueError(
            f"repo_id должен иметь вид 'org_slug/repo_slug', получено: {repo_id!r}"
        )

    def close(self) -> None:
        """Закрывает HTTP-сессию."""
        self.session.close()

    def __enter__(self) -> "SourceCraftClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
