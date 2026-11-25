import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_GET, require_POST

from .models import Product, SaleBanner, Cart, CartItem, Address, Order, OrderItem
from .forms import AddressForm, UserProfileForm, CustomUserCreationForm

logger = logging.getLogger(__name__)

SORT_OPTIONS = (
    {'value': '-created_at', 'label': 'Newest Arrivals'},
    {'value': 'price', 'label': 'Price: Low to High'},
    {'value': '-price', 'label': 'Price: High to Low'},
    {'value': 'name', 'label': 'Name: A-Z'},
)
VALID_SORT_VALUES = {opt['value'] for opt in SORT_OPTIONS}
VALID_ORDER_STATUSES = {choice[0] for choice in Order.STATUS_CHOICES}


def _is_ajax(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


def _parse_float(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(value, min_val=None, max_val=None):
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return None
    if min_val is not None and parsed < min_val:
        return None
    if max_val is not None and parsed > max_val:
        return None
    return parsed


def _apply_product_filters(queryset, params):
    """Shared product filtering pipeline used by both HTML catalog and JSON API."""
    query = params.get('q', '').strip()
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))

    category = params.get('category')
    if category:
        queryset = queryset.filter(category=category)

    material = params.get('material')
    if material:
        queryset = queryset.filter(material=material)

    min_price = _parse_float(params.get('min_price'))
    if min_price is not None:
        queryset = queryset.filter(price__gte=min_price)

    max_price = _parse_float(params.get('max_price'))
    if max_price is not None:
        queryset = queryset.filter(price__lte=max_price)

    requires_assembly = params.get('requires_assembly')
    if requires_assembly == 'true':
        queryset = queryset.filter(requires_assembly=True)
    elif requires_assembly == 'false':
        queryset = queryset.filter(requires_assembly=False)

    if params.get('is_available') == 'true':
        queryset = queryset.filter(is_available=True, stock_quantity__gt=0)

    if params.get('on_sale') == 'true':
        queryset = queryset.filter(on_sale=True)

    return queryset, query


def _serialize_product(product):
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


def get_or_create_cart(request):
    cart_id = request.session.get('cart_id')
    cart = None

    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            if cart_id and str(cart.id) != str(cart_id):
                try:
                    anon_cart = Cart.objects.get(id=cart_id, user__isnull=True)
                    with transaction.atomic():
                        for item in anon_cart.items.select_related('product'):
                            cart_item, created = CartItem.objects.get_or_create(
                                cart=cart,
                                product=item.product,
                                defaults={'quantity': item.quantity, 'price': item.price},
                            )
                            if not created:
                                cart_item.quantity = min(cart_item.quantity + item.quantity, 99)
                                cart_item.save()
                        anon_cart.delete()
                    messages.info(request, "Your previous cart items have been merged with your account cart.")
                except Cart.DoesNotExist:
                    pass
            request.session['cart_id'] = cart.id
        except Cart.DoesNotExist:
            if cart_id:
                try:
                    cart = Cart.objects.get(id=cart_id, user__isnull=True)
                    cart.user = request.user
                    cart.save(update_fields=['user'])
                    messages.info(request, "Your previous cart has been associated with your account.")
                except Cart.DoesNotExist:
                    cart = Cart.objects.create(user=request.user)
            else:
                cart = Cart.objects.create(user=request.user)
            request.session['cart_id'] = cart.id
    else:
        if cart_id:
            try:
                cart = Cart.objects.get(id=cart_id, user__isnull=True)
            except Cart.DoesNotExist:
                cart = Cart.objects.create(user=None)
                request.session['cart_id'] = cart.id
        else:
            cart = Cart.objects.create(user=None)
            request.session['cart_id'] = cart.id

    cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
    request.session['cart_item_count'] = cart_item_count
    return cart, cart_item_count


