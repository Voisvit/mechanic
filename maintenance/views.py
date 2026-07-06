import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth import logout
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    MachineForm,
    MachinePartForm,
    MachineSpecForm,
    MaintenanceLogForm,
    MaintenancePlanForm,
    PersonForm,
)
from .models import Machine, MachinePart, MaintenanceLog, MaintenancePlan, MaintenanceType, Person


SYSTEM_NAME = "Журнал технічного обслуговування обладнання"


def build_context(page_title, **kwargs):
    return {
        "page_title": page_title,
        "system_name": SYSTEM_NAME,
        **kwargs,
    }


def build_print_context(document_title, **kwargs):
    return {
        "document_title": document_title,
        "generated_at": timezone.localdate(),
        "system_name": SYSTEM_NAME,
        **kwargs,
    }


def logout_view(request):
    logout(request)
    return redirect("login")


def get_month_choices():
    return get_month_choices_uk()


def get_year_choices(base_year):
    return [base_year - 1, base_year, base_year + 1]


def get_month_choices_uk():
    return [
        (1, "Січень"),
        (2, "Лютий"),
        (3, "Березень"),
        (4, "Квітень"),
        (5, "Травень"),
        (6, "Червень"),
        (7, "Липень"),
        (8, "Серпень"),
        (9, "Вересень"),
        (10, "Жовтень"),
        (11, "Листопад"),
        (12, "Грудень"),
    ]


def get_month_label_uk(month_number):
    for value, label in get_month_choices_uk():
        if value == month_number:
            return label
    return str(month_number)


def get_effective_plan_status(plan, today):
    if plan.status == MaintenancePlan.Status.DONE:
        return MaintenancePlan.Status.DONE
    if plan.status == MaintenancePlan.Status.CANCELLED:
        return MaintenancePlan.Status.CANCELLED
    if plan.planned_date < today:
        return MaintenancePlan.Status.OVERDUE
    return plan.status


