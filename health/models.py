#import pgcrypto

#from django.contrib.auth.models import AbstractUser
from django.db import models

'''
class User(AbstractUser):
    """Пользователь сервиса, авторизованный через Я ID."""

    ya_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Уникальный идентификатор пользователя в Я ID",
    )
    access_token = pgcrypto.EncryptedTextField(
        null=True, blank=True, help_text="OAuth access token SourceCraft/Я ID (зашифрован)"
    )
    refresh_token = pgcrypto.EncryptedTextField(
        null=True, blank=True, help_text="OAuth refresh token SourceCraft/Я ID (зашифрован)"
    )
    token_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self) -> str:
        return self.get_full_name() or self.username


class UserRepositoryAccess(models.Model):
    """Cписок репозиториев, доступных пользователю в SourceCraft."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="repository_access"
    )
    repository = models.ForeignKey(
        "Repository", on_delete=models.CASCADE, related_name="user_access"
    )

    class Meta:
        verbose_name = "Доступ пользователя к репозиторию"
        verbose_name_plural = "Доступ пользователей к репозиториям"
        unique_together = ("user", "repository")

    def __str__(self) -> str:
        return f"{self.user} -> {self.repository}"
'''


class Repository(models.Model):
    """Репозиторий SourceCraft"""

    class VisibilityType(models.TextChoices):
        PUBLIC = "public", "public"
        INTERNAL = "internal", "internal"
        PRIVATE = "private", "private"

    org_slug = models.CharField(
        "организация",
        max_length=128,
    )
    repo_slug = models.CharField(
        "репозиторий",
        max_length=128,
    )
    description = models.TextField(
        "описание",
        blank=True,
    )
    language = models.CharField(
        "язык",
        max_length=64,
        blank=True,
    )
    stars = models.PositiveIntegerField(
        "лайки",
        default=0,
    )
    forks = models.PositiveIntegerField(
        "форки",
        default=0,
    )
    sourcecraft_id = models.CharField(
        "идентификатор SourceCraft",
        max_length=255,
        unique=True,
    )
    url = models.URLField()
    logo_url = models.URLField()
    is_empty = models.BooleanField(
        default=False
    )
    last_updated = models.DateTimeField()
    visibility = models.CharField(
        max_length=10,
        choices=VisibilityType.choices,
    )
    last_scanned_at = models.DateTimeField(
        "последняя проверка",
        null=True,
        blank=True,
    )
    #last_commit_sha_processed = models.CharField(
    #    "для инкрементального сбора истории коммитов при повторном анализе",
    #    max_length=64,
    #    blank=True,
    #)

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "репозиторий"
        verbose_name_plural = "репозитории"
        unique_together = ("org_slug", "repo_slug")
        ordering = ["org_slug", "repo_slug"]

    def __str__(self):
        return f"{self.org_slug}/{self.repo_slug}"

    def latest_scan(self):
        return self.scans.all().first()


