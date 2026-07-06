from django import forms

from .models import Machine, MachinePart, MachineSpec, MaintenanceLog, MaintenancePlan, MaintenanceType, Person


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


class PersonForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Person
        fields = ["full_name", "position", "is_active"]


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
        self.fields["maintenance_type"].queryset = MaintenanceType.objects.order_by("code", "name")
        self.fields["related_plan"].required = False

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
        self.fields["maintenance_type"].queryset = MaintenanceType.objects.order_by("code", "name")
