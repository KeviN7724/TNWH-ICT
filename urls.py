from django.urls import path
from .views import download_pdf_report, download_excel_report
from .views import product_list, print_product
from .views import upload_products
from .views import product_list, transfer_product, product_transfer_history
from .views import update_department


urlpatterns = [
    path('', product_list, name='product_list'),  # List products with pagination
    path('print/<int:product_id>/', print_product, name='print_product'),
    path('upload/', upload_products, name='upload_products'),
    path("products/", product_list, name="product_list"),
    path("products/<uuid:product_id>/transfer/", transfer_product, name="transfer_product"),
    path("products/<uuid:product_id>/history/", product_transfer_history, name="product_transfer_history"),
    path("update-department/<uuid:product_id>/", update_department, name="update_department"),
    path('admin/products/download-pdf/', download_pdf_report, name='admin_download_pdf'),
    path('admin/products/download-excel/', download_excel_report, name='admin_download_excel'),
    # path('', views.login_page, name='landing'),
    # path('inventory/', views.inventory_list_view, name='inventory-list'),
]
