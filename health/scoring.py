"""Прозрачный rule-based расчёт Repo Health Score.

Модуль не обращается к моделям Django и не пишет в БД. Функция
:func:`score_from_raw` получает словарь сырых метрик и возвращает пару:
- ``scores`` — словарь ``{категория: {total, weight_used,
  data_completeness, raw_metrics}}``;
- ``findings`` — список словарей с полями, совместимыми с моделью
  :class:`health.models.Finding`.

Ключи категорий и значения severity должны совпадать с choices моделей
:class:`health.models.MetricSample` и :class:`health.models.Finding`.
"""

from health.models import Finding, MetricSample


# Веса категорий. Сумма равна 1.0.
CATEGORY_WEIGHTS = {
    MetricSample.Category.DOCS: 0.15,
    MetricSample.Category.CI_CD: 0.25,
    MetricSample.Category.SECURITY: 0.20,
    MetricSample.Category.ACTIVITY: 0.25,
    MetricSample.Category.ISSUES: 0.10,
    MetricSample.Category.CODE_HEALTH: 0.05,
}


def _docs_score(raw: dict) -> int:
    return 80 if raw.get("has_readme") else 20


def _ci_cd_score(raw: dict) -> int:
    return 85 if raw.get("has_ci") and raw.get("releases") else 40


def _security_score(raw: dict) -> int:
    return 90 if raw.get("open_alerts", 0) == 0 else 35


def _activity_score(raw: dict) -> int:
    return 90 if raw.get("days_since_commit", 99) < 14 else 45


def _issues_score(raw: dict) -> int:
    open_issues = raw.get("open_issues")
    if open_issues is None:
        return 70
    if open_issues == 0:
        return 95
    if open_issues <= 10:
        return 75
    return 50


def _code_health_score(raw: dict) -> int:
    todo_count = raw.get("todo_count")
    if todo_count is None:
        return 65
    if todo_count <= 5:
        return 85
    if todo_count <= 20:
        return 65
    return 45


_CATEGORY_EVALUATORS = {
    MetricSample.Category.DOCS: _docs_score,
    MetricSample.Category.CI_CD: _ci_cd_score,
    MetricSample.Category.SECURITY: _security_score,
    MetricSample.Category.ACTIVITY: _activity_score,
    MetricSample.Category.ISSUES: _issues_score,
    MetricSample.Category.CODE_HEALTH: _code_health_score,
}


def _build_findings(raw: dict) -> list[dict]:
    """Создаёт список находок с severity, допустимой моделью Finding."""
    findings: list[dict] = []

    if not raw.get("has_ci"):
        findings.append(
            {
                "category": MetricSample.Category.CI_CD,
                "severity": Finding.Severity.HIGH,
                "title": "Нет CI-конфига",
                "detail": "В репозитории не найден пайплайн SourceCraft CI.",
                "recommendation": (
                    "Добавьте .sourcecraft/ci.yaml "
                    "с базовой проверкой сборки."
                ),
                "evidence_refs": [".sourcecraft/ci.yaml"],
                "estimated_score_impact": 10,
            }
        )

    if raw.get("open_alerts", 0):
        findings.append(
            {
                "category": MetricSample.Category.SECURITY,
                "severity": Finding.Severity.CRITICAL,
                "title": "Открытые AppSec-алерты",
                "detail": f"Найдено алертов: {raw['open_alerts']}.",
                "recommendation": (
                    "Закройте уязвимости зависимостей "
                    "или зафиксируйте ложные срабатывания."
                ),
                "evidence_refs": ["security/alerts"],
                "estimated_score_impact": 20,
            }
        )

    if raw.get("days_since_commit", 0) > 30:
        findings.append(
            {
                "category": MetricSample.Category.ACTIVITY,
                "severity": Finding.Severity.MEDIUM,
                "title": "Давно не было коммитов",
                "detail": (
                    f"Последняя активность "
                    f"{raw['days_since_commit']} дн. назад."
                ),
                "recommendation": (
                    "Проверьте, не заброшен ли проект, "
                    "и обновите статус в README."
                ),
                "evidence_refs": ["commits/HEAD"],
                "estimated_score_impact": 15,
            }
        )

    if not raw.get("releases"):
        findings.append(
            {
                "category": MetricSample.Category.CI_CD,
                "severity": Finding.Severity.LOW,
                "title": "Нет релизов",
                "detail": "Теги и релизы не найдены.",
                "recommendation": (
                    "Опубликуйте хотя бы один релиз, "
                    "чтобы потребители видели стабильную версию."
                ),
                "evidence_refs": ["releases"],
                "estimated_score_impact": 5,
            }
        )

    if not raw.get("has_readme"):
        findings.append(
            {
                "category": MetricSample.Category.DOCS,
                "severity": Finding.Severity.MEDIUM,
                "title": "Отсутствует README",
                "detail": "В репозитории не найден файл README.",
                "recommendation": (
                    "Добавьте README.md с описанием проекта "
                    "и инструкцией по запуску."
                ),
                "evidence_refs": ["README.md"],
                "estimated_score_impact": 8,
            }
        )

    return findings


def score_from_raw(raw: dict) -> tuple[dict, list[dict]]:
    """Считает score 0-100 по категориям.

    Возвращает ``(scores, findings)``:
    - ``scores`` — ``{категория: dict}``, где ``dict`` совместим с полями
      модели :class:`health.models.HealthScore` (без ``scan``);
    - ``findings`` — список словарей, совместимых с полями модели
      :class:`health.models.Finding` (без ``scan``).

    Значения score не зависят от LLM — только от правил.
    """
    scores: dict[str, dict] = {}
    for category, weight in CATEGORY_WEIGHTS.items():
        evaluator = _CATEGORY_EVALUATORS[category]
        total = evaluator(raw)
        scores[category] = {
            "total": total,
            "weight_used": weight,
            "data_completeness": 1.0,
            "raw_metrics": dict(raw),
        }

    findings = _build_findings(raw)
    return scores, findings
