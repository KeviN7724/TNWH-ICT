from django.db import models, IntegrityError
from django.contrib.auth.models import User
from django.utils.timezone import now
from io import BytesIO
from django.core.files.base import ContentFile
import uuid
import barcode
from barcode.writer import ImageWriter
import base64
import hashlib
from datetime import timedelta


class TransferLog(models.Model):
    id = models.AutoField(primary_key=True)
    product = models.ForeignKey('Product', on_delete=models.CASCADE, verbose_name="Product")
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_transfers')
    receiver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='received_transfers')
    transferred_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"#{self.id}: {self.product.host_name_category} from {self.sender} to {self.receiver} on {self.transferred_at}"


class ProductGroup(models.Model):
    group_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200, verbose_name="Group Name")

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.AutoField(primary_key=True)
    unique_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="Unique ID")
    hostname = models.CharField(max_length=255, blank=True, null=True, verbose_name="Hostname")
    host_name_category = models.CharField(max_length=10,choices=[("Desktop", "Desktop"), ("Laptop", "Laptop")],verbose_name="Host Name Category")
    model_number = models.CharField(max_length=13, null=True, blank=True, verbose_name="Model Number")
    serial_number = models.CharField(max_length=13, unique=True, null=True, blank=True, verbose_name="Serial Number")
    lan_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="LAN IP")
    wan_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="WAN IP")
    mac_address = models.CharField(max_length=17, blank=True, verbose_name="MAC Address")
    location = models.CharField(max_length=255, blank=True, null=True)
    barcode = models.ImageField(upload_to='barcodes/', blank=True, verbose_name="Barcode Image")
    token = models.CharField(max_length=36, unique=True, blank=True, editable=False, verbose_name="Unique Token")
    item_type = models.CharField(max_length=100, choices=[
        ("Monitor", "Monitor"),
        ("Mouse", "Mouse"),
        ("Printer", "Printer"),
        ("Phone", "Phone"),
        ("Keyboard", "Keyboard"),
        ("CPU", "CPU"),
        ("Scanner", "Scanner")
    ], verbose_name="Item Type")
    #country_id = models.CharField(max_length=10, null=True, verbose_name="Country ID")
    #manufacturer_id = models.CharField(max_length=6, null=True, verbose_name="Manufacturer ID")
    number_id = models.CharField(max_length=5, null=True, verbose_name="Number ID")
    department = models.CharField(max_length=100, null=True, blank=True, verbose_name="Department")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Created By")
    users = models.ManyToManyField(User, blank=True, verbose_name="Assigned Users", related_name="assigned_products")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")
    last_updated_hourly = models.DateTimeField(null=True, blank=True, verbose_name="Last Updated Hourly")

    def get_transfer_history(self):
        return TransferLog.objects.filter(product=self).order_by('-transferred_at')

    def save(self, *args, **kwargs):
        if not self.token:
            while True:
                new_token = str(uuid.uuid4())
                if not Product.objects.filter(token=new_token).exists():
                    self.token = new_token
                    break

        barcode_data = self.serial_number or self.model_number or self.token or str(self.id)
        if barcode_data:
            barcode_class = barcode.get_barcode_class('code128')
            barcode_instance = barcode_class(barcode_data, writer=ImageWriter())
            buffer = BytesIO()
            barcode_instance.write(buffer)
            filename = f'barcode_{self.token}.png'
            self.barcode.save(filename, ContentFile(buffer.getvalue()), save=False)

        if not self.last_updated_hourly or (now() - self.last_updated_hourly) >= timedelta(hours=1):
            self.last_updated_hourly = now()

        try:
            super().save(*args, **kwargs)
        except IntegrityError:
            self.token = str(uuid.uuid4())
            super().save(*args, **kwargs)

    def transfer_to(self, new_user):
        TransferLog.objects.create(
            product=self,
            sender=self.user,
            receiver=new_user,
            transferred_at=now()
        )
        self.users.add(new_user)
        self.save()


