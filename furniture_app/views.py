import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db import DatabaseError
from django.db.models import Sum
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.views.decorators.http import require_POST

from .models import Product, CartItem, Address, Order
from .forms import AddressForm, UserProfileForm, CustomUserCreationForm
from .services import CartService, CatalogService, DomainError, OrderService, SORT_OPTIONS

logger = logging.getLogger(__name__)


def _is_ajax(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


def index(request):
    products, query = CatalogService.filter_products(request.GET)
    return render(request, 'index.html', {
        'product_categories': Product.CATEGORY_CHOICES,
        'product_materials': Product.MATERIAL_CHOICES,
        'sort_options': SORT_OPTIONS,
        'products': products,
        'active_sale_banners': CatalogService.active_banners(),
        'search_query': query,
    })


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
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Quantity must be between 1 and 99.'}, status=400)

    try:
        cart, _, merged = CartService.get_or_create_cart(request)
        if merged:
            messages.info(request, "Your previous cart items have been merged with your account cart.")
        cart_item_count = CartService.add_item(cart, product, quantity)
        request.session['cart_item_count'] = cart_item_count
    except DomainError as exc:
        return JsonResponse({'success': False, 'message': exc.message}, status=exc.status_code)
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
    cart, cart_item_count, _ = CartService.get_or_create_cart(request)
    cart_items = cart.items.select_related('product').all()
    return render(request, 'cart.html', {
        'cart': cart,
        'cart_items': cart_items,
        'cart_item_count': cart_item_count,
    })


@require_POST
def remove_from_cart(request, item_pk):
    try:
        cart, _, _ = CartService.get_or_create_cart(request)
        cart_item = get_object_or_404(CartItem, pk=item_pk)
        if cart_item.cart_id != cart.id:
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
    cart, _, _ = CartService.get_or_create_cart(request)
    current_quantity = cart_item.quantity

    try:
        data = json.loads(request.body)
        new_quantity = int(data.get('quantity'))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse(
            {'success': False, 'message': 'Invalid quantity provided.', 'current_quantity': current_quantity},
            status=400,
        )

    try:
        payload = CartService.update_item_quantity(cart, cart_item, new_quantity)
        request.session['cart_item_count'] = payload['cart_item_count']
        return JsonResponse({'success': True, **payload})
    except DomainError as exc:
        return JsonResponse(
            {'success': False, 'message': exc.message, 'current_quantity': current_quantity},
            status=exc.status_code,
        )
    except DatabaseError as exc:
        logger.exception("Database error updating cart item %s: %s", item_pk, exc)
        return JsonResponse(
            {'success': False, 'message': 'Could not update quantity.', 'current_quantity': current_quantity},
            status=500,
        )


@login_required
def checkout(request):
    cart, _, _ = CartService.get_or_create_cart(request)
    if not cart.items.exists():
        messages.warning(request, "Your cart is empty. Please add items before checking out.")
        return redirect('furniture_app:view_cart')

    if request.method == 'POST':
        shipping_address_id = request.POST.get('shipping_address')
        payment_method = (request.POST.get('payment_method') or 'Cash on Delivery').strip()
        try:
            order = OrderService.place_order(request.user, cart, shipping_address_id, payment_method)
            request.session['cart_item_count'] = 0
            messages.success(request, f"Your order #{order.id} has been placed successfully!")
            return redirect('furniture_app:order_detail', order_pk=order.pk)
        except DomainError as exc:
            messages.error(request, exc.message)
            return redirect('furniture_app:checkout')

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

    if request.method != 'POST':
        if is_ajax:
            return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)
        if request.user.is_staff:
            return redirect('furniture_app:admin_view_all_orders')
        return redirect('furniture_app:order_detail', order_pk=order_pk)

    new_status = request.POST.get('status')
    try:
        OrderService.update_status(request.user, order, new_status)
    except DomainError as exc:
        if is_ajax:
            return JsonResponse({'success': False, 'message': exc.message}, status=exc.status_code)
        messages.error(request, exc.message)
        return redirect('furniture_app:admin_view_all_orders' if request.user.is_staff else 'furniture_app:user_profile')
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


def error_400(request, exception=None):
    return render(request, '400.html', status=400)


def error_403(request, exception=None):
    return render(request, '403.html', status=403)


def error_404(request, exception=None):
    return render(request, '404.html', status=404)


def error_500(request):
    return render(request, '500.html', status=500)
