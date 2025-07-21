from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('LIVING_ROOM', 'Living Room'),
        ('BEDROOM', 'Bedroom'),
        ('DINING_ROOM', 'Dining Room'),
        ('OFFICE', 'Office'),
        ('OUTDOOR', 'Outdoor'),
        ('KITCHEN', 'Kitchen'),
    ]

    MATERIAL_CHOICES = [
        ('WOOD', 'Wood'),
        ('METAL', 'Metal'),
        ('FABRIC', 'Fabric'),
        ('LEATHER', 'Leather'),
        ('GLASS', 'Glass'),
        ('PLASTIC', 'Plastic'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='LIVING_ROOM')
    material = models.CharField(max_length=50, choices=MATERIAL_CHOICES, default='WOOD')
    stock_quantity = models.IntegerField(default=0)
    is_available = models.BooleanField(default=True)
    requires_assembly = models.BooleanField(default=False)
    on_sale = models.BooleanField(default=False)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_discounted_price(self):
        if self.on_sale and self.discount_percentage > 0:
            discount_amount = self.price * (self.discount_percentage / 100)
            return self.price - discount_amount
        return self.price

class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.username if self.user else 'Anonymous'}"

    def get_total_price(self):
        return sum(item.get_total() for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('cart', 'product')

    def __str__(self):
        return f"{self.quantity} x {self.product.name} in cart {self.cart.id}"

    def get_total(self):
        return self.quantity * self.price

class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    first_name = models.CharField(max_length=100, default='')
    last_name = models.CharField(max_length=100, default='')
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.first_name} {self.last_name}, {self.street_address}, {self.city}"

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, related_name='orders_shipped_to')
    payment_method = models.CharField(max_length=50)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name} for Order {self.order.id}"

    def get_total(self):
        return self.quantity * self.price

class SaleBanner(models.Model):
    title = models.CharField(max_length=255)
    featured_product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    custom_message = models.TextField(blank=True, null=True, help_text="Overrides default message if provided.")
    sale_end_date = models.DateTimeField(null=True, blank=True, help_text="Leave blank for ongoing sale.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
