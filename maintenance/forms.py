from django import forms
from django.db.models import Q
from django.forms import BaseFormSet, BaseInlineFormSet, formset_factory, inlineformset_factory
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
    PartAnalyticalMapping,
    Person,
)


MAINTENANCE_LOG_TYPE_CODES = (*ALLOWED_MAINTENANCE_TYPE_CODES, "Ремонт")


def get_part_choice_label(part):
    label = f"{part.name} (#{part.pk}, {part.unit})"
    if part.description:
        label = f"{label} — {part.description}"
    return label


class PartModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return get_part_choice_label(obj)


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
    part = PartModelChoiceField(
        label="Запчастина",
        queryset=Part.objects.none(),
        empty_label="Оберіть запчастину",
    )

    class Meta:
        model = MachinePart
        fields = ["part", "quantity"]

    def __init__(self, *args, machine=None, **kwargs):
        self.machine = machine
        super().__init__(*args, **kwargs)
        self.fields["part"].queryset = Part.objects.order_by("name", "unit", "pk")

        if self.machine is not None:
            self.fields["part"].queryset = self.fields["part"].queryset.exclude(
                machine_parts__machine=self.machine
            )
        self.fields["part"].queryset = self.fields["part"].queryset.distinct()

    def clean(self):
        cleaned_data = super().clean()
        part = cleaned_data.get("part")

        if self.machine and part and self.machine.machine_parts.filter(part=part).exists():
            self.add_error("part", "Ця запчастина вже додана до машини.")

        return cleaned_data


