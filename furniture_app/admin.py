from django.contrib import admin
from django.utils.html import format_html
from .models import Product, SaleBanner, Order, OrderItem, Address, Cart, CartItem


admin.site.site_header = "My Furniture Store Admin"
admin.site.site_title = "Furniture Store Admin"
admin.site.index_title = "Store & Catalog Management"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'image_thumbnail',
        'name',
        'category',
        'material',
        'price',
        'stock_quantity',
        'on_sale',
        'discount_percentage',
        'is_available',
        'requires_assembly',
        'created_at',
    )
    list_display_links = ('image_thumbnail', 'name')
    list_filter = ('category', 'material', 'on_sale', 'is_available', 'requires_assembly')
    list_editable = ('price', 'stock_quantity', 'is_available', 'on_sale')
    search_fields = ('name', 'description')
    date_hierarchy = 'created_at'
    readonly_fields = ('image_preview', 'created_at', 'updated_at')
    fieldsets = (
        ('Product Details', {
            'fields': ('name', 'description', 'category', 'material'),
        }),
        ('Media', {
            'fields': ('image', 'image_preview'),
        }),
        ('Pricing & Inventory', {
            'fields': ('price', 'on_sale', 'discount_percentage', 'stock_quantity', 'is_available', 'requires_assembly'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Image')
    def image_thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" style="width: 56px; height: 56px; object-fit: cover; border-radius: 6px; border: 1px solid #ddd;" />',
                obj.image.url,
                obj.name,
            )
        return format_html('<span style="color: #888; font-size: 12px;">No Image</span>')

    @admin.display(description='Current Image Preview')
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="{}" style="max-width: 280px; max-height: 280px; object-fit: contain; border-radius: 8px; border: 1px solid #ccc; padding: 4px;" />',
                obj.image.url,
                obj.name,
            )
        return "No image uploaded yet."

    class Media:
        css = {
            'all': ('admin.css',)
        }


@admin.register(SaleBanner)
class SaleBannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'featured_product', 'is_active', 'sale_end_date', 'updated_at')
    list_filter = ('is_active',)
    list_editable = ('is_active',)
    search_fields = ('title', 'featured_product__name', 'custom_message')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'total_price', 'payment_method', 'status', 'order_date')
    list_filter = ('status', 'payment_method', 'order_date')
    list_editable = ('status',)
    search_fields = ('id', 'user__username', 'user__email')
    date_hierarchy = 'order_date'
    inlines = [OrderItemInline]


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'city', 'state', 'country', 'is_default')
    list_filter = ('country', 'state', 'is_default')
    search_fields = ('user__username', 'street_address', 'city', 'zip_code')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'updated_at')
    search_fields = ('user__username',)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'product', 'quantity', 'price')
    search_fields = ('product__name', 'cart__user__username')
