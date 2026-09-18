"""Клиент публичного API SourceCraft.

Модуль инкапсулирует HTTP-доступ к API SourceCraft `https://api.sourcecraft.tech`
Спецификация: `https://api.sourcecraft.tech/sourcecraft.swagger.json`
"""

from typing import Any, Iterator

from django.conf import settings

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_TIMEOUT = 15.0
DEFAULT_PAGE_SIZE = 100

# Коды ответов, при которых имеет смысл повторять запрос.
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


class SourceCraftError(RuntimeError):
    """Базовая ошибка при обращении к API SourceCraft"""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: Any | None = None
    ) -> None:
        error_txt = payload.get('message', '')
        message += f'\n{error_txt})'
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class SourceCraftClient:
    """Клиент API SourceCraft"""

    def __init__(
        self,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        if not token:
            token = settings.SOURCECRAFT_API_TOKEN
        self.access_token = token
        self.base_url = settings.SOURCECRAFT_API_BASE_URL.rstrip("/")
        self.timeout = timeout
        self.session = session or self._build_session(retries)

    @staticmethod
    def _build_session(retries: int) -> requests.Session:
        """Создаёт `requests.Session` с retry и пулом соединений"""

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
        return {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 OPR/136.0.0.0",
            "Authorization": f"Bearer {self.access_token}",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Выполняет запрос и возвращает разобранный JSON"""

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
            raise SourceCraftError(f"Ошибка при запросе {url}: {exc}") from exc

        if response.status_code >= 400:
            payload: Any
            try:
                payload = response.json()
            except ValueError:
                payload = response.text[:500]
            raise SourceCraftError(
                f"Ответ {response.status_code} для {url}",
                status_code=response.status_code,
                payload=payload,
            )

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise SourceCraftError(f"Некорректный JSON в ответе {url}") from exc

    def _fetch_page(
        self,
        path: str,
        collection_key: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        page_token: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Загружает одну страницу и возвращает (items, next_page_token)"""

        query = dict(params or {})
        query["page_size"] = page_size
        if page_token:
            query["page_token"] = page_token

        data = self._request("GET", path, params=query) or {}
        items = data.get(collection_key) or []
        return items, data.get("next_page_token")

    def _iter_pages(
        self,
        path: str,
        collection_key: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_page_token: str | None = None,
    ) -> Iterator[tuple[list[dict[str, Any]], str | None]]:
        """Итерирует страницы, отдавая (items, next_page_token).

        Внутренний метод: инкапсулирует знание о `path` и `collection_key`.
        Позволяет обрабатывать данные потоково и сохранять курсор
        (`next_page_token`) между батчами, не накапливая все страницы в памяти.
        """

        page_token = start_page_token
        while True:
            items, page_token = self._fetch_page(
                path,
                collection_key=collection_key,
                params=params,
                page_size=page_size,
                page_token=page_token,
            )
            yield items, page_token
            if not page_token:
                return

    def iter_public_repositories(
        self,
        filter_query: str | None = None,
        sort_by: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_page_token: str | None = None,
    ) -> Iterator[tuple[list[dict[str, Any]], str | None]]:
        """Итерирует страницы публичных репозиториев батчами.

        Отдаёт `(items, next_page_token)` для каждой страницы, чтобы вызывающий
        код сам решал, когда сбрасывать накопленные данные в БД, и мог сохранять
        курсор между батчами.
        """

        params: dict[str, Any] = {}
        if filter_query:
            params["filter"] = filter_query
        if sort_by:
            params["sort_by"] = sort_by
        return self._iter_pages(
            "/repos",
            collection_key="repositories",
            params=params,
            page_size=page_size,
            start_page_token=start_page_token,
        )

    def _paginate(
        self,
        path: str,
        collection_key: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Iterator[dict[str, Any]]:
        """Итерирует элементы пагинации, пока API возвращает next_page_token"""

        for items, _ in self._iter_pages(
            path,
            collection_key=collection_key,
            params=params,
            page_size=page_size,
        ):
            yield from items

    def list_public_repositories(
        self,
        filter_query: str | None = None,
        sort_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Возвращает список публичных репозиториев"""

        params: dict[str, Any] = {}
        if filter_query:
            params["filter"] = filter_query
        if sort_by:
            params["sort_by"] = sort_by
        return list(
            self._paginate(
                "/repos",
                collection_key="repositories",
                params=params,
            )
        )

    def get_repository(self, repo_id: str) -> dict[str, Any]:
        """Возвращает репозиторий по id"""

        data = self._request("GET", f"/repos/id:{repo_id}")
        return data or {}

    def get_repository_file_tree(
        self,
        repo_id: str,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Возвращает список файлов репозитория"""

        params: dict[str, Any] = {"revision": since or "HEAD"}
        return list(
            self._paginate(
                f"/repos/id:{repo_id}/trees",
                collection_key="trees",
                params=params,
            )
        )

    def get_ci_pipelines(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает запуски CI/CD"""

        return list(
            self._paginate(
                f"/repos/id:{repo_id}/cicd/runs",
                collection_key="runs",
            )
        )

    def get_appsec_findings(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает находки AppSec"""
        # TODO
        return []

    def get_issues(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает задачи репозитория"""

        return list(
            self._paginate(
                f"/repos/id:{repo_id}/issues",
                collection_key="issues",
            )
        )

    def get_merge_requests(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает pull requests репозитория"""

        return list(
            self._paginate(
                f"/repos/id:{repo_id}/pulls",
                collection_key="pull_requests",
            )
        )

    def get_contributors(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает участников репозитория"""

        return list(
            self._paginate(
                f"/repos/id:{repo_id}/contributors",
                collection_key="contributors",
            )
        )

    def get_releases(self, repo_id: str) -> list[dict[str, Any]]:
        """Возвращает релизы репозитория"""

        return list(
            self._paginate(
                f"/repos/id:{repo_id}/releases",
                collection_key="releases",
            )
        )

    def close(self) -> None:
        """Закрывает HTTP-сессию"""
        self.session.close()

    def __exit__(self, *exc_info: object) -> None:
        self.close()