def build_monthly_schedule_context(year, month, today, selected_machine="", include_inactive_with_activity=False):
    days_in_month = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    machine_activity_ids = set()
    if include_inactive_with_activity:
        machine_activity_ids.update(
            MaintenancePlan.objects.filter(planned_date__range=(start_date, end_date)).values_list("machine_id", flat=True)
        )
        machine_activity_ids.update(
            MaintenanceLog.objects.filter(performed_date__range=(start_date, end_date)).values_list("machine_id", flat=True)
        )

    machines_queryset = Machine.objects.filter(is_active=True)
    if include_inactive_with_activity and machine_activity_ids:
        machines_queryset = Machine.objects.filter(Q(is_active=True) | Q(id__in=machine_activity_ids))

    machines_queryset = machines_queryset.order_by("name", "inventory_number")
    if selected_machine:
        if include_inactive_with_activity:
            machines_queryset = Machine.objects.filter(pk=selected_machine)
        else:
            machines_queryset = machines_queryset.filter(pk=selected_machine)
    machines = list(machines_queryset)

    plans_queryset = MaintenancePlan.objects.filter(planned_date__range=(start_date, end_date))
    if not include_inactive_with_activity:
        plans_queryset = plans_queryset.filter(machine__is_active=True)

    plans = (
        plans_queryset
        .exclude(status=MaintenancePlan.Status.CANCELLED)
        .select_related("machine", "maintenance_type")
        .order_by("planned_date", "maintenance_type__code")
    )
    if selected_machine:
        plans = plans.filter(machine_id=selected_machine)

    plans_by_machine_day = {}
    for plan in plans:
        plans_by_machine_day.setdefault((plan.machine_id, plan.planned_date.day), []).append(plan)

    schedule_rows = []
    for index, machine in enumerate(machines, start=1):
        cells = []
        monthly_codes = []
        done_count = 0
        overdue_count = 0

        for day in range(1, days_in_month + 1):
            day_plans = plans_by_machine_day.get((machine.id, day), [])
            codes = ", ".join(plan.maintenance_type.code for plan in day_plans)
            status_class = ""
            effective_statuses = [get_effective_plan_status(plan, today) for plan in day_plans]

            if any(status == MaintenancePlan.Status.OVERDUE for status in effective_statuses):
                status_class = "schedule-cell-overdue"
                overdue_count += sum(
                    1 for status in effective_statuses if status == MaintenancePlan.Status.OVERDUE
                )
            elif any(status == MaintenancePlan.Status.DONE for status in effective_statuses):
                status_class = "schedule-cell-done"
                done_count += sum(
                    1 for status in effective_statuses if status == MaintenancePlan.Status.DONE
                )

            monthly_codes.extend(plan.maintenance_type.code for plan in day_plans)
            cells.append(
                {
                    "day": day,
                    "codes": codes,
                    "status_class": status_class,
                    "title": "; ".join(
                        f"{plan.maintenance_type.code}: {dict(MaintenancePlan.Status.choices)[get_effective_plan_status(plan, today)]}"
                        for plan in day_plans
                    ),
                    "actions": [
                        {
                            "label": "Відмітити виконання",
                            "url": reverse("maintenance_log_create", kwargs={"pk": machine.pk})
                            + f"?maintenance_type={plan.maintenance_type_id}&related_plan={plan.pk}",
                        }
                        for plan in day_plans
                        if get_effective_plan_status(plan, today) != MaintenancePlan.Status.DONE
                    ],
                }
            )

        unique_codes = []
        for code in monthly_codes:
            if code not in unique_codes:
                unique_codes.append(code)

        notes = []
        if done_count:
            notes.append(f"Виконано: {done_count}")
        if overdue_count:
            notes.append(f"Прострочено: {overdue_count}")

        schedule_rows.append(
            {
                "index": index,
                "machine": machine,
                "repair_types": ", ".join(unique_codes) or "-",
                "cells": cells,
                "notes": " | ".join(notes) or "-",
            }
        )

    return {
        "selected_month": month,
        "selected_year": year,
        "selected_machine": selected_machine,
        "month_choices": get_month_choices(),
        "year_choices": get_year_choices(today.year),
        "machines_for_filter": Machine.objects.filter(is_active=True).order_by("name", "inventory_number"),
        "days": range(1, days_in_month + 1),
        "days_in_month": days_in_month,
        "month_name": get_month_label_uk(month),
        "schedule_rows": schedule_rows,
    }


def build_parts_list_context(search_query="", selected_machine=""):
    machine_parts = (
        MachinePart.objects.select_related("machine", "part")
        .filter(machine__is_active=True)
        .order_by("part__name", "machine__name", "machine__inventory_number")
    )

    if search_query:
        machine_parts = machine_parts.filter(part__name__icontains=search_query)

    if selected_machine:
        machine_parts = machine_parts.filter(machine_id=selected_machine)

    grouped_parts = {}
    for machine_part in machine_parts:
        part_id = machine_part.part_id
        if part_id not in grouped_parts:
            grouped_parts[part_id] = {
                "part": machine_part.part,
                "total_quantity": 0,
                "machines": [],
            }

        grouped_parts[part_id]["total_quantity"] += machine_part.quantity
        grouped_parts[part_id]["machines"].append(machine_part.machine)

    part_rows = []
    for index, item in enumerate(grouped_parts.values(), start=1):
        unique_machines = []
        seen_machine_ids = set()
        for machine in item["machines"]:
            if machine.id not in seen_machine_ids:
                unique_machines.append(machine)
                seen_machine_ids.add(machine.id)

        part_rows.append(
            {
                "index": index,
                "part": item["part"],
                "total_quantity": item["total_quantity"],
                "machines": unique_machines,
            }
        )

    return {
        "part_rows": part_rows,
        "search_query": search_query,
        "selected_machine": selected_machine,
        "machines": Machine.objects.filter(is_active=True).order_by("name", "inventory_number"),
    }


