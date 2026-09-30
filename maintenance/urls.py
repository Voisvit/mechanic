"""
URL configuration for maintenance project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.urls import path

from . import views

protected = login_required

urlpatterns = [
    path('login/', LoginView.as_view(template_name='login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', protected(views.home), name='home'),
    path('equipment/', protected(views.equipment), name='equipment'),
    path('equipment/inactive/', protected(views.inactive_equipment), name='inactive_equipment'),
    path('equipment/add/', protected(views.machine_create), name='machine_create'),
    path('equipment/<int:pk>/', protected(views.machine_detail), name='machine_detail'),
    path('equipment/<int:pk>/edit/', protected(views.machine_update), name='machine_update'),
    path('equipment/<int:pk>/deactivate/', protected(views.machine_deactivate), name='machine_deactivate'),
    path('equipment/<int:pk>/restore/', protected(views.machine_restore), name='machine_restore'),
    path('equipment/<int:pk>/delete/', protected(views.machine_delete), name='machine_delete'),
    path('equipment/<int:pk>/logs/add/', protected(views.maintenance_log_create), name='maintenance_log_create'),
    path('equipment/<int:pk>/logs/<int:log_pk>/edit/', protected(views.maintenance_log_update), name='maintenance_log_update'),
    path('equipment/<int:pk>/logs/<int:log_pk>/delete/', protected(views.maintenance_log_delete), name='maintenance_log_delete'),
    path('equipment/<int:pk>/specification/', protected(views.machine_specification), name='machine_specification'),
    path('equipment/<int:pk>/analytics/', protected(views.machine_analytics), name='machine_analytics'),
    path('equipment/<int:pk>/print/', protected(views.machine_detail_print), name='machine_detail_print'),
    path('equipment/<int:pk>/specification/edit/', protected(views.machine_specification_edit), name='machine_specification_edit'),
    path('equipment/<int:pk>/parts/add/', protected(views.machine_part_create), name='machine_part_create'),
    path('equipment/<int:pk>/parts/<int:part_pk>/delete/', protected(views.machine_part_delete), name='machine_part_delete'),
    path('schedule/', protected(views.schedule), name='schedule'),
    path('schedule/print/', protected(views.monthly_schedule_print), name='monthly_schedule_print'),
    path('schedule/transfer/', protected(views.monthly_schedule_transfer), name='monthly_schedule_transfer'),
    path('schedule/yearly/', protected(views.yearly_schedule), name='yearly_schedule'),
    path('schedule/yearly/print/', protected(views.yearly_schedule_print), name='yearly_schedule_print'),
    path('schedule/plans/', protected(views.maintenance_plan_list), name='maintenance_plan_list'),
    path('schedule/plans/bulk-add/', protected(views.maintenance_plan_bulk_create), name='maintenance_plan_bulk_create'),
    path('schedule/plans/add/', protected(views.maintenance_plan_create), name='maintenance_plan_create'),
    path('schedule/plans/<int:pk>/edit/', protected(views.maintenance_plan_update), name='maintenance_plan_update'),
    path('schedule/plans/<int:pk>/cancel/', protected(views.maintenance_plan_cancel), name='maintenance_plan_cancel'),
    path('archive/', protected(views.archive_index), name='archive_index'),
    path('archive/<int:year>/', protected(views.archive_year), name='archive_year'),
    path('archive/<int:year>/<int:month>/', protected(views.archive_month), name='archive_month'),
    path('parts/', protected(views.parts), name='parts'),
    path('parts/add/', protected(views.part_create), name='part_create'),
    path('parts/<int:pk>/edit/', protected(views.part_update), name='part_update'),
    path('parts/<int:pk>/delete/', protected(views.part_delete), name='part_delete'),
    path('parts/print/', protected(views.parts_print), name='parts_print'),
    path('references/', protected(views.references), name='references'),
    path('references/inactive/', protected(views.inactive_persons), name='inactive_persons'),
    path('references/add/', protected(views.person_create), name='person_create'),
    path('references/<int:pk>/edit/', protected(views.person_update), name='person_update'),
    path('references/<int:pk>/deactivate/', protected(views.person_deactivate), name='person_deactivate'),
    path('references/<int:pk>/restore/', protected(views.person_restore), name='person_restore'),
    path('admin/', admin.site.urls),
]
