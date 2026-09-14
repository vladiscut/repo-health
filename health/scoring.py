def score_from_raw(raw: dict) -> tuple[dict, list[dict]]:
    """Прозрачный rule-based score 0-100. LLM сюда не ходит."""
    activity = 90 if raw.get("days_since_commit", 99) < 14 else 45
    community = min(100, 40 + raw.get("contributors", 0) * 6 + raw.get("stars", 0))
    maintenance = 85 if raw.get("has_ci") and raw.get("releases", 0) else 40
    documentation = 80 if raw.get("has_readme") else 20
    security = 90 if raw.get("open_alerts", 0) == 0 else 35

    weights = {
        "activity": 0.25,
        "community": 0.15,
        "maintenance": 0.25,
        "documentation": 0.15,
        "security": 0.20,
    }
    total = round(
        activity * weights["activity"]
        + community * weights["community"]
        + maintenance * weights["maintenance"]
        + documentation * weights["documentation"]
        + security * weights["security"]
    )

    findings = []
    if not raw.get("has_ci"):
        findings.append(
            {
                "category": "Maintenance",
                "severity": "warning",
                "title": "Нет CI-конфига",
                "detail": "В репозитории не найден пайплайн SourceCraft CI.",
                "recommendation": "Добавьте .sourcecraft/ci.yaml с базовой проверкой сборки.",
            }
        )
    if raw.get("open_alerts", 0):
        findings.append(
            {
                "category": "Security",
                "severity": "critical",
                "title": "Открытые AppSec-алерты",
                "detail": f"Найдено алертов: {raw['open_alerts']}.",
                "recommendation": "Закройте уязвимости зависимостей или зафиксируйте ложные срабатывания.",
            }
        )
    if raw.get("days_since_commit", 0) > 30:
        findings.append(
            {
                "category": "Activity",
                "severity": "warning",
                "title": "Давно не было коммитов",
                "detail": f"Последняя активность {raw['days_since_commit']} дн. назад.",
                "recommendation": "Проверьте, не заброшен ли проект, и обновите статус в README.",
            }
        )
    if not raw.get("releases"):
        findings.append(
            {
                "category": "Maintenance",
                "severity": "info",
                "title": "Нет релизов",
                "detail": "Теги и релизы не найдены.",
                "recommendation": "Опубликуйте хотя бы один релиз, чтобы потребители видели стабильную версию.",
            }
        )

    return (
        {
            "total": total,
            "activity": activity,
            "community": min(100, community),
            "maintenance": maintenance,
            "documentation": documentation,
            "security": security,
        },
        findings,
    )