def home(request):
    today = timezone.localdate()
    selected_year = request.GET.get("year", str(today.year))
    selected_month = request.GET.get("month", str(today.month))

    try:
        year = int(selected_year)
        month = int(selected_month)
        if month < 1 or month > 12:
            raise ValueError
    except ValueError:
        year = today.year
        month = today.month

    month_label = get_month_label_uk(month)
    document_heading = (
        "Графік проведення планово-попереджувального ремонту та технічного "
        f"обслуговування обладнання підготовчої дільниці №2 на {month_label} {year} року"
    )

    return render(
        request,
        "schedule.html",
        build_context(
            document_heading,
            **build_monthly_schedule_context(year, month, today),
            home_mode=True,
            schedule_heading=document_heading,
        ),
    )


def equipment(request):
    search_query = request.GET.get("q", "").strip()
    machines = Machine.objects.filter(is_active=True)

    if search_query:
        machines = machines.filter(
            Q(name__icontains=search_query) | Q(inventory_number__icontains=search_query)
        )

    machines = machines.order_by("name", "inventory_number")

    return render(
        request,
        "equipment.html",
        build_context(
            "Обладнання",
            machines=machines,
            search_query=search_query,
            inactive_count=Machine.objects.filter(is_active=False).count(),
        ),
    )


def inactive_equipment(request):
    search_query = request.GET.get("q", "").strip()
    machines = Machine.objects.filter(is_active=False)

    if search_query:
        machines = machines.filter(
            Q(name__icontains=search_query) | Q(inventory_number__icontains=search_query)
        )

    machines = machines.order_by("name", "inventory_number")

    return render(
        request,
        "inactive_equipment.html",
        build_context(
            "Неактивні машини",
            machines=machines,
            search_query=search_query,
        ),
    )


def machine_create(request):
    if request.method == "POST":
        form = MachineForm(request.POST)
        if form.is_valid():
            machine = form.save()
            return redirect("machine_detail", pk=machine.pk)
    else:
        form = MachineForm(initial={"is_active": True})

    return render(
        request,
        "machine_form.html",
        build_context(
            "Додати машину",
            form=form,
            form_title="Додати машину",
            back_url=reverse("equipment"),
            cancel_url=reverse("equipment"),
        ),
    )


def machine_update(request, pk):
    machine = get_object_or_404(Machine, pk=pk)

    if request.method == "POST":
        form = MachineForm(request.POST, instance=machine)
        if form.is_valid():
            machine = form.save()
            return redirect("machine_detail", pk=machine.pk)
    else:
        form = MachineForm(instance=machine)

    detail_url = reverse("machine_detail", kwargs={"pk": machine.pk})
    return render(
        request,
        "machine_form.html",
        build_context(
            "Редагувати машину",
            machine=machine,
            form=form,
            form_title="Редагувати машину",
            back_url=detail_url,
            cancel_url=detail_url,
        ),
    )


def machine_deactivate(request, pk):
    machine = get_object_or_404(Machine, pk=pk)
    detail_url = reverse("machine_detail", kwargs={"pk": machine.pk})

    if request.method == "POST":
        machine.is_active = False
        machine.save(update_fields=["is_active"])
        messages.success(request, "Машину деактивовано")
        return redirect("equipment")

    return render(
        request,
        "machine_deactivate_confirm.html",
        build_context(
            "Деактивувати машину",
            machine=machine,
            back_url=detail_url,
            cancel_url=detail_url,
        ),
    )


def machine_restore(request, pk):
    machine = get_object_or_404(Machine, pk=pk, is_active=False)

    if request.method == "POST":
        machine.is_active = True
        machine.save(update_fields=["is_active"])
        messages.success(request, "Машину відновлено")
        return redirect("inactive_equipment")

    return render(
        request,
        "machine_restore_confirm.html",
        build_context(
            "Відновити машину",
            machine=machine,
            back_url=reverse("inactive_equipment"),
            cancel_url=reverse("inactive_equipment"),
        ),
    )


def machine_detail(request, pk):
    machine = get_object_or_404(
        Machine.objects.prefetch_related(
            "maintenance_logs__maintenance_type",
            "maintenance_logs__responsible_person",
            "maintenance_logs__executor",
        ),
        pk=pk,
    )
    maintenance_logs = machine.maintenance_logs.select_related(
        "maintenance_type",
        "responsible_person",
        "executor",
    ).all()

    return render(
        request,
        "machine_detail.html",
        build_context(
            "Справа машини",
            machine=machine,
            maintenance_logs=maintenance_logs,
            back_url=reverse("equipment"),
        ),
    )


