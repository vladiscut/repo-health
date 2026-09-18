import logging
from datetime import datetime

from django.utils.dateparse import parse_datetime

from health.models import Repository
from integrations.sourcecraft import SourceCraftClient


logger = logging.getLogger(__name__)


def _parse_datetime(value: str | None) -> datetime | None:
    """Разбирает ISO-8601 строку в datetime"""

    if not value:
        return None
    return parse_datetime(value)


def _to_int(value: object) -> int:
    """Приводит значение к int"""

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def prepare_repository_data(payload: dict) -> dict:
    """Подготавливает данные для одного объекта JSON"""

    try:
        organization = payload.get("organization", {})
        logo = payload.get("logo", {})
        language = payload.get("language", {})
        counters = payload.get("counters", {})
        reaction = payload.get("rating", {}).get("reaction_counts", [])
        stars = [i['count'] for i in reaction if i.get("type") == "positive_low"]

        return {
            "org_slug": organization.get("slug"),
            "repo_slug": payload.get("slug"),
            "description": payload.get("description"),
            "language": language.get("name"),
            "stars": _to_int(stars[0] if stars else 0),
            "forks": _to_int(counters.get("forks")),
            "sourcecraft_id": payload.get("id"),
            "url": payload.get("web_url"),
            "logo_url": logo.get("url"),
            "is_empty": payload.get("is_empty"),
            "last_updated": _parse_datetime(payload.get("last_updated")),
            "visibility": payload.get("visibility"),
        }
    except Exception as e:
        logger.error(f"Ошибка при подготовке данных из объекта JSON: {e}")


def prepare_repositories_data(payload: list) -> list:
    """Подготавливает данные из списка JSON объектов из ответа SourceCraft API"""

    return list(
        filter(
            None,
            [prepare_repository_data(i) for i in payload]
        )
    )


def _flush_repositories(buffer: list[Repository]) -> None:
    """Сбрасывает накопленные объекты в БД и очищает буфер"""

    if not buffer:
        return

    Repository.objects.bulk_create(
        buffer,
        update_conflicts=True,
        unique_fields=["sourcecraft_id"],
        update_fields=[
            "org_slug",
            "repo_slug",
            "description",
            "language",
            "stars",
            "forks",
            "url",
            "logo_url",
            "is_empty",
            "last_updated",
            "visibility",
            "updated_at",
        ],
        batch_size=500,
    )
    buffer.clear()


def update_all_public_repositories(
    start_page_token: str | None = None,
) -> str | None:
    """Создаёт или обновляет объекты `Repository` пачками страниц

    Не собирает все страницы в память: накапливает до `pages_per_batch`
    страниц, сбрасывает их в БД и продолжает со следующей страницы

    Возвращает `next_page_token`
    """

    client = SourceCraftClient()
    buffer: list[Repository] = []
    # Сколько страниц API накапливать перед сбросом в БД
    pages_per_batch = 20  # т.е. pages_per_batch * 100 репозиториев за раз
    # Сколько страниц в пачке
    pages_in_batch = 0

    try:
        for items, next_token in client.iter_public_repositories(
            start_page_token=start_page_token,
        ):
            for item in items:
                data = prepare_repository_data(item)
                if data:
                    buffer.append(Repository(**data))

            pages_in_batch += 1
            if pages_in_batch >= pages_per_batch:
                _flush_repositories(buffer)
                return next_token

        _flush_repositories(buffer)
        return None
    finally:
        client.close()
