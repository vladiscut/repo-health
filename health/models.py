from django.db import models


class Repository(models.Model):
    org_slug = models.CharField("организация", max_length=128)
    repo_slug = models.CharField("репозиторий", max_length=128)
    name = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    language = models.CharField("язык", max_length=64, blank=True)
    stars = models.PositiveIntegerField("лайки", default=0)
    forks = models.PositiveIntegerField("форки", default=0)
    last_scanned_at = models.DateTimeField("последняя проверка", null=True, blank=True)

    class Meta:
        verbose_name = "репозиторий"
        verbose_name_plural = "репозитории"
        unique_together = ("org_slug", "repo_slug")
        ordering = ["org_slug", "repo_slug"]

    def __str__(self):
        return f"{self.org_slug}/{self.repo_slug}"

    def latest_scan(self):
        return self.scans.filter(status=Scan.Status.SUCCESS).first()


class Scan(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "в очереди"
        RUNNING = "running", "идёт"
        SUCCESS = "success", "готово"
        FAILED = "failed", "ошибка"

    repository = models.ForeignKey(
        Repository, on_delete=models.CASCADE, related_name="scans", verbose_name="репозиторий"
    )
    status = models.CharField("статус", max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField("создан", auto_now_add=True)
    finished_at = models.DateTimeField("завершён", null=True, blank=True)
    raw = models.JSONField("сырые данные", default=dict, blank=True)
    error = models.TextField("ошибка", blank=True)

    class Meta:
        verbose_name = "проверка"
        verbose_name_plural = "проверки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.repository} @ {self.created_at:%Y-%m-%d %H:%M}"


class HealthScore(models.Model):
    scan = models.OneToOneField(Scan, on_delete=models.CASCADE, related_name="score", verbose_name="проверка")
    total = models.PositiveSmallIntegerField("итого", default=0)
    activity = models.PositiveSmallIntegerField("активность", default=0)
    community = models.PositiveSmallIntegerField("сообщество", default=0)
    maintenance = models.PositiveSmallIntegerField("сопровождение", default=0)
    documentation = models.PositiveSmallIntegerField("документация", default=0)
    security = models.PositiveSmallIntegerField("безопасность", default=0)

    class Meta:
        verbose_name = "оценка здоровья"
        verbose_name_plural = "оценки здоровья"

    def categories(self):
        return [
            ("Activity", self.activity),
            ("Community", self.community),
            ("Maintenance", self.maintenance),
            ("Documentation", self.documentation),
            ("Security", self.security),
        ]

    @property
    def level(self):
        if self.total >= 80:
            return "ok"
        if self.total >= 50:
            return "mid"
        return "low"


class Finding(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "info"
        WARNING = "warning", "warning"
        CRITICAL = "critical", "critical"

    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="findings", verbose_name="проверка")
    category = models.CharField("категория", max_length=32)
    severity = models.CharField("серьёзность", max_length=16, choices=Severity.choices)
    title = models.CharField("заголовок", max_length=255)
    detail = models.TextField("детали", blank=True)
    recommendation = models.TextField("рекомендация", blank=True)

    class Meta:
        verbose_name = "находка"
        verbose_name_plural = "находки"
        ordering = ["severity", "category"]