def machine_detail_print(request, pk):
    machine = get_object_or_404(
        Machine.objects.prefetch_related(
            "maintenance_logs__maintenance_type",
            "maintenance_logs__responsible_person",
            "maintenance_logs__executor",
        ),
        pk=pk,
    )
    maintenance_logs = machine.maintenance_logs.select_related(
        "maintenance_type",
        "responsible_person",
        "executor",
    ).all()

    return render(
        request,
        "print_machine_detail.html",
        build_print_context(
            f"Справа машини: {machine.name}",
            machine=machine,
            maintenance_logs=maintenance_logs,
        ),
    )


def maintenance_log_create(request, pk):
    machine = get_object_or_404(Machine, pk=pk, is_active=True)

    if request.method == "POST":
        form = MaintenanceLogForm(request.POST, machine=machine)
        if form.is_valid():
            maintenance_log = form.save(commit=False)
            maintenance_log.machine = machine
            maintenance_log.save()
            if maintenance_log.related_plan:
                maintenance_log.related_plan.status = MaintenancePlan.Status.DONE
                maintenance_log.related_plan.save(update_fields=["status"])
            return redirect("machine_detail", pk=machine.pk)
    else:
        initial = {"performed_date": timezone.localdate()}
        related_plan_id = request.GET.get("related_plan")
        maintenance_type_id = request.GET.get("maintenance_type")

        if related_plan_id:
            related_plan = get_object_or_404(
                MaintenancePlan.objects.exclude(
                    status__in=[MaintenancePlan.Status.DONE, MaintenancePlan.Status.CANCELLED]
                ),
                pk=related_plan_id,
                machine=machine,
            )
            initial["related_plan"] = related_plan
            initial["maintenance_type"] = related_plan.maintenance_type
        elif maintenance_type_id:
            initial["maintenance_type"] = maintenance_type_id

        form = MaintenanceLogForm(initial=initial, machine=machine)

    detail_url = reverse("machine_detail", kwargs={"pk": machine.pk})
    return render(
        request,
        "maintenance_log_form.html",
        build_context(
            "Додати запис про виконані роботи",
            machine=machine,
            form=form,
            form_title="Додати запис про виконані роботи",
            back_url=detail_url,
            cancel_url=detail_url,
        ),
    )


def maintenance_log_update(request, pk, log_pk):
    machine = get_object_or_404(Machine, pk=pk, is_active=True)
    maintenance_log = get_object_or_404(MaintenanceLog, pk=log_pk, machine=machine)

    if request.method == "POST":
        form = MaintenanceLogForm(request.POST, instance=maintenance_log, machine=machine)
        if form.is_valid():
            maintenance_log = form.save()
            if maintenance_log.related_plan:
                maintenance_log.related_plan.status = MaintenancePlan.Status.DONE
                maintenance_log.related_plan.save(update_fields=["status"])
            return redirect("machine_detail", pk=machine.pk)
    else:
        form = MaintenanceLogForm(instance=maintenance_log, machine=machine)

    detail_url = reverse("machine_detail", kwargs={"pk": machine.pk})
    return render(
        request,
        "maintenance_log_form.html",
        build_context(
            "Редагувати запис про виконані роботи",
            machine=machine,
            maintenance_log=maintenance_log,
            form=form,
            form_title="Редагувати запис про виконані роботи",
            back_url=detail_url,
            cancel_url=detail_url,
        ),
    )


def maintenance_log_delete(request, pk, log_pk):
    machine = get_object_or_404(Machine, pk=pk, is_active=True)
    maintenance_log = get_object_or_404(MaintenanceLog, pk=log_pk, machine=machine)
    detail_url = reverse("machine_detail", kwargs={"pk": machine.pk})

    if request.method == "POST":
        maintenance_log.delete()
        return redirect("machine_detail", pk=machine.pk)

    return render(
        request,
        "maintenance_log_delete_confirm.html",
        build_context(
            "Видалити запис про виконані роботи",
            machine=machine,
            maintenance_log=maintenance_log,
            back_url=detail_url,
            cancel_url=detail_url,
        ),
    )