class Scan(models.Model):
    """Один запуск анализа репозитория — неизменяемый снимок результата."""

    class Status(models.TextChoices):
        PENDING = "pending", "в очереди"
        RUNNING = "running", "идёт"
        SUCCESS = "success", "готово"
        FAILED = "failed", "ошибка"
        PARTIAL = "partial", "частично (часть данных недоступна)"

    class TriggeredBy(models.TextChoices):
        SCHEDULE = "schedule", "по расписанию"
        USER = "user", "пользователем"
        MANUAL = "manual", "вручную (management-команда)"

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name="scans",
        verbose_name="репозиторий",
    )
    status = models.CharField(
        "статус",
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(
        "создан",
        auto_now_add=True,
    )
    finished_at = models.DateTimeField(
        "завершён",
        null=True,
        blank=True,
    )
    raw = models.JSONField(
        "сырые данные",
        default=dict,
        blank=True,
    )
    error = models.TextField(
        "ошибка",
        null=True,
        blank=True,
    )
    triggered_by = models.CharField(
        "кем запущен",
        max_length=20,
        choices=TriggeredBy.choices,
    )

    '''
    triggered_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_analysis_runs",
    )
    '''
    # commit_sha_at_analysis = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "проверка"
        verbose_name_plural = "проверки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.repository} @ {self.created_at:%Y-%m-%d %H:%M}"


class MetricSample(models.Model):
    """Одна собранная метрика внутри категории для конкретного прогона анализа."""

    class Category(models.TextChoices):
        DOCS = "docs", "документация и лучшие практики"
        CI_CD = "ci_cd", "CI/CD"
        SECURITY = "security", "security"
        ACTIVITY = "activity", "активность проекта"
        ISSUES = "issues", "issues"
        CODE_HEALTH = "code_health", "состояние кода и технический долг"

    scan = models.ForeignKey(
        Scan,
        on_delete=models.CASCADE,
        related_name="metric_samples",
    )
    category = models.CharField(
        "категория",
        max_length=15,
        choices=Category.choices,
    )
    metric_key = models.CharField(
        "например: ci_success_rate_90d, readme_present, todo_count",
        max_length=100,
    )
    value = models.JSONField(
        "значение метрики (число/строка/структура) или null, если недоступно",
        null=True,
        blank=True,
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
    )
    is_available = models.BooleanField(
        "доступность",
        default=True,
        help_text="False = данные недоступны ('нет данных'), не путать со значением 0",
    )
    error_reason = models.CharField(
        "причина недоступности, если is_available=False",
        max_length=255,
        blank=True,
    )
    source_reference = models.CharField(
        "ссылка на файл/pipeline/commit/issue/MR, подтверждающая метрику",
        max_length=500,
        blank=True,
    )
    created_at = models.DateTimeField(
        "создан",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Метрика"
        verbose_name_plural = "Метрики"

    def __str__(self) -> str:
        return f"{self.scan_id}:{self.category}:{self.metric_key}"


class HealthScore(models.Model):
    scan = models.ForeignKey(
        Scan,
        on_delete=models.CASCADE,
        related_name="scores",
        verbose_name="проверка"
    )
    category = models.CharField(
        "категория",
        max_length=15,
        choices=MetricSample.Category.choices
    )
    total = models.PositiveSmallIntegerField(
        "итого",
        null=True,
        blank=True,
        help_text="0-100, null = категория помечена 'Нет данных'"
    )
    weight_used = models.FloatField(
        "вес категории, фактически применённый при расчёте (после перенормировки)"
    )
    data_completeness = models.FloatField(
        "доля доступных метрик категории, от 0.0 до 1.0",
        default=1.0,
    )
    raw_metrics = models.JSONField(
        "снимок значений метрик, использованных в расчёте",
        default=dict,
        blank=True,
    )

    class Meta:
        verbose_name = "оценка по категории"
        verbose_name_plural = "оценки по категории"
        unique_together = ("scan", "category")

    def __str__(self) -> str:
        return f"{self.scan_id}:{self.category}={self.total if self.total is not None else 'нет данных'}"


class Finding(models.Model):

    class Severity(models.TextChoices):
        LOW = "low", "low"
        MEDIUM = "medium", "medium"
        HIGH = "high", "high"
        CRITICAL = "critical", "critical"

    scan = models.ForeignKey(
        Scan,
        on_delete=models.CASCADE,
        related_name="findings",
        verbose_name="проверка",
    )
    category = models.CharField(
        "категория",
        max_length=32,
    )
    severity = models.CharField(
        "серьёзность",
        max_length=16,
        choices=Severity.choices,
    )
    title = models.CharField(
        "заголовок",
        max_length=255,
    )
    detail = models.TextField(
        "детали",
        blank=True,
    )
    recommendation = models.TextField(
        "рекомендация",
        blank=True,
    )
    evidence_refs = models.JSONField(
        "список ссылок на факты: файлы/pipeline/vulnerability/commit/issue/MR",
        default=list,
        blank=True,
    )
    estimated_score_impact = models.SmallIntegerField(
        "ожидаемый прирост Repo Health Score при устранении проблемы",
        default=0,
    )

    class Meta:
        verbose_name = "находка"
        verbose_name_plural = "находки"
        ordering = ["severity", "category"]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"
