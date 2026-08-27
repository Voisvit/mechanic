from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.utils import OperationalError, ProgrammingError

from .models import (
    ALLOWED_MAINTENANCE_TYPE_CODES,
    Machine,
    MachinePart,
    MachineSpec,
    MaintenanceLog,
    MaintenanceLogPartUsage,
    MaintenancePlan,
    MaintenanceType,
    Part,
    Person,
)


MAINTENANCE_LOG_TYPE_CODES = (*ALLOWED_MAINTENANCE_TYPE_CODES, "Ремонт")


def ensure_repair_maintenance_type():
    try:
        MaintenanceType.objects.get_or_create(
            code="Ремонт",
            defaults={
                "name": "Ремонт",
                "description": "Позапланові або ремонтні роботи без прив'язки до плану ТО.",
            },
        )
    except (OperationalError, ProgrammingError):
        # У read-only середовищі не блокуємо рендер форми.
        pass


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            else:
                widget.attrs["class"] = "form-control"


class MachineForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Machine
        fields = [
            "name",
            "technological_number",
            "inventory_number",
            "brand",
            "location",
            "length",
            "height",
            "description",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class MachineSpecForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MachineSpec
        fields = [
            "shift_maintenance_description",
            "to1_description",
            "to2_description",
            "to3_description",
        ]
        widgets = {
            "shift_maintenance_description": forms.Textarea(attrs={"rows": 3}),
            "to1_description": forms.Textarea(attrs={"rows": 3}),
            "to2_description": forms.Textarea(attrs={"rows": 3}),
            "to3_description": forms.Textarea(attrs={"rows": 3}),
        }


class MachinePartForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MachinePart
        fields = ["part", "quantity"]

    def __init__(self, *args, machine=None, **kwargs):
        self.machine = machine
        super().__init__(*args, **kwargs)

        if self.machine is not None:
            self.fields["part"].queryset = self.fields["part"].queryset.exclude(
                machine_parts__machine=self.machine
            )

    def clean(self):
        cleaned_data = super().clean()
        part = cleaned_data.get("part")

        if self.machine and part and self.machine.machine_parts.filter(part=part).exists():
            self.add_error("part", "Ця запчастина вже додана до машини.")

        return cleaned_data


class PartForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Part
        fields = ["name", "unit", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class PersonForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Person
        fields = ["full_name", "position", "is_active"]


class MonthlyScheduleTransferForm(BootstrapMixin, forms.Form):
    source_month = forms.TypedChoiceField(label="На основі місяця", coerce=int)
    source_year = forms.IntegerField(label="Рік джерела", min_value=2000, max_value=2100)
    target_month = forms.TypedChoiceField(label="Сформувати на місяць", coerce=int)
    target_year = forms.IntegerField(label="Рік цільового місяця", min_value=2000, max_value=2100)

    def __init__(self, *args, month_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = month_choices or []
        self.fields["source_month"].choices = choices
        self.fields["target_month"].choices = choices

    def clean(self):
        cleaned_data = super().clean()
        source_year = cleaned_data.get("source_year")
        source_month = cleaned_data.get("source_month")
        target_year = cleaned_data.get("target_year")
        target_month = cleaned_data.get("target_month")

        if None in {source_year, source_month, target_year, target_month}:
            return cleaned_data

        if (source_year, source_month) >= (target_year, target_month):
            raise forms.ValidationError(
                "Місяць, на основі якого формуються події, повинен передувати цільовому місяцю."
            )

        return cleaned_data


class MaintenanceLogForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceLog
        fields = [
            "performed_date",
            "maintenance_type",
            "work_description",
            "responsible_person",
            "executor",
            "related_plan",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
            "work_description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, machine=None, **kwargs):
        self.machine = machine
        super().__init__(*args, **kwargs)
        self.fields["responsible_person"].queryset = Person.objects.filter(is_active=True).order_by("full_name")
        self.fields["executor"].queryset = Person.objects.filter(is_active=True).order_by("full_name")
        ensure_repair_maintenance_type()
        self.fields["maintenance_type"].queryset = MaintenanceType.objects.filter(
            code__in=MAINTENANCE_LOG_TYPE_CODES
        ).order_by("code", "name")
        self.fields["related_plan"].required = False
        self.fields["related_plan"].empty_label = "Позапланові роботи"

        active_plan_queryset = MaintenancePlan.objects.none()
        if self.machine is not None:
            active_plan_queryset = (
                MaintenancePlan.objects.filter(machine=self.machine)
                .exclude(status__in=[MaintenancePlan.Status.DONE, MaintenancePlan.Status.CANCELLED])
                .select_related("maintenance_type")
                .order_by("planned_date", "maintenance_type__code")
            )
        self.fields["related_plan"].queryset = active_plan_queryset

    def clean(self):
        cleaned_data = super().clean()
        related_plan = cleaned_data.get("related_plan")
        maintenance_type = cleaned_data.get("maintenance_type")

        if related_plan and self.machine and related_plan.machine_id != self.machine.id:
            self.add_error("related_plan", "Можна обрати лише планову роботу для цієї машини.")

        if related_plan and maintenance_type and related_plan.maintenance_type_id != maintenance_type.id:
            self.add_error("maintenance_type", "Вид ТО має збігатися з обраною плановою роботою.")

        return cleaned_data


class MaintenanceLogPartUsageForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceLogPartUsage
        fields = ["part", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["part"].queryset = Part.objects.order_by("name")
        self.fields["part"].empty_label = "Оберіть запчастину або матеріал"
        self.fields["quantity"].widget.attrs["step"] = "0.001"
        self.fields["quantity"].widget.attrs["min"] = "0.001"

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError("Кількість повинна бути більшою за 0.")
        return quantity


class BaseMaintenanceLogPartUsageFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        seen_part_ids = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            part = form.cleaned_data.get("part")
            quantity = form.cleaned_data.get("quantity")

            if not part and quantity in (None, ""):
                continue

            if not part or quantity in (None, ""):
                raise forms.ValidationError("Для кожного рядка потрібно обрати позицію та вказати кількість.")

            if part.pk in seen_part_ids:
                raise forms.ValidationError("Одна й та сама запчастина або матеріал не може повторюватися в одному записі.")
            seen_part_ids.add(part.pk)


MaintenanceLogPartUsageFormSet = inlineformset_factory(
    MaintenanceLog,
    MaintenanceLogPartUsage,
    form=MaintenanceLogPartUsageForm,
    formset=BaseMaintenanceLogPartUsageFormSet,
    extra=3,
    can_delete=True,
)


class MaintenancePlanForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MaintenancePlan
        fields = [
            "machine",
            "maintenance_type",
            "planned_date",
            "status",
            "note",
        ]
        widgets = {
            "planned_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["machine"].queryset = Machine.objects.filter(is_active=True).order_by("name", "inventory_number")
        self.fields["maintenance_type"].queryset = MaintenanceType.objects.filter(
            code__in=ALLOWED_MAINTENANCE_TYPE_CODES
        ).order_by("code", "name")