class HostnameAssignment(models.Model):
    hostname = models.CharField(max_length=255, verbose_name="Hostname")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Assigned User")
    assigned_date = models.DateField(auto_now_add=True, verbose_name="Assignment Date")
    unassigned_date = models.DateField(null=True, blank=True, verbose_name="Unassignment Date")
    status = models.CharField(max_length=20, choices=[('Assigned', 'Assigned'), ('Unassigned', 'Unassigned')])

    def __str__(self):
        return f"{self.hostname} -> {self.user.username} ({self.status})"

    def save(self, *args, **kwargs):
        # Update the hostname field in the matching Product
        try:
            product = Product.objects.get(hostname=self.hostname)
            if self.status == 'Assigned':
                product.hostname = self.hostname
            elif self.status == 'Unassigned':
                active_assignments = HostnameAssignment.objects.filter(
                    hostname=self.hostname,
                    status='Assigned'
                ).exclude(id=self.id)
                if not active_assignments.exists():
                    product.hostname = None
            product.save(update_fields=['hostname'])
        except Product.DoesNotExist:
            pass  # Optionally raise error or log

        super().save(*args, **kwargs)

    def is_active(self):
        return self.status == 'Assigned' and self.unassigned_date is None

    def generate_short_code(self):
        try:
            product = Product.objects.get(hostname=self.hostname)
            if product.serial_number:
                hash_object = hashlib.sha256(product.serial_number.encode())
                return base64.b32encode(hash_object.digest()).decode()[:8]
        except Product.DoesNotExist:
            return None
        
    def get_serial_number(self):
        try:
            product = Product.objects.get(hostname=self.hostname)
            return product.serial_number
        except Product.DoesNotExist:
            return "N/A"    

    @staticmethod
    def get_current_hostname_assignment(hostname_str):
        return HostnameAssignment.objects.filter(
            hostname=hostname_str, 
            status='Assigned'
        ).order_by('-assigned_date').first()



#Stock Received
# class StockReceive(models.Model):
#     UNIT_CHOICES = [
#         ('pcs', 'Pieces'),
#         ('box', 'Box'),
#         ('kg', 'Kilogram'),
#         ('ltr', 'Litre'),
#         ('unit', 'Unit'),
#     ]

#     supplier_name = models.CharField(max_length=255, verbose_name="Supplier Name")
#     item_category = models.CharField(max_length=20,choices=[("Desktop", "Desktop"), ("Laptop", "Laptop"), ("Printer", "Printer"), ("YealinkPhone", "YealinkPhone")], verbose_name="Item Category")
#     model_number = models.CharField(max_length=13, null=True, blank=True, verbose_name="Model Number")
#     quantity = models.PositiveIntegerField(verbose_name="Quantity")
#     unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES, verbose_name="Unit of Measure (UoM)")
#     total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total Amount (Ksh.)")
#     invoice_no = models.CharField(max_length=255, null=True, blank=True, verbose_name="Invoice Number")
#     received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Received By")
#     timestamp = models.DateTimeField(auto_now_add=True)
#     date_received = models.DateField(default=now, verbose_name="Date Received")

#     def __str__(self):
#      return f"{self.quantity} {self.unit_of_measure} {self.invoice_no} of {self.item_category} from {self.supplier_name}"


class StockInvoice(models.Model):
    supplier_name = models.CharField(max_length=255, verbose_name="Supplier Name")
    invoice_no = models.CharField(max_length=255, unique=True, verbose_name="Invoice Number")
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Received By")
    date_received = models.DateField(default=now, verbose_name="Date Received")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice_no} from {self.supplier_name}"

    def total_items(self):
        return self.items.count()

    def total_amount(self):
        return sum(item.total_amount for item in self.items.all())


class StockReceive(models.Model):
    UNIT_CHOICES = [
        ('pcs', 'Pieces'),
        ('box', 'Box'),
        ('kg', 'Kilogram'),
        ('ltr', 'Litre'),
        ('unit', 'Unit'),
    ]

    CATEGORY_CHOICES = [
        ("Desktop", "Desktop"),
        ("Laptop", "Laptop"),
        ("Printer", "Printer"),
        ("YealinkPhone", "YealinkPhone"),
    ]

    invoice = models.ForeignKey(StockInvoice, on_delete=models.CASCADE, related_name='items', verbose_name="Invoice")
    item_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name="Item Category")
    model_number = models.CharField(max_length=20, null=True, blank=True, verbose_name="Model Number")
    quantity = models.PositiveIntegerField(verbose_name="Quantity")
    unit_of_measure = models.CharField(max_length=10, choices=UNIT_CHOICES, verbose_name="Unit of Measure (UoM)")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Unit Price (Ksh.)")
    total_amount = models.DecimalField(
    max_digits=10, decimal_places=2, verbose_name="Total Amount (Ksh.)", blank=True, default=0.00
)

    def save(self, *args, **kwargs):
        # Auto calculate total_amount before saving
        self.total_amount = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} {self.unit_of_measure} of {self.item_category} - Invoice {self.invoice.invoice_no}"