def machine_specification(request, pk):
    machine = get_object_or_404(
        Machine.objects.select_related("specification").prefetch_related("machine_parts__part"),
        pk=pk,
    )
    specification = getattr(machine, "specification", None)
    machine_parts = machine.machine_parts.all()

    return render(
        request,
        "machine_specification.html",
        build_context(
            "ТТХ машини",
            machine=machine,
            specification=specification,
            machine_parts=machine_parts,
            back_url=reverse("machine_detail", kwargs={"pk": machine.pk}),
        ),
    )


def machine_specification_edit(request, pk):
    machine = get_object_or_404(Machine, pk=pk)
    specification = getattr(machine, "specification", None)

    if request.method == "POST":
        form = MachineSpecForm(request.POST, instance=specification)
        if form.is_valid():
            specification = form.save(commit=False)
            specification.machine = machine
            specification.save()
            return redirect("machine_specification", pk=machine.pk)
    else:
        form = MachineSpecForm(instance=specification)

    specification_url = reverse("machine_specification", kwargs={"pk": machine.pk})
    return render(
        request,
        "machine_spec_form.html",
        build_context(
            "ТТХ машини",
            machine=machine,
            form=form,
            form_title="Додати або редагувати ТТХ машини",
            back_url=specification_url,
            cancel_url=specification_url,
        ),
    )


def machine_part_create(request, pk):
    machine = get_object_or_404(Machine, pk=pk)

    if request.method == "POST":
        form = MachinePartForm(request.POST, machine=machine)
        if form.is_valid():
            machine_part = form.save(commit=False)
            machine_part.machine = machine
            machine_part.save()
            return redirect("machine_specification", pk=machine.pk)
    else:
        form = MachinePartForm(machine=machine)

    specification_url = reverse("machine_specification", kwargs={"pk": machine.pk})
    return render(
        request,
        "machine_part_form.html",
        build_context(
            "Додати запчастину до машини",
            machine=machine,
            form=form,
            form_title="Додати запчастину до машини",
            back_url=specification_url,
            cancel_url=specification_url,
        ),
    )


def machine_part_delete(request, pk, part_pk):
    machine = get_object_or_404(Machine, pk=pk)
    machine_part = get_object_or_404(machine.machine_parts.select_related("part"), pk=part_pk)
    specification_url = reverse("machine_specification", kwargs={"pk": machine.pk})

    if request.method == "POST":
        machine_part.delete()
        return redirect("machine_specification", pk=machine.pk)

    return render(
        request,
        "machine_part_delete_confirm.html",
        build_context(
            "Видалити запчастину з машини",
            machine=machine,
            machine_part=machine_part,
            back_url=specification_url,
            cancel_url=specification_url,
        ),
    )


def schedule(request):
    redirect_url = reverse("home")
    query_string = request.GET.urlencode()
    if query_string:
        redirect_url = f"{redirect_url}?{query_string}"
    return redirect(redirect_url)


def monthly_schedule_print(request):
    today = timezone.localdate()
    selected_year = request.GET.get("year", str(today.year))
    selected_month = request.GET.get("month", str(today.month))
    selected_machine = request.GET.get("machine", "").strip()

    try:
        year = int(selected_year)
        month = int(selected_month)
        if month < 1 or month > 12:
            raise ValueError
    except ValueError:
        year = today.year
        month = today.month

    context = build_monthly_schedule_context(year, month, today, selected_machine)
    return render(
        request,
        "print_monthly_schedule.html",
        build_print_context(
            f"Місячний графік ТО за {context['month_name']} {year}",
            **context,
        ),
    )


def archive_index(request):
    today = timezone.localdate()
    current_year = today.year
    plan_years = set(MaintenancePlan.objects.values_list("planned_date__year", flat=True))
    log_years = set(MaintenanceLog.objects.values_list("performed_date__year", flat=True))
    years = sorted((plan_years | log_years | {current_year}) - {None}, reverse=True)

    return render(
        request,
        "archive_index.html",
        build_context(
            "Архів",
            archive_years=years,
            current_year=current_year,
        ),
    )


