import logging
from decimal import Decimal
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import Address, Cart, CartItem, Order, OrderItem, Product, SaleBanner

logger = logging.getLogger(__name__)

SORT_OPTIONS = (
    {'value': '-created_at', 'label': 'Newest Arrivals'},
    {'value': 'price', 'label': 'Price: Low to High'},
    {'value': '-price', 'label': 'Price: High to Low'},
    {'value': 'name', 'label': 'Name: A-Z'},
)
VALID_SORT_VALUES = {opt['value'] for opt in SORT_OPTIONS}


class DomainError(Exception):
    """Controlled business-logic exception with HTTP status code."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CatalogService:
    """Query and serialization logic for products and active sale banners."""

    @staticmethod
    def filter_products(params):
        queryset = Product.objects.filter(is_available=True)

        query = (params.get('q') or '').strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))

        category = params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        material = params.get('material')
        if material:
            queryset = queryset.filter(material=material)

        for param_name, lookup in (('min_price', 'price__gte'), ('max_price', 'price__lte')):
            raw = params.get(param_name)
            if raw not in (None, ''):
                try:
                    queryset = queryset.filter(**{lookup: Decimal(str(raw))})
                except (ValueError, ArithmeticError):
                    pass

        requires_assembly = params.get('requires_assembly')
        if requires_assembly == 'true':
            queryset = queryset.filter(requires_assembly=True)
        elif requires_assembly == 'false':
            queryset = queryset.filter(requires_assembly=False)

        if params.get('is_available') == 'true':
            queryset = queryset.filter(stock_quantity__gt=0)

        if params.get('on_sale') == 'true':
            queryset = queryset.filter(on_sale=True)

        sort_by = params.get('sort_by', '-created_at')
        queryset = queryset.order_by(sort_by if sort_by in VALID_SORT_VALUES else '-created_at')
        return queryset, query

    @staticmethod
    def active_banners():
        now = timezone.now()
        return (
            SaleBanner.objects.filter(is_active=True, featured_product__isnull=False)
            .filter(Q(sale_end_date__isnull=True) | Q(sale_end_date__gte=now))
            .select_related('featured_product')
            .order_by('-updated_at')
        )

    @staticmethod
    def serialize_product(product):
        return {
            'id': product.pk,
            'name': product.name,
            'description': product.description or '',
            'price': float(product.price),
            'discounted_price': float(product.get_discounted_price()),
            'on_sale': product.on_sale,
            'discount_percentage': float(product.discount_percentage),
            'category': product.category,
            'category_display': product.get_category_display(),
            'material': product.material,
            'material_display': product.get_material_display(),
            'stock_quantity': product.stock_quantity,
            'is_available': product.is_available,
            'requires_assembly': product.requires_assembly,
            'image_url': product.image.url if product.image else None,
            'created_at': product.created_at.isoformat(),
        }


class CartService:
    """Cart resolution, merging, item mutation, and stock validation."""

    @staticmethod
    def get_or_create_cart(request):
        cart_id = request.session.get('cart_id')
        cart = None
        merged = False

        if request.user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            if cart_id and str(cart.id) != str(cart_id):
                anon_cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()
                if anon_cart:
                    with transaction.atomic():
                        for item in anon_cart.items.select_related('product'):
                            cart_item, created = CartItem.objects.get_or_create(
                                cart=cart,
                                product=item.product,
                                defaults={'quantity': item.quantity, 'price': item.price},
                            )
                            if not created:
                                cart_item.quantity = min(cart_item.quantity + item.quantity, 99)
                                cart_item.save(update_fields=['quantity'])
                        anon_cart.delete()
                    merged = True
            request.session['cart_id'] = cart.id
        else:
            if cart_id:
                cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()
            if not cart:
                cart = Cart.objects.create(user=None)
                request.session['cart_id'] = cart.id

        count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        request.session['cart_item_count'] = count
        return cart, count, merged

    @staticmethod
    def add_item(cart, product, quantity):
        if not product.is_available:
            raise DomainError('This product is currently unavailable.', 400)
        if quantity < 1 or quantity > 99:
            raise DomainError('Quantity must be between 1 and 99.', 400)

        price_to_store = product.get_discounted_price() if product.on_sale else product.price
        with transaction.atomic():
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': quantity, 'price': price_to_store},
            )
            desired_qty = quantity if created else cart_item.quantity + quantity
            if product.stock_quantity > 0 and desired_qty > product.stock_quantity:
                if created:
                    cart_item.delete()
                raise DomainError(f'Only {product.stock_quantity} left in stock.', 400)

            if not created:
                cart_item.quantity = min(desired_qty, 99)
                cart_item.price = price_to_store
                cart_item.save(update_fields=['quantity', 'price'])

        return cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0

    @staticmethod
    def update_item_quantity(cart, cart_item, new_quantity):
        if cart_item.cart_id != cart.id:
            raise DomainError('Unauthorized action.', 403)
        if new_quantity < 0 or new_quantity > 99:
            raise DomainError('Quantity must be between 0 and 99.', 400)
        if new_quantity > 0 and cart_item.product.stock_quantity > 0 and new_quantity > cart_item.product.stock_quantity:
            raise DomainError(f'Only {cart_item.product.stock_quantity} left in stock.', 400)

        if new_quantity == 0:
            name = cart_item.product.name
            cart_item.delete()
            message = f'{name} removed from cart.'
            item_total = 0.0
        else:
            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity'])
            message = f'Quantity for {cart_item.product.name} updated.'
            item_total = float(cart_item.get_total())

        count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        total_price = float(cart.get_total_price())
        return {
            'message': message,
            'new_quantity': new_quantity,
            'item_total': item_total,
            'cart_item_count': count,
            'cart_total_price': total_price,
        }


class OrderService:
    """Atomic checkout and order status transitions."""

    ALLOWED_PAYMENT_METHODS = {'Cash on Delivery', 'COD'}
    VALID_STATUSES = {choice[0] for choice in Order.STATUS_CHOICES}

    @staticmethod
    def place_order(user, cart, shipping_address_id, payment_method='Cash on Delivery'):
        if payment_method not in OrderService.ALLOWED_PAYMENT_METHODS:
            raise DomainError('Invalid payment method selected.', 400)

        try:
            shipping_address = Address.objects.get(pk=shipping_address_id, user=user)
        except (Address.DoesNotExist, ValueError, TypeError):
            raise DomainError('Selected shipping address is invalid.', 400)

        try:
            with transaction.atomic():
                cart_items = list(cart.items.select_related('product').all())
                if not cart_items:
                    raise DomainError('Your cart is empty.', 400)

                for item in cart_items:
                    if not item.product.is_available:
                        raise DomainError(f'{item.product.name} is no longer available.', 400)
                    if item.product.stock_quantity > 0 and item.quantity > item.product.stock_quantity:
                        raise DomainError(f'Only {item.product.stock_quantity} of {item.product.name} available.', 400)

                total_price = sum(item.get_total() for item in cart_items)
                order = Order.objects.create(
                    user=user,
                    total_price=total_price,
                    status='PENDING',
                    shipping_address=shipping_address,
                    payment_method='Cash on Delivery',
                )
                OrderItem.objects.bulk_create([
                    OrderItem(order=order, product=item.product, quantity=item.quantity, price=item.price)
                    for item in cart_items
                ])
                for item in cart_items:
                    if item.product.stock_quantity > 0:
                        item.product.stock_quantity = max(0, item.product.stock_quantity - item.quantity)
                        item.product.save(update_fields=['stock_quantity'])

                cart.items.all().delete()
                return order
        except (DatabaseError, IntegrityError) as exc:
            logger.exception('Order placement failed for user %s: %s', user.pk, exc)
            raise DomainError('Could not complete your order due to a system error.', 500)

    @staticmethod
    def update_status(actor, order, new_status):
        if not actor.is_staff:
            if order.user_id != actor.id:
                raise DomainError('You do not have permission to update this order.', 403)
            if order.status not in ('PENDING', 'PROCESSING'):
                raise DomainError('Only pending or processing orders can be cancelled.', 400)
            if new_status != 'CANCELLED':
                raise DomainError('You may only cancel your order.', 403)

        if new_status not in OrderService.VALID_STATUSES:
            raise DomainError('Invalid status provided.', 400)

        order.status = new_status
        order.save(update_fields=['status'])
        return order