def index(request):
    products, query = _apply_product_filters(Product.objects.filter(is_available=True), request.GET)

    sort_by = request.GET.get('sort_by', '-created_at')
    products = products.order_by(sort_by if sort_by in VALID_SORT_VALUES else '-created_at')

    now = timezone.now()
    active_sale_banners = SaleBanner.objects.filter(
        is_active=True,
        featured_product__isnull=False,
    ).filter(
        Q(sale_end_date__isnull=True) | Q(sale_end_date__gte=now)
    ).select_related('featured_product').order_by('-updated_at')

    context = {
        'product_categories': Product.CATEGORY_CHOICES,
        'product_materials': Product.MATERIAL_CHOICES,
        'sort_options': SORT_OPTIONS,
        'products': products,
        'active_sale_banners': active_sale_banners,
        'search_query': query,
    }
    return render(request, 'index.html', context)


@require_POST
def add_to_cart(request, product_pk):
    if not request.user.is_authenticated:
        if _is_ajax(request):
            return JsonResponse(
                {
                    'success': False,
                    'message': 'Please log in to add items to your cart.',
                    'login_url': reverse('furniture_app:login'),
                },
                status=401,
            )
        messages.warning(request, "Please log in or create an account to add items to your cart.")
        return redirect('furniture_app:login')

    product = get_object_or_404(Product, pk=product_pk)
    if not product.is_available:
        return JsonResponse({'success': False, 'message': 'This product is currently unavailable.'}, status=400)

    quantity = _parse_int(request.POST.get('quantity', 1), min_val=1, max_val=99)
    if quantity is None:
        return JsonResponse({'success': False, 'message': 'Quantity must be between 1 and 99.'}, status=400)

    try:
        with transaction.atomic():
            cart, _ = get_or_create_cart(request)
            price_to_store = product.get_discounted_price() if product.on_sale else product.price

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': quantity, 'price': price_to_store},
            )
            desired_quantity = quantity if created else cart_item.quantity + quantity
            if product.stock_quantity > 0 and desired_quantity > product.stock_quantity:
                if created:
                    cart_item.delete()
                return JsonResponse(
                    {'success': False, 'message': f'Only {product.stock_quantity} left in stock.'},
                    status=400,
                )
            if not created:
                cart_item.quantity = min(desired_quantity, 99)
                cart_item.price = price_to_store
                cart_item.save()

            cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
            request.session['cart_item_count'] = cart_item_count
    except DatabaseError as exc:
        logger.exception("Database error adding product %s to cart: %s", product_pk, exc)
        return JsonResponse({'success': False, 'message': 'Could not update your cart. Please try again.'}, status=500)

    return JsonResponse({
        'success': True,
        'message': f'{product.name} added to cart!',
        'cart_item_count': cart_item_count,
    })


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    related_products = Product.objects.filter(
        category=product.category,
        is_available=True,
    ).exclude(pk=product.pk).order_by('-created_at')[:4]

    return render(request, 'product_detail.html', {
        'product': product,
        'related_products': related_products,
    })


def view_cart(request):
    cart, cart_item_count = get_or_create_cart(request)
    cart_items = cart.items.select_related('product').all()
    return render(request, 'cart.html', {
        'cart': cart,
        'cart_items': cart_items,
        'cart_item_count': cart_item_count,
    })


@require_POST
def remove_from_cart(request, item_pk):
    try:
        cart, _ = get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, pk=item_pk)

        if cart_item.cart != cart:
            return JsonResponse({'success': False, 'message': 'Unauthorized action.'}, status=403)

        cart_item.delete()
        cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        cart_total_price = cart.get_total_price()
        request.session['cart_item_count'] = cart_item_count
    except DatabaseError as exc:
        logger.exception("Database error removing cart item %s: %s", item_pk, exc)
        return JsonResponse({'success': False, 'message': 'Could not remove item. Please try again.'}, status=500)

    return JsonResponse({
        'success': True,
        'message': 'Item removed from cart.',
        'cart_item_count': cart_item_count,
        'cart_total_price': float(cart_total_price),
    })