def archive_year(request, year):
    today = timezone.localdate()
    month_cards = []
    for month_number, month_label in get_month_choices_uk():
        month_start = date(year, month_number, 1)
        status_label = "Архів"
        if month_start.year > today.year or (month_start.year == today.year and month_start.month > today.month):
            status_label = "Заплановано"
        elif month_start.year == today.year and month_start.month == today.month:
            status_label = "Поточний"

        plan_count = MaintenancePlan.objects.filter(planned_date__year=year, planned_date__month=month_number).count()
        log_count = MaintenanceLog.objects.filter(performed_date__year=year, performed_date__month=month_number).count()
        month_cards.append(
            {
                "number": month_number,
                "label": month_label,
                "status_label": status_label,
                "plan_count": plan_count,
                "log_count": log_count,
                "url": reverse("archive_month", kwargs={"year": year, "month": month_number}),
            }
        )

    return render(
        request,
        "archive_year.html",
        build_context(
            "Архів",
            archive_year=year,
            month_cards=month_cards,
        ),
    )


def archive_month(request, year, month):
    today = timezone.localdate()
    if month < 1 or month > 12:
        month = today.month

    return render(
        request,
        "schedule.html",
        build_context(
            f"Архів за {get_month_label_uk(month)} {year}",
            **build_monthly_schedule_context(year, month, today, include_inactive_with_activity=True),
            archive_mode=True,
            archive_year=year,
        ),
    )


def yearly_schedule(request):
    today = timezone.localdate()
    selected_year = request.GET.get("year", str(today.year))

    try:
        year = int(selected_year)
    except ValueError:
        year = today.year

    machines = list(Machine.objects.filter(is_active=True).order_by("name", "inventory_number"))
    plans = (
        MaintenancePlan.objects.filter(
            machine__is_active=True,
            planned_date__year=year,
        )
        .exclude(status=MaintenancePlan.Status.CANCELLED)
        .select_related("machine", "maintenance_type")
        .order_by("planned_date", "maintenance_type__code")
    )

    plans_by_machine_month = {}
    for plan in plans:
        plans_by_machine_month.setdefault((plan.machine_id, plan.planned_date.month), []).append(plan)

    yearly_rows = []
    month_choices_uk = get_month_choices_uk()
    for index, machine in enumerate(machines, start=1):
        months = []
        for month_number, month_label in month_choices_uk:
            month_plans = plans_by_machine_month.get((machine.id, month_number), [])
            codes = ", ".join(plan.maintenance_type.code for plan in month_plans)
            effective_statuses = [get_effective_plan_status(plan, today) for plan in month_plans]
            status_class = ""
            if any(status == MaintenancePlan.Status.OVERDUE for status in effective_statuses):
                status_class = "schedule-cell-overdue"
            elif any(status == MaintenancePlan.Status.DONE for status in effective_statuses):
                status_class = "schedule-cell-done"

            title = "; ".join(
                f"{plan.maintenance_type.code}: {dict(MaintenancePlan.Status.choices)[get_effective_plan_status(plan, today)]}"
                for plan in month_plans
            )
            months.append(
                {
                    "number": month_number,
                    "label": month_label,
                    "codes": codes,
                    "status_class": status_class,
                    "title": title,
                    "url": reverse("schedule") + f"?year={year}&month={month_number}&machine={machine.pk}",
                }
            )

        yearly_rows.append(
            {
                "index": index,
                "machine": machine,
                "months": months,
            }
        )

    return render(
        request,
        "yearly_schedule.html",
        build_context(
            "Річний графік ППР",
            selected_year=year,
            year_choices=get_year_choices(today.year),
            month_choices_uk=month_choices_uk,
            yearly_rows=yearly_rows,
        ),
    )


