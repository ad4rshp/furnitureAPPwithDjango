from django.contrib import admin
from .models import Product, SaleBanner

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'on_sale', 'discount_percentage', 'is_available', 'requires_assembly', 'created_at')
    list_filter = ('category', 'on_sale', 'is_available', 'requires_assembly', 'material')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'
    fields = ('name', 'description', 'price', 'category', 'material', 'image', 'is_available', 'requires_assembly', 'on_sale', 'discount_percentage')

    class Media:
        css = {
            'all': ('admin.css',)
        }

class SaleBannerAdmin(admin.ModelAdmin):
    list_display = ('featured_product', 'custom_message', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('featured_product__name', 'custom_message')

admin.site.register(Product, ProductAdmin)
admin.site.register(SaleBanner, SaleBannerAdmin)
