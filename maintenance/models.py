from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


ALLOWED_MAINTENANCE_TYPE_CODES = (
    "ТО-1",
    "ТО-2",
    "ТО-3",
    "КР",
    "СР",
    "ПР",
)


class ActiveModelMixin(models.Model):
    is_active = models.BooleanField("Активний", default=True)

    class Meta:
        abstract = True


class Machine(ActiveModelMixin):
    name = models.CharField("Назва", max_length=255)
    technological_number = models.CharField("Технологічний номер", max_length=100, blank=True)
    inventory_number = models.CharField("Інвентарний номер", max_length=100, blank=True)
    brand = models.CharField("Марка / виробник", max_length=255, blank=True)
    location = models.CharField("Розташування", max_length=255, blank=True)
    length = models.DecimalField("Довжина", max_digits=10, decimal_places=2, null=True, blank=True)
    height = models.DecimalField("Висота", max_digits=10, decimal_places=2, null=True, blank=True)
    description = models.TextField("Опис", blank=True)

    class Meta:
        verbose_name = "Обладнання"
        verbose_name_plural = "Обладнання"
        ordering = ["name", "inventory_number"]

    def __str__(self):
        if self.inventory_number:
            return f"{self.name} ({self.inventory_number})"
        return self.name


class Person(ActiveModelMixin):
    class Position(models.TextChoices):
        CHIEF_ENGINEER = "chief_engineer", "головний інженер"
        PREPARATION_SECTION_HEAD = "preparation_section_head", "начальник підготовчої дільниці"
        MECHANIC = "mechanic", "механік"
        LOCKSMITH = "locksmith", "слюсар"
        OTHER = "other", "інше"

    full_name = models.CharField("ПІБ", max_length=255)
    position = models.CharField(
        "Посада",
        max_length=50,
        choices=Position.choices,
        blank=True,
    )

    class Meta:
        verbose_name = "Особа"
        verbose_name_plural = "Особи"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Part(models.Model):
    name = models.CharField("Назва", max_length=255)
    unit = models.CharField("Одиниця виміру", max_length=50)
    description = models.TextField("Опис", blank=True)

    class Meta:
        verbose_name = "Запчастина"
        verbose_name_plural = "Запчастини"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.unit})"