def yearly_schedule_print(request):
    today = timezone.localdate()
    selected_year = request.GET.get("year", str(today.year))

    try:
        year = int(selected_year)
    except ValueError:
        year = today.year

    machines = list(Machine.objects.filter(is_active=True).order_by("name", "inventory_number"))
    plans = (
        MaintenancePlan.objects.filter(machine__is_active=True, planned_date__year=year)
        .exclude(status=MaintenancePlan.Status.CANCELLED)
        .select_related("machine", "maintenance_type")
        .order_by("planned_date", "maintenance_type__code")
    )

    plans_by_machine_month = {}
    for plan in plans:
        plans_by_machine_month.setdefault((plan.machine_id, plan.planned_date.month), []).append(plan)

    yearly_rows = []
    month_choices_uk = get_month_choices_uk()
    for index, machine in enumerate(machines, start=1):
        months = []
        for month_number, month_label in month_choices_uk:
            month_plans = plans_by_machine_month.get((machine.id, month_number), [])
            codes = ", ".join(plan.maintenance_type.code for plan in month_plans)
            effective_statuses = [get_effective_plan_status(plan, today) for plan in month_plans]
            status_class = ""
            if any(status == MaintenancePlan.Status.OVERDUE for status in effective_statuses):
                status_class = "schedule-cell-overdue"
            elif any(status == MaintenancePlan.Status.DONE for status in effective_statuses):
                status_class = "schedule-cell-done"

            months.append(
                {
                    "number": month_number,
                    "label": month_label,
                    "codes": codes,
                    "status_class": status_class,
                }
            )

        yearly_rows.append({"index": index, "machine": machine, "months": months})

    return render(
        request,
        "print_yearly_schedule.html",
        build_print_context(
            f"Річний графік ППР за {year} рік",
            selected_year=year,
            month_choices_uk=month_choices_uk,
            yearly_rows=yearly_rows,
        ),
    )


def maintenance_plan_list(request):
    today = timezone.localdate()
    selected_year = request.GET.get("year", str(today.year))
    selected_month = request.GET.get("month", str(today.month))
    selected_machine = request.GET.get("machine", "").strip()
    selected_type = request.GET.get("maintenance_type", "").strip()

    plans = MaintenancePlan.objects.select_related("machine", "maintenance_type").order_by(
        "planned_date",
        "machine__name",
        "maintenance_type__code",
    )

    try:
        year = int(selected_year)
        plans = plans.filter(planned_date__year=year)
    except ValueError:
        year = today.year
        plans = plans.filter(planned_date__year=year)

    try:
        month = int(selected_month)
        if 1 <= month <= 12:
            plans = plans.filter(planned_date__month=month)
        else:
            month = today.month
            plans = plans.filter(planned_date__month=month)
    except ValueError:
        month = today.month
        plans = plans.filter(planned_date__month=month)

    if selected_machine:
        plans = plans.filter(machine_id=selected_machine)

    if selected_type:
        plans = plans.filter(maintenance_type_id=selected_type)

    machines = Machine.objects.filter(is_active=True).order_by("name", "inventory_number")
    maintenance_types = MaintenanceType.objects.order_by("code", "name")

    plan_rows = [
        {
            "plan": plan,
            "effective_status": dict(MaintenancePlan.Status.choices)[get_effective_plan_status(plan, today)],
        }
        for plan in plans
    ]

    return render(
        request,
        "maintenance_plan_list.html",
        build_context(
            "Планові роботи",
            plan_rows=plan_rows,
            selected_year=year,
            selected_month=month,
            selected_machine=selected_machine,
            selected_type=selected_type,
            month_choices=get_month_choices(),
            year_choices=get_year_choices(today.year),
            machines=machines,
            maintenance_types=maintenance_types,
        ),
    )


def maintenance_plan_create(request):
    if request.method == "POST":
        form = MaintenancePlanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("maintenance_plan_list")
    else:
        form = MaintenancePlanForm(initial={"status": MaintenancePlan.Status.PLANNED})

    return render(
        request,
        "maintenance_plan_form.html",
        build_context(
            "Створити планову роботу",
            form=form,
            form_title="Створити планову роботу",
            back_url=reverse("maintenance_plan_list"),
            cancel_url=reverse("maintenance_plan_list"),
        ),
    )


