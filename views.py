from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.utils.timezone import now
from uuid import UUID
import pandas as pd
from .forms import UploadFileForm, ProductUploadForm
from .models import Product, ProductGroup, TransferLog


def upload_file(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Read file with pandas
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.name.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(file)
                else:
                    messages.error(request, "Unsupported file format. Please upload a CSV or Excel file.")
                    return redirect('upload_file')
                
                group = ProductGroup.objects.create(name="New Inventory Group")

                # Iterate and create Product objects
                for _, row in df.iterrows():
                    Product.objects.create(
                        host_name_category=row.get('host_name_category', ''),
                        serial_number=row.get('serial_number', ''),
                        model_number=row.get('model_number', ''),
                        category=row.get('category', ''),
                        country_id=row.get('country_id', ''),
                        manufacturer_id=row.get('manufacturer_id', ''),
                        number_id=row.get('number_id', ''),
                        department=row.get('department', ''),
                        users=row.get('users', ''),
                        user=request.user,  # Assign current user
                        group=group
                    )

                messages.success(request, "Products uploaded successfully!")
                return redirect('upload_file')

            except Exception as e:
                messages.error(request, f"Error processing file: {str(e)}")
                return redirect('upload_file')
    else:
        form = UploadFileForm()
    
    products = Product.objects.all()
    return render(request, 'upload.html', {'form': form, 'products': products})


def product_list(request):
    products = Product.objects.all().order_by('user')
    
    # Group by user and limit each user to 5 products
    grouped_products = {}
    for product in products:
        if product.user not in grouped_products:
            grouped_products[product.user] = []
        if len(grouped_products[product.user]) < 7:
            grouped_products[product.user].append(product)

    return render(request, "list.html", {"grouped_products": grouped_products})


def print_product(request, product_id):
    try:
        product_uuid = UUID(str(product_id))  # Validate UUID
        product = get_object_or_404(Product, id=product_uuid)
    except ValueError:
        return HttpResponse("Invalid Product ID format", status=400)
    return HttpResponse(f"Printing product: {product.host_name_category}")


def create_product(request):
    if request.method == "POST":
        host_name_category = request.POST.get("host_name_category")
        department = request.POST.get("department")
        user_ids = request.POST.getlist("users")  # Handle multiple users
        product = Product.objects.create(host_name_category=host_name_category, department=department)
        product.users.set(User.objects.filter(id__in=user_ids))
        product.save()
        return redirect("inventory_list")  # Redirect to inventory page
    
    users = User.objects.all()
    return render(request, "inventory.html", {"users": users})


def upload_products(request):
    if request.method == "POST":
        form = ProductUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Read file
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                elif file.name.endswith('.xlsx'):
                    df = pd.read_excel(file)
                else:
                    messages.error(request, "Invalid file format. Please upload CSV or Excel.")
                    return redirect('upload_products')
                
                # Iterate and update/create products
                for _, row in df.iterrows():
                    product, created = Product.objects.update_or_create(
                        serial_number=row.get("serial_number", None),
                        defaults={
                            "host_name_category": row.get("host_name_category", ""),
                            "model_number": row.get("model_number", ""),
                            "country_id": row.get("country_id", ""),
                            "manufacturer_id": row.get("manufacturer_id", ""),
                            "number_id": row.get("number_id", ""),
                            "department": row.get("department", ""),
                        }
                    )
                    product.save()
                messages.success(request, "Products uploaded successfully!")
                return redirect('upload_products')
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")
                return redirect('upload_products')
    else:
        form = ProductUploadForm()
    return render(request, "upload.html", {"form": form})


def transfer_product(request, product_id):
    product = get_object_or_404(Product, id=UUID(product_id))
    if request.method == "POST":
        new_owner_id = request.POST.get("new_owner")
        new_owner = get_object_or_404(User, id=new_owner_id)

        if product.current_owner:
            TransferLog.objects.create(
                product=product,
                sender=product.current_owner,
                receiver=new_owner,
                transferred_at=now()
            )

        product.current_owner = new_owner
        product.save()

        messages.success(request, f"Product {product.host_name_category} transferred to {new_owner.username}")
        return redirect("product_list")
    
    users = User.objects.exclude(id=product.current_owner.id if product.current_owner else None)
    return render(request, "transfer_product.html", {"product": product, "users": users})


def product_transfer_history(request, product_id):
    product = get_object_or_404(Product, id=UUID(product_id))
    transfers = TransferLog.objects.filter(product=product).order_by("-transferred_at")
    return render(request, "transfer_history.html", {"product": product, "transfers": transfers})


def transfer_to(self, new_owner):
    if self.current_owner:
        TransferLog.objects.create(
            product=self,
            sender=self.current_owner,
            receiver=new_owner,
            transferred_at=now()
        )
    self.current_owner = new_owner
    self.save()


def inventory_list(request):
    products_list = Product.objects.all()
    paginator = Paginator(products_list, 20)  # Show 20 products per page

    page_number = request.GET.get("page")
    products = paginator.get_page(page_number)

    return render(request, "base.html", {"products": products})    


def login_page(request):
    return render(request, 'login.html')


#CUSTOM ADMIN
@login_required
def dashboard_view(request):
    return render(request, 'products/dashboard.html')