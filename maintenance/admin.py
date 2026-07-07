from django.contrib import admin

from .models import (
    Machine,
    MachinePart,
    MachineSpec,
    MaintenanceLog,
    MaintenancePlan,
    MaintenanceType,
    Part,
    Person,
)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "technological_number", "inventory_number", "brand", "location", "is_active")
    list_filter = ("is_active", "brand", "location")
    search_fields = ("name", "technological_number", "inventory_number", "brand", "location")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "is_active")
    list_filter = ("is_active", "position")
    search_fields = ("full_name", "position")


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("name", "unit")
    search_fields = ("name", "unit")


@admin.register(MachinePart)
class MachinePartAdmin(admin.ModelAdmin):
    list_display = ("machine", "part", "quantity")
    list_filter = ("machine", "part")
    autocomplete_fields = ("machine", "part")


@admin.register(MaintenanceType)
class MaintenanceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(MaintenancePlan)
class MaintenancePlanAdmin(admin.ModelAdmin):
    list_display = ("machine", "maintenance_type", "planned_date", "status")
    list_filter = ("status", "maintenance_type", "planned_date")
    autocomplete_fields = ("machine", "maintenance_type")
    search_fields = (
        "machine__name",
        "machine__technological_number",
        "machine__inventory_number",
        "maintenance_type__code",
        "maintenance_type__name",
    )
    date_hierarchy = "planned_date"


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ("machine", "maintenance_type", "performed_date", "responsible_person", "executor")
    list_filter = ("maintenance_type", "performed_date")
    autocomplete_fields = (
        "machine",
        "maintenance_type",
        "responsible_person",
        "executor",
        "related_plan",
    )
    date_hierarchy = "performed_date"


@admin.register(MachineSpec)
class MachineSpecAdmin(admin.ModelAdmin):
    list_display = ("machine",)
    autocomplete_fields = ("machine",)
