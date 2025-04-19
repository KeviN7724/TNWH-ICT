import logging
from django.contrib import admin
from django.utils.timezone import now
from datetime import timedelta
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rangefilter.filters import DateRangeFilter
import csv
from reportlab.pdfgen import canvas
from .models import Product, HostnameAssignment, TransferLog
from django.contrib import messages
from django.urls import path
from django.shortcuts import render


logger = logging.getLogger(__name__)

class UpdatedHourlyFilter(admin.SimpleListFilter):
    title = "Updated At"
    parameter_name = "updated_at"

    def lookups(self, request, model_admin):
        return [
            ("hourly", "Updated Hourly"),
            ("today", "Today"),
            ("past_7_days", "Past 7 Days"),
            ("this_month", "This Month"),
            ("this_year", "This Year"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "hourly":
            return queryset.filter(updated_at__gte=now() - timedelta(hours=1))
        if self.value() == "today":
            return queryset.filter(updated_at__date=now().date())
        if self.value() == "past_7_days":
            return queryset.filter(updated_at__gte=now() - timedelta(days=7))
        if self.value() == "this_month":
            return queryset.filter(updated_at__month=now().month, updated_at__year=now().year)
        if self.value() == "this_year":
            return queryset.filter(updated_at__year=now().year)
        return queryset

class TransferLogInline(admin.TabularInline):
    model = TransferLog
    extra = 0
    fields = ['sender', 'receiver', 'transferred_at']
    readonly_fields = ['transferred_at'] 

class Past7DaysFilter(admin.SimpleListFilter):
    title = _('Report in Past 7 Days')
    parameter_name = 'past_7_days'

    def lookups(self, request, model_admin):
        return [('True', _('Last 7 Days'))]

    def queryset(self, request, queryset):
        if self.value() == 'True':
            seven_days_ago = timezone.now() - timedelta(days=7)
            return queryset.filter(transferlog__transferred_at__gte=seven_days_ago).distinct()
        return queryset

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id','hostname', 'user', 'host_name_category', 'serial_number')  # Updated display
    list_filter = ('created_at', Past7DaysFilter, UpdatedHourlyFilter)
    search_fields = ('host_name_category', 'user__username')  # Adjusted search
    inlines = [TransferLogInline]
    actions = ['download_transfer_report', 'export_as_pdf']

    def get_transfer_count(self, obj):
        return TransferLog.objects.filter(product=obj).count()
    get_transfer_count.short_description = 'Transfer Count'

    def download_transfer_report(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transfer_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Host Name', 'Sender', 'Receiver', 'Transferred At'])  # Updated header
        for log in TransferLog.objects.filter(product__in=queryset):
            writer.writerow([log.product.hostname, log.sender.username if log.sender else 'N/A',
                             log.receiver.username if log.receiver else 'N/A', log.transferred_at])
        return response
    download_transfer_report.short_description = 'Download Transfer History as CSV'

    def export_as_pdf(self, request, queryset):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="used_items_report.pdf"'
        
        p = canvas.Canvas(response)
        p.setFont("Helvetica", 12)
        p.drawString(200, 800, "ITEMS ASSIGNED REPORT FOR PAST 7 DAYS")
        
        y_position = 780
        p.setFont("Helvetica", 10)
        p.drawString(50, y_position, "Host Name")  # Updated column header
        p.drawString(70, y_position, "Serial Number")  # Added serial number column
        p.drawString(200, y_position, "User")
        p.drawString(350, y_position, "Assigned Date")
        p.drawString(500, y_position, "Returned Date")
        y_position -= 20
        
        seven_days_ago = timezone.now() - timedelta(days=7)
        assignments = HostnameAssignment.objects.filter(assigned_date__gte=seven_days_ago)

        for assignment in assignments:
            p.drawString(50, y_position, assignment.product.hostname)  # Updated to hostname
            p.drawString(70, y_position, assignment.product.serial_number)  # Added serial number
            p.drawString(200, y_position, assignment.user.username if assignment.user else "N/A")
            p.drawString(350, y_position, assignment.assigned_date.strftime('%Y-%m-%d %H:%M'))
            p.drawString(500, y_position, assignment.returned_date.strftime('%Y-%m-%d %H:%M') if assignment.returned_date else "N/A")
            y_position -= 20

            # Create a new page if space is running out
            if y_position < 50:  
                p.showPage()
                y_position = 800

        p.save()
        return response
    export_as_pdf.short_description = "Export Used Items Report as PDF"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['past_7_days'] = 'past_7_days' in request.GET and request.GET['past_7_days'] == 'True'
        return super().changelist_view(request, extra_context=extra_context)

@admin.register(HostnameAssignment)
class ItemAssignmentAdmin(admin.ModelAdmin):
    #list_display = ('hostname', 'user', 'assigned_date', 'unassigned_date', 'status')
    list_display = ('id','hostname', 'get_serial_number', 'user', 'assigned_date', 'unassigned_date', 'status')
    list_filter = (('assigned_date', DateRangeFilter), ('unassigned_date', DateRangeFilter))
    search_fields = ('user__username', 'hostname')
    ordering = ('-assigned_date',)
    actions = ["export_as_pdf", "export_as_excel", "download_assigned", "download_unassigned"]

    def get__serial_number(self, obj):
        return obj.get_serial_number()
    get__serial_number.short_description = 'Serial Number'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('report/', self.admin_site.admin_view(self.report_view), name='item_assignment_report'),
        ]
        return custom_urls + urls

    def report_view(self, request):
        assignments = HostnameAssignment.objects.all().order_by('-assigned_date')
        context = {'assignments': assignments}
        return render(request, 'admin/item_assignment_report.html', context)

    def view_report(self, request, queryset):
        return self.report_view(request)

    view_report.short_description = "View Report in Admin"

    def export_as_pdf(self, request, queryset):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="item_assignment_report.pdf"'

        p = canvas.Canvas(response)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(200, 800, "HOSTNAME ASSIGNMENT REPORT")
        p.line(200, 795, 420, 795)

        y_position = 780
        p.setFont("Helvetica", 10)
        p.drawString(30, y_position, "No.")
        p.drawString(70, y_position, "Hostname")
        p.drawString(150, y_position, "Serial Number")
        p.drawString(250, y_position, "User")
        p.drawString(350, y_position, "Assigned Date")
        p.drawString(500, y_position, "Unassigned Date")
        y_position -= 20

        for index, assignment in enumerate(queryset, start=1):
            p.drawString(30, y_position, str(index))
            p.drawString(70, y_position, assignment.hostname)
            p.drawString(150, y_position, assignment.get_serial_number())
            p.drawString(250, y_position, assignment.user.username if assignment.user else "N/A")
            p.drawString(350, y_position, assignment.assigned_date.strftime('%Y-%m-%d'))
            p.drawString(500, y_position, assignment.unassigned_date.strftime('%Y-%m-%d') if assignment.unassigned_date else "N/A")
            y_position -= 20

            if y_position < 50:
                p.showPage()
                y_position = 800
                p.setFont("Helvetica", 10)

        p.save()
        return response

    export_as_pdf.short_description = "Download PDF To Print"


#stock received
from .models import StockInvoice, StockReceive

class StockReceiveAdmin(admin.ModelAdmin):
    list_display = (
        'id','item_category', 'quantity', 'unit_of_measure', 'unit_price',
        'invoice_no', 'supplier_name', 'received_by', 'date_received', 'total_amount'
    )
    list_filter = ['item_category', 'invoice__supplier_name']
    search_fields = ('invoice__invoice_no', 'invoice__supplier_name', 'item_category', 'model_number')
    readonly_fields = ('total_amount',)  # to make total_amount read-only to avoid form errors

    def supplier_name(self, obj):
        return obj.invoice.supplier_name
    supplier_name.admin_order_field = 'invoice__supplier_name'

    def invoice_no(self, obj):
        return obj.invoice.invoice_no
    invoice_no.admin_order_field = 'invoice__invoice_no'

    def received_by(self, obj):
        return obj.invoice.received_by
    received_by.admin_order_field = 'invoice__received_by'

    def date_received(self, obj):
        return obj.invoice.date_received
    date_received.admin_order_field = 'invoice__date_received'


class StockReceiveInline(admin.TabularInline):
    model = StockReceive
    extra = 1


@admin.register(StockInvoice)
class StockInvoiceAdmin(admin.ModelAdmin):
    list_display = ['id','invoice_no', 'supplier_name', 'received_by', 'date_received', 'total_items', 'total_amount']
    list_filter = ['supplier_name', 'date_received']
    inlines = [StockReceiveInline]


admin.site.register(StockReceive, StockReceiveAdmin)