@login_required
@require_POST
def update_cart_item_quantity(request, item_pk):
    cart_item = get_object_or_404(CartItem.objects.select_related('product', 'cart'), pk=item_pk)
    cart, _ = get_or_create_cart(request)
    current_quantity = cart_item.quantity

    if cart_item.cart != cart:
        return JsonResponse(
            {'success': False, 'message': 'Unauthorized action.', 'current_quantity': current_quantity},
            status=403,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse(
            {'success': False, 'message': 'Invalid request payload.', 'current_quantity': current_quantity},
            status=400,
        )

    new_quantity = _parse_int(data.get('quantity'), min_val=0, max_val=99)
    if new_quantity is None:
        return JsonResponse(
            {'success': False, 'message': 'Quantity must be between 0 and 99.', 'current_quantity': current_quantity},
            status=400,
        )

    if new_quantity > 0 and cart_item.product.stock_quantity > 0 and new_quantity > cart_item.product.stock_quantity:
        return JsonResponse(
            {
                'success': False,
                'message': f'Only {cart_item.product.stock_quantity} left in stock.',
                'current_quantity': current_quantity,
            },
            status=400,
        )

    try:
        if new_quantity == 0:
            product_name = cart_item.product.name
            cart_item.delete()
            message = f"{product_name} removed from cart."
            item_total = 0.0
        else:
            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity'])
            message = f"Quantity for {cart_item.product.name} updated."
            item_total = float(cart_item.get_total())

        cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        cart_total_price = cart.get_total_price()
        request.session['cart_item_count'] = cart_item_count
    except DatabaseError as exc:
        logger.exception("Database error updating cart item %s: %s", item_pk, exc)
        return JsonResponse(
            {'success': False, 'message': 'Could not update quantity.', 'current_quantity': current_quantity},
            status=500,
        )

    return JsonResponse({
        'success': True,
        'message': message,
        'new_quantity': new_quantity,
        'item_total': item_total,
        'cart_item_count': cart_item_count,
        'cart_total_price': float(cart_total_price),
    })


@login_required
def checkout(request):
    cart, _ = get_or_create_cart(request)
    if not cart.items.exists():
        messages.warning(request, "Your cart is empty. Please add items before checking out.")
        return redirect('furniture_app:view_cart')

    if request.method == 'POST':
        shipping_address_id = request.POST.get('shipping_address')
        if not shipping_address_id:
            messages.error(request, "Please select a shipping address.")
            return redirect('furniture_app:checkout')

        try:
            shipping_address = Address.objects.get(pk=shipping_address_id, user=request.user)
        except (Address.DoesNotExist, ValueError):
            messages.error(request, "Selected shipping address is invalid.")
            return redirect('furniture_app:checkout')

        payment_method = request.POST.get('payment_method', 'Cash on Delivery').strip()
        if payment_method not in ('Cash on Delivery', 'COD'):
            messages.error(request, "Invalid payment method selected.")
            return redirect('furniture_app:checkout')

        try:
            with transaction.atomic():
                cart_items = list(cart.items.select_related('product').all())
                for item in cart_items:
                    if not item.product.is_available:
                        messages.error(request, f"{item.product.name} is no longer available.")
                        return redirect('furniture_app:view_cart')
                    if item.product.stock_quantity > 0 and item.quantity > item.product.stock_quantity:
                        messages.error(request, f"Only {item.product.stock_quantity} of {item.product.name} available.")
                        return redirect('furniture_app:view_cart')

                total_price = sum(item.get_total() for item in cart_items)
                order = Order.objects.create(
                    user=request.user,
                    total_price=total_price,
                    status='PENDING',
                    shipping_address=shipping_address,
                    payment_method='Cash on Delivery',
                )
                OrderItem.objects.bulk_create([
                    OrderItem(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        price=item.price,
                    )
                    for item in cart_items
                ])
                for item in cart_items:
                    if item.product.stock_quantity > 0:
                        item.product.stock_quantity = max(0, item.product.stock_quantity - item.quantity)
                        item.product.save(update_fields=['stock_quantity'])

                cart.items.all().delete()
                request.session['cart_item_count'] = 0
        except (DatabaseError, IntegrityError) as exc:
            logger.exception("Checkout failed for user %s: %s", request.user.pk, exc)
            messages.error(request, "We could not complete your order due to a system error. Please try again.")
            return redirect('furniture_app:checkout')

        messages.success(request, f"Your order #{order.id} has been placed successfully!")
        return redirect('furniture_app:order_detail', order_pk=order.pk)

    return render(request, 'payment_method.html', {
        'cart': cart,
        'user_addresses': request.user.addresses.all(),
    })


@login_required
def user_profile(request):
    addresses = request.user.addresses.all()
    orders = request.user.orders.all().order_by('-order_date').prefetch_related('items__product').select_related('shipping_address')
    user_profile_form = UserProfileForm(instance=request.user)
    address_form = AddressForm()

    if request.method == 'POST':
        if 'update_profile_submit' in request.POST:
            user_profile_form = UserProfileForm(request.POST, instance=request.user)
            if user_profile_form.is_valid():
                user_profile_form.save()
                messages.success(request, "Profile updated successfully!")
                return redirect('furniture_app:user_profile')
            messages.error(request, "Please correct the errors in your profile form.")
        elif 'add_address_submit' in request.POST:
            address_form = AddressForm(request.POST)
            if address_form.is_valid():
                address = address_form.save(commit=False)
                address.user = request.user
                address.save()
                messages.success(request, "Address added successfully!")
                return redirect('furniture_app:user_profile')
            messages.error(request, "Please correct the errors in your address form.")

    return render(request, 'userprofile.html', {
        'user': request.user,
        'addresses': addresses,
        'orders': orders,
        'user_profile_form': user_profile_form,
        'address_form': address_form,
    })


@login_required
def user_settings(request):
    profile_form = UserProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        if 'update_account_submit' in request.POST:
            profile_form = UserProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Account details updated.")
                return redirect('furniture_app:user_settings')
            messages.error(request, "Please fix the errors in your account details.")
        elif 'change_password_submit' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated successfully.")
                return redirect('furniture_app:user_settings')
            messages.error(request, "Please fix the errors in your password form.")

    return render(request, 'settings.html', {
        'profile_form': profile_form,
        'password_form': password_form,
    })


@login_required
def add_address(request):
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Address added successfully!")
            return redirect('furniture_app:user_profile')
    else:
        form = AddressForm()

    return render(request, 'add_address.html', {'form': form})


@login_required
def edit_address(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, "Address updated successfully!")
            return redirect('furniture_app:user_profile')
    else:
        form = AddressForm(instance=address)

    return render(request, 'edit_address.html', {'form': form, 'address': address})


@login_required
@require_POST
def set_default_address(request, pk):
    address_to_set_default = get_object_or_404(Address, pk=pk, user=request.user)
    address_to_set_default.is_default = True
    address_to_set_default.save()
    messages.success(request, "Default address updated.")
    return redirect('furniture_app:user_profile')


@login_required
@require_POST
def delete_address(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if address.is_default:
        messages.error(request, "Cannot delete the default address. Please set another address as default first.")
    else:
        address.delete()
        messages.success(request, "Address deleted successfully.")
    return redirect('furniture_app:user_profile')


@staff_member_required
def admin_orders_dashboard(request):
    all_orders = Order.objects.select_related('user', 'shipping_address').prefetch_related('items__product').order_by('-order_date')
    return render(request, 'admin_orders_dashboard.html', {
        'all_orders': all_orders,
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required
def update_order_status(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk)
    is_ajax = _is_ajax(request)

    if not request.user.is_staff:
        if order.user != request.user:
            message = 'You do not have permission to update this order.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=403)
            messages.error(request, message)
            return redirect('furniture_app:user_profile')

        if order.status not in ['PENDING', 'PROCESSING']:
            message = 'Only pending or processing orders can be cancelled.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=400)
            messages.error(request, message)
            return redirect('furniture_app:user_profile')

    if request.method == 'POST':
        new_status = request.POST.get('status')

        if not request.user.is_staff and new_status != 'CANCELLED':
            message = 'You may only cancel your order.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=403)
            messages.error(request, message)
            return redirect('furniture_app:user_profile')

        if new_status in VALID_ORDER_STATUSES:
            try:
                order.status = new_status
                order.save(update_fields=['status'])
            except DatabaseError as exc:
                logger.exception("Failed updating order %s status: %s", order_pk, exc)
                message = "Could not update order status. Please try again."
                if is_ajax:
                    return JsonResponse({'success': False, 'message': message}, status=500)
                messages.error(request, message)
                return redirect('furniture_app:admin_view_all_orders' if request.user.is_staff else 'furniture_app:user_profile')

            message = f"Order #{order.id} status updated to {order.get_status_display()}."
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'new_status_display': order.get_status_display(),
                    'new_status_value': order.status,
                })
            messages.success(request, message)
            return redirect('furniture_app:admin_view_all_orders' if request.user.is_staff else 'furniture_app:user_profile')

        message = "Invalid status provided."
        if is_ajax:
            return JsonResponse({'success': False, 'message': message}, status=400)
        messages.error(request, message)
        return redirect('furniture_app:admin_view_all_orders' if request.user.is_staff else 'furniture_app:user_profile')

    if is_ajax:
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)
    if request.user.is_staff:
        return redirect('furniture_app:admin_view_all_orders')
    return redirect('furniture_app:order_detail', order_pk=order_pk)


@login_required
@require_POST
def delete_order(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk)
    if order.user != request.user and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'You do not have permission to delete this order.'}, status=403)

    if order.status != 'CANCELLED' and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Only cancelled orders can be removed from your list.'}, status=400)

    try:
        order.delete()
    except DatabaseError as exc:
        logger.exception("Failed deleting order %s: %s", order_pk, exc)
        return JsonResponse({'success': False, 'message': 'Could not remove order. Please try again.'}, status=500)

    return JsonResponse({'success': True, 'message': f'Order #{order_pk} has been removed from your list.'})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('furniture_app:index')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect('furniture_app:index')
    else:
        form = CustomUserCreationForm()

    return render(request, 'signup.html', {'form': form})