class PartAnalyticalMapping(models.Model):
    source_part = models.ForeignKey(
        Part,
        verbose_name="Фактично використана запчастина",
        on_delete=models.CASCADE,
        related_name="analytical_mappings",
    )
    target_part = models.ForeignKey(
        Part,
        verbose_name="Аналітична відповідність",
        on_delete=models.PROTECT,
        related_name="analytical_mapping_targets",
    )
    quantity_factor = models.DecimalField(
        "Кількість",
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    class Meta:
        verbose_name = "Аналітична відповідність запчастини"
        verbose_name_plural = "Аналітичні відповідності запчастин"
        unique_together = ("source_part", "target_part")
        ordering = ["source_part__name", "target_part__name"]

    def __str__(self):
        return f"{self.source_part} -> {self.target_part} x {self.quantity_factor}"


class MachinePart(models.Model):
    machine = models.ForeignKey(
        Machine,
        verbose_name="Обладнання",
        on_delete=models.CASCADE,
        related_name="machine_parts",
    )
    part = models.ForeignKey(
        Part,
        verbose_name="Запчастина",
        on_delete=models.CASCADE,
        related_name="machine_parts",
    )
    quantity = models.DecimalField("Кількість", max_digits=10, decimal_places=2, default=1)

    class Meta:
        verbose_name = "Запчастина обладнання"
        verbose_name_plural = "Запчастини обладнання"
        unique_together = ("machine", "part")
        ordering = ["machine__name", "part__name"]

    def __str__(self):
        return f"{self.machine} - {self.part}: {self.quantity}"


class MaintenanceType(models.Model):
    code = models.CharField("Код", max_length=50, unique=True)
    name = models.CharField("Назва", max_length=255)
    description = models.TextField("Опис", blank=True)

    class Meta:
        verbose_name = "Тип ТО"
        verbose_name_plural = "Типи ТО"
        ordering = ["code", "name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class MaintenancePlan(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Заплановано"
        DONE = "done", "Виконано"
        OVERDUE = "overdue", "Прострочено"
        CANCELLED = "cancelled", "Скасовано"

    machine = models.ForeignKey(
        Machine,
        verbose_name="Обладнання",
        on_delete=models.CASCADE,
        related_name="maintenance_plans",
    )
    maintenance_type = models.ForeignKey(
        MaintenanceType,
        verbose_name="Тип ТО",
        on_delete=models.PROTECT,
        related_name="maintenance_plans",
    )
    planned_date = models.DateField("Запланована дата")
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    note = models.TextField("Примітка", blank=True)

    class Meta:
        verbose_name = "План ТО"
        verbose_name_plural = "Плани ТО"
        ordering = ["planned_date", "machine__name"]

    def __str__(self):
        return f"{self.machine} - {self.maintenance_type} на {self.planned_date}"


class MaintenanceLog(models.Model):
    machine = models.ForeignKey(
        Machine,
        verbose_name="Обладнання",
        on_delete=models.CASCADE,
        related_name="maintenance_logs",
    )
    maintenance_type = models.ForeignKey(
        MaintenanceType,
        verbose_name="Тип ТО",
        on_delete=models.PROTECT,
        related_name="maintenance_logs",
    )
    performed_date = models.DateField("Дата виконання")
    work_description = models.TextField("Опис виконаних робіт")
    responsible_person = models.ForeignKey(
        Person,
        verbose_name="Відповідальна особа",
        on_delete=models.PROTECT,
        related_name="responsible_maintenance_logs",
        limit_choices_to={"is_active": True},
    )
    executor = models.ForeignKey(
        Person,
        verbose_name="Виконавець",
        on_delete=models.PROTECT,
        related_name="executed_maintenance_logs",
        limit_choices_to={"is_active": True},
    )
    related_plan = models.ForeignKey(
        MaintenancePlan,
        verbose_name="Пов'язаний план",
        on_delete=models.SET_NULL,
        related_name="maintenance_logs",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Журнал ТО"
        verbose_name_plural = "Журнал ТО"
        ordering = ["-performed_date", "-created_at"]

    def __str__(self):
        return f"{self.machine} - {self.maintenance_type} ({self.performed_date})"


class MaintenanceLogPartUsage(models.Model):
    maintenance_log = models.ForeignKey(
        MaintenanceLog,
        verbose_name="Запис про виконані роботи",
        on_delete=models.CASCADE,
        related_name="used_parts",
    )
    part = models.ForeignKey(
        Part,
        verbose_name="Запчастина або матеріал",
        on_delete=models.PROTECT,
        related_name="maintenance_log_usages",
    )
    quantity = models.DecimalField(
        "Використана кількість",
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    class Meta:
        verbose_name = "Використана запчастина або матеріал"
        verbose_name_plural = "Використані запчастини та матеріали"
        unique_together = ("maintenance_log", "part")
        ordering = ["part__name"]

    def __str__(self):
        return f"{self.maintenance_log} - {self.part}: {self.quantity}"


class MachineSpec(models.Model):
    machine = models.OneToOneField(
        Machine,
        verbose_name="Обладнання",
        on_delete=models.CASCADE,
        related_name="specification",
    )
    shift_maintenance_description = models.TextField("Опис щозмінного обслуговування", blank=True)
    to1_description = models.TextField("Опис ТО-1", blank=True)
    to2_description = models.TextField("Опис ТО-2", blank=True)
    to3_description = models.TextField("Опис ТО-3", blank=True)

    class Meta:
        verbose_name = "Специфікація обладнання"
        verbose_name_plural = "Специфікації обладнання"
        ordering = ["machine__name"]

    def __str__(self):
        return f"Специфікація: {self.machine}"
