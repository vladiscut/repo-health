# Repo Health

Сервис оценки здоровья открытых репозиториев SourceCraft.
Стек: Django, шаблоны, DRF, Postgres, Redis, Celery.

## Запуск

```bash
copy .env.example .env
docker compose up --build
```

Открыть http://127.0.0.1:8002/

- список репозиториев: `/`
- карточка здоровья: `/repos/<org>/<repo>/`
- admin: `/admin/`
- API: `/api/repos/`

Демо-данные подставляются командой `seed_demo` при старте web-контейнера.

## Локально без Docker

Нужны Postgres и Redis, затем:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 8002
celery --app=config worker -B -l info
```

В `.env` для хоста укажите `POSTGRES_CONTAINER=localhost` и порты compose (`5433`, `6372`), либо поднимите только db/redis.