class PartForm(BootstrapMixin, forms.ModelForm):
    has_analytical_mapping = forms.BooleanField(
        label="Аналог / комплект",
        required=False,
    )

    class Meta:
        model = Part
        fields = ["name", "unit", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.fields["has_analytical_mapping"].initial = self.instance.analytical_mappings.exists()

    def clean(self):
        cleaned_data = super().clean()
        name = (cleaned_data.get("name") or "").strip()
        unit = (cleaned_data.get("unit") or "").strip()
        description = (cleaned_data.get("description") or "").strip()
        cleaned_data["name"] = name
        cleaned_data["unit"] = unit
        cleaned_data["description"] = description

        if not name or not unit:
            return cleaned_data

        duplicate_parts = Part.objects.all()
        if self.instance.pk:
            duplicate_parts = duplicate_parts.exclude(pk=self.instance.pk)

        for part in duplicate_parts:
            if (
                part.name.strip().casefold() == name.casefold()
                and part.unit.strip().casefold() == unit.casefold()
                and (part.description or "").strip().casefold() == description.casefold()
            ):
                raise forms.ValidationError("Така запчастина вже існує.")

        return cleaned_data


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
            "performed_date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date",
                },
            ),
            "work_description": forms.Textarea(attrs={"rows": 4}),
        }

    performed_date = forms.DateField(
        label="Дата виконання",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
            },
        ),
    )

    def __init__(self, *args, machine=None, selected_plan=None, **kwargs):
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
            available_plans = ~Q(status__in=[MaintenancePlan.Status.DONE, MaintenancePlan.Status.CANCELLED])
            if self.instance.related_plan_id:
                available_plans |= Q(pk=self.instance.related_plan_id)
            if selected_plan:
                available_plans |= Q(pk=selected_plan.pk)
            active_plan_queryset = (
                MaintenancePlan.objects.filter(machine=self.machine)
                .filter(available_plans)
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
    part = PartModelChoiceField(
        label="Запчастина або матеріал",
        queryset=Part.objects.none(),
        empty_label="Оберіть запчастину або матеріал",
        required=False,
    )

    class Meta:
        model = MaintenanceLogPartUsage
        fields = ["part", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["part"].queryset = Part.objects.order_by("name", "unit", "pk").distinct()
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


class PartAnalyticalMappingForm(BootstrapMixin, forms.ModelForm):
    target_part = PartModelChoiceField(
        label="Запчастина",
        queryset=Part.objects.none(),
        empty_label="Оберіть запчастину",
        required=False,
    )

    class Meta:
        model = PartAnalyticalMapping
        fields = ["target_part", "quantity_factor"]

    def __init__(self, *args, source_part=None, **kwargs):
        self.source_part = source_part
        super().__init__(*args, **kwargs)
        queryset = Part.objects.order_by("name", "unit", "pk")
        if self.source_part and self.source_part.pk:
            queryset = queryset.exclude(pk=self.source_part.pk)
        self.fields["target_part"].queryset = queryset.distinct()
        self.fields["quantity_factor"].widget.attrs["step"] = "0.001"
        self.fields["quantity_factor"].widget.attrs["min"] = "0.001"

    def clean_quantity_factor(self):
        quantity_factor = self.cleaned_data.get("quantity_factor")
        if quantity_factor is not None and quantity_factor <= 0:
            raise forms.ValidationError("Кількість повинна бути більшою за 0.")
        return quantity_factor


class BasePartAnalyticalMappingFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["source_part"] = self.instance
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        seen_target_ids = set()
        active_mapping_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            target_part = form.cleaned_data.get("target_part")
            quantity_factor = form.cleaned_data.get("quantity_factor")

            if not target_part and quantity_factor in (None, ""):
                continue

            if not target_part or quantity_factor in (None, ""):
                raise forms.ValidationError("Для кожної відповідності потрібно обрати запчастину та вказати кількість.")

            active_mapping_count += 1

            if self.instance.pk and target_part.pk == self.instance.pk:
                raise forms.ValidationError("Запчастина не може бути аналітичною відповідністю сама до себе.")

            if target_part.pk in seen_target_ids:
                raise forms.ValidationError("Одна й та сама запчастина не може повторюватися в аналітичній відповідності.")
            seen_target_ids.add(target_part.pk)

            if (
                self.instance.pk
                and PartAnalyticalMapping.objects.filter(
                    source_part=target_part,
                    target_part=self.instance,
                )
                .exclude(pk=form.instance.pk)
                .exists()
            ):
                raise forms.ValidationError(
                    f"Некоректна циклічна відповідність: «{target_part.name}» уже зараховується до цієї запчастини."
                )

        if active_mapping_count == 0:
            raise forms.ValidationError("Для аналога або комплекту потрібно додати хоча б одну аналітичну відповідність.")


PartAnalyticalMappingFormSet = inlineformset_factory(
    Part,
    PartAnalyticalMapping,
    fk_name="source_part",
    form=PartAnalyticalMappingForm,
    formset=BasePartAnalyticalMappingFormSet,
    extra=1,
    can_delete=True,
)


class MaintenancePlanBulkRowForm(BootstrapMixin, forms.Form):
    planned_date = forms.DateField(
        label="Дата",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    machine = forms.ModelChoiceField(
        label="Обладнання",
        queryset=Machine.objects.none(),
        empty_label="Оберіть обладнання",
    )
    maintenance_type = forms.ModelChoiceField(
        label="Вид робіт / тип ТО",
        queryset=MaintenanceType.objects.none(),
        empty_label="Оберіть вид робіт",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["machine"].queryset = Machine.objects.filter(is_active=True).order_by("name", "inventory_number")
        self.fields["maintenance_type"].queryset = MaintenanceType.objects.filter(
            code__in=ALLOWED_MAINTENANCE_TYPE_CODES
        ).order_by("code", "name")


class BaseMaintenancePlanBulkFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        seen_keys = set()
        active_rows = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            planned_date = form.cleaned_data.get("planned_date")
            machine = form.cleaned_data.get("machine")
            maintenance_type = form.cleaned_data.get("maintenance_type")

            if not planned_date and not machine and not maintenance_type:
                continue

            if not planned_date or not machine or not maintenance_type:
                raise forms.ValidationError("Для кожної позиції потрібно заповнити дату, обладнання та вид робіт.")

            active_rows += 1
            row_key = (planned_date, machine.pk, maintenance_type.pk)
            if row_key in seen_keys:
                raise forms.ValidationError("У формі є дубльована позиція з однаковою датою, обладнанням і видом робіт.")
            seen_keys.add(row_key)

        if active_rows == 0:
            raise forms.ValidationError("Додайте хоча б одну позицію графіка.")


MaintenancePlanBulkFormSet = formset_factory(
    MaintenancePlanBulkRowForm,
    formset=BaseMaintenancePlanBulkFormSet,
    extra=5,
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