@login_required
def order_detail(request, order_pk):
    order = get_object_or_404(Order.objects.select_related('user', 'shipping_address'), pk=order_pk)
    if not request.user.is_staff and order.user != request.user:
        messages.error(request, "You do not have permission to view this order.")
        return redirect('furniture_app:user_profile')

    order_items = order.items.select_related('product').all()
    return render(request, 'order_detail.html', {
        'order': order,
        'order_items': order_items,
    })


@require_GET
def api_health(request):
    try:
        count = Product.objects.filter(is_available=True).count()
    except DatabaseError as exc:
        logger.exception("Health check database error: %s", exc)
        return JsonResponse({'status': 'error', 'message': 'Database unavailable'}, status=503)

    return JsonResponse({'status': 'ok', 'products_count': count})


@require_GET
def api_product_list(request):
    try:
        products, _ = _apply_product_filters(Product.objects.filter(is_available=True).order_by('-created_at'), request.GET)
        limit = _parse_int(request.GET.get('limit', 50), min_val=1, max_val=100) or 50
        offset = _parse_int(request.GET.get('offset', 0), min_val=0) or 0
        total_count = products.count()
        page_items = products[offset:offset + limit]
        return JsonResponse({
            'count': total_count,
            'limit': limit,
            'offset': offset,
            'products': [_serialize_product(p) for p in page_items],
        })
    except DatabaseError as exc:
        logger.exception("API product list error: %s", exc)
        return JsonResponse({'error': 'Unable to fetch products.'}, status=500)


@require_GET
def api_product_detail(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found.'}, status=404)
    except DatabaseError as exc:
        logger.exception("API product detail error: %s", exc)
        return JsonResponse({'error': 'Unable to fetch product.'}, status=500)
    return JsonResponse(_serialize_product(product))


def error_400(request, exception=None):
    return render(request, '400.html', status=400)


def error_403(request, exception=None):
    return render(request, '403.html', status=403)


def error_404(request, exception=None):
    return render(request, '404.html', status=404)


def error_500(request):
    return render(request, '500.html', status=500)