def maintenance_plan_update(request, pk):
    maintenance_plan = get_object_or_404(MaintenancePlan, pk=pk)

    if request.method == "POST":
        form = MaintenancePlanForm(request.POST, instance=maintenance_plan)
        if form.is_valid():
            form.save()
            return redirect("maintenance_plan_list")
    else:
        form = MaintenancePlanForm(instance=maintenance_plan)

    return render(
        request,
        "maintenance_plan_form.html",
        build_context(
            "Редагувати планову роботу",
            maintenance_plan=maintenance_plan,
            form=form,
            form_title="Редагувати планову роботу",
            back_url=reverse("maintenance_plan_list"),
            cancel_url=reverse("maintenance_plan_list"),
        ),
    )


def maintenance_plan_cancel(request, pk):
    maintenance_plan = get_object_or_404(MaintenancePlan, pk=pk)

    if request.method == "POST":
        maintenance_plan.status = MaintenancePlan.Status.CANCELLED
        maintenance_plan.save(update_fields=["status"])
        return redirect("maintenance_plan_list")

    return render(
        request,
        "maintenance_plan_cancel_confirm.html",
        build_context(
            "Скасувати планову роботу",
            maintenance_plan=maintenance_plan,
            back_url=reverse("maintenance_plan_list"),
            cancel_url=reverse("maintenance_plan_list"),
        ),
    )


def parts(request):
    search_query = request.GET.get("q", "").strip()
    selected_machine = request.GET.get("machine", "").strip()

    return render(
        request,
        "parts.html",
        build_context(
            "Запчастини",
            **build_parts_list_context(search_query, selected_machine),
        ),
    )


def parts_print(request):
    search_query = request.GET.get("q", "").strip()
    selected_machine = request.GET.get("machine", "").strip()
    return render(
        request,
        "print_parts.html",
        build_print_context(
            "Загальний перелік запчастин",
            **build_parts_list_context(search_query, selected_machine),
        ),
    )


def references(request):
    persons = Person.objects.filter(is_active=True).order_by("full_name")

    return render(
        request,
        "references.html",
        build_context(
            "Відповідальні особи",
            persons=persons,
            inactive_count=Person.objects.filter(is_active=False).count(),
        ),
    )


def inactive_persons(request):
    persons = Person.objects.filter(is_active=False).order_by("full_name")

    return render(
        request,
        "inactive_persons.html",
        build_context(
            "Неактивні особи",
            persons=persons,
        ),
    )


def person_create(request):
    if request.method == "POST":
        form = PersonForm(request.POST)
        if form.is_valid():
            person = form.save()
            return redirect("references")
    else:
        form = PersonForm(initial={"is_active": True})

    return render(
        request,
        "person_form.html",
        build_context(
            "Додати особу",
            form=form,
            form_title="Додати особу",
            back_url=reverse("references"),
            cancel_url=reverse("references"),
        ),
    )


def person_update(request, pk):
    person = get_object_or_404(Person, pk=pk)

    if request.method == "POST":
        form = PersonForm(request.POST, instance=person)
        if form.is_valid():
            form.save()
            return redirect("references")
    else:
        form = PersonForm(instance=person)

    return render(
        request,
        "person_form.html",
        build_context(
            "Редагувати особу",
            person=person,
            form=form,
            form_title="Редагувати особу",
            back_url=reverse("references"),
            cancel_url=reverse("references"),
        ),
    )


def person_deactivate(request, pk):
    person = get_object_or_404(Person, pk=pk)

    if request.method == "POST":
        person.is_active = False
        person.save(update_fields=["is_active"])
        messages.success(request, "Особу деактивовано")
        return redirect("references")

    return render(
        request,
        "person_deactivate_confirm.html",
        build_context(
            "Деактивувати особу",
            person=person,
            back_url=reverse("references"),
            cancel_url=reverse("references"),
        ),
    )


def person_restore(request, pk):
    person = get_object_or_404(Person, pk=pk, is_active=False)

    if request.method == "POST":
        person.is_active = True
        person.save(update_fields=["is_active"])
        messages.success(request, "Особу відновлено")
        return redirect("inactive_persons")

    return render(
        request,
        "person_restore_confirm.html",
        build_context(
            "Відновити особу",
            person=person,
            back_url=reverse("inactive_persons"),
            cancel_url=reverse("inactive_persons"),
        ),
    )
