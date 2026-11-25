import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.views.decorators.http import require_GET, require_POST

from .models import Product, SaleBanner, Cart, CartItem, Address, Order, OrderItem
from .forms import AddressForm, UserProfileForm, CustomUserCreationForm


def _is_ajax(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


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
                    for item in anon_cart.items.all():
                        cart_item, created = CartItem.objects.get_or_create(
                            cart=cart,
                            product=item.product,
                            defaults={'quantity': item.quantity, 'price': item.price},
                        )
                        if not created:
                            cart_item.quantity += item.quantity
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
                    cart.save()
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
    product_categories = Product.CATEGORY_CHOICES
    product_materials = Product.MATERIAL_CHOICES

    sort_options = [
        {'value': '-created_at', 'label': 'Newest Arrivals'},
        {'value': 'price', 'label': 'Price: Low to High'},
        {'value': '-price', 'label': 'Price: High to Low'},
        {'value': 'name', 'label': 'Name: A-Z'},
    ]

    products = Product.objects.filter(is_available=True)

    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))

    category = request.GET.get('category')
    if category:
        products = products.filter(category=category)

    material = request.GET.get('material')
    if material:
        products = products.filter(material=material)

    min_price = request.GET.get('min_price')
    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass

    max_price = request.GET.get('max_price')
    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass

    requires_assembly = request.GET.get('requires_assembly')
    if requires_assembly == 'true':
        products = products.filter(requires_assembly=True)
    elif requires_assembly == 'false':
        products = products.filter(requires_assembly=False)

    in_stock_only = request.GET.get('is_available')
    if in_stock_only == 'true':
        products = products.filter(is_available=True, stock_quantity__gt=0)

    sort_by = request.GET.get('sort_by', '-created_at')
    if sort_by in [opt['value'] for opt in sort_options]:
        products = products.order_by(sort_by)
    else:
        products = products.order_by('-created_at')

    now = timezone.now()
    active_sale_banners = SaleBanner.objects.filter(
        is_active=True,
        featured_product__isnull=False,
    ).filter(
        Q(sale_end_date__isnull=True) | Q(sale_end_date__gte=now)
    ).select_related('featured_product').order_by('-updated_at')

    _, cart_item_count = get_or_create_cart(request)

    context = {
        'product_categories': product_categories,
        'product_materials': product_materials,
        'sort_options': sort_options,
        'products': products,
        'active_sale_banners': active_sale_banners,
        'cart_item_count': cart_item_count,
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

    try:
        quantity = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid quantity provided.'}, status=400)

    if quantity < 1 or quantity > 99:
        return JsonResponse({'success': False, 'message': 'Quantity must be between 1 and 99.'}, status=400)

    cart, _ = get_or_create_cart(request)
    price_to_store = product.get_discounted_price() if product.on_sale else product.price

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': quantity, 'price': price_to_store},
    )
    if not created:
        cart_item.quantity = min(cart_item.quantity + quantity, 99)
        cart_item.price = price_to_store
        cart_item.save()

    cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
    request.session['cart_item_count'] = cart_item_count

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
    ).exclude(pk=product.pk).order_by('?')[:4]

    _, cart_item_count = get_or_create_cart(request)

    context = {
        'product': product,
        'related_products': related_products,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'product_detail.html', context)


def view_cart(request):
    cart, cart_item_count = get_or_create_cart(request)
    cart_items = cart.items.select_related('product').all()
    context = {
        'cart': cart,
        'cart_items': cart_items,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'cart.html', context)


@require_POST
def remove_from_cart(request, item_pk):
    cart, _ = get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, pk=item_pk)

    if cart_item.cart != cart:
        return JsonResponse({'success': False, 'message': 'Unauthorized action.'}, status=403)

    cart_item.delete()

    cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
    cart_total_price = cart.get_total_price()
    request.session['cart_item_count'] = cart_item_count

    return JsonResponse({
        'success': True,
        'message': 'Item removed from cart.',
        'cart_item_count': cart_item_count,
        'cart_total_price': float(cart_total_price),
    })


@login_required
@require_POST
def update_cart_item_quantity(request, item_pk):
    cart_item = get_object_or_404(CartItem, pk=item_pk)
    cart, _ = get_or_create_cart(request)
    current_quantity_before_change = cart_item.quantity

    if cart_item.cart != cart:
        return JsonResponse(
            {
                'success': False,
                'message': 'Unauthorized action.',
                'current_quantity': current_quantity_before_change,
            },
            status=403,
        )

    try:
        data = json.loads(request.body)
        new_quantity = int(data.get('quantity'))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse(
            {
                'success': False,
                'message': 'Invalid quantity provided.',
                'current_quantity': current_quantity_before_change,
            },
            status=400,
        )

    if new_quantity < 0 or new_quantity > 99:
        return JsonResponse(
            {
                'success': False,
                'message': 'Quantity must be between 0 and 99.',
                'current_quantity': current_quantity_before_change,
            },
            status=400,
        )

    if new_quantity == 0:
        product_name = cart_item.product.name
        cart_item.delete()
        message = f"{product_name} removed from cart."
        item_total = 0.0
    else:
        cart_item.quantity = new_quantity
        cart_item.save()
        message = f"Quantity for {cart_item.product.name} updated."
        item_total = float(cart_item.get_total())

    cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
    cart_total_price = cart.get_total_price()
    request.session['cart_item_count'] = cart_item_count

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
    cart, cart_item_count = get_or_create_cart(request)
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
        except Address.DoesNotExist:
            messages.error(request, "Selected shipping address is invalid.")
            return redirect('furniture_app:checkout')

        with transaction.atomic():
            cart_items = list(cart.items.select_related('product').all())
            total_price = sum(item.get_total() for item in cart_items)
            order = Order.objects.create(
                user=request.user,
                total_price=total_price,
                status='PENDING',
                shipping_address=shipping_address,
                payment_method='COD',
            )
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price=item.price,
                )
                if item.product.stock_quantity > 0:
                    item.product.stock_quantity = max(0, item.product.stock_quantity - item.quantity)
                    item.product.save(update_fields=['stock_quantity'])

            cart.items.all().delete()
            request.session['cart_item_count'] = 0

        messages.success(request, f"Your order #{order.id} has been placed successfully!")
        return redirect('furniture_app:order_detail', order_pk=order.pk)

    user_addresses = request.user.addresses.all()
    context = {
        'cart': cart,
        'cart_item_count': cart_item_count,
        'user_addresses': user_addresses,
    }
    return render(request, 'payment_method.html', context)


@login_required
def user_profile(request):
    addresses = request.user.addresses.all()
    orders = request.user.orders.all().order_by('-order_date').prefetch_related('items__product')
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

    _, cart_item_count = get_or_create_cart(request)

    context = {
        'user': request.user,
        'addresses': addresses,
        'orders': orders,
        'cart_item_count': cart_item_count,
        'user_profile_form': user_profile_form,
        'address_form': address_form,
    }
    return render(request, 'userprofile.html', context)


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

    _, cart_item_count = get_or_create_cart(request)
    context = {
        'form': form,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'add_address.html', context)


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

    _, cart_item_count = get_or_create_cart(request)
    context = {
        'form': form,
        'address': address,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'edit_address.html', context)


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
    status_choices = Order.STATUS_CHOICES

    _, cart_item_count = get_or_create_cart(request)

    context = {
        'all_orders': all_orders,
        'status_choices': status_choices,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'admin_orders_dashboard.html', context)


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

        if new_status and new_status in [choice[0] for choice in Order.STATUS_CHOICES]:
            order.status = new_status
            order.save()
            message = f"Order #{order.id} status updated to {order.get_status_display()}."

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'new_status_display': order.get_status_display(),
                    'new_status_value': order.status,
                })
            messages.success(request, message)
            if request.user.is_staff:
                return redirect('furniture_app:admin_view_all_orders')
            return redirect('furniture_app:user_profile')

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

    order.delete()
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

    _, cart_item_count = get_or_create_cart(request)
    context = {
        'form': form,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'signup.html', context)


@login_required
def order_detail(request, order_pk):
    order = get_object_or_404(Order.objects.select_related('user', 'shipping_address'), pk=order_pk)
    if not request.user.is_staff and order.user != request.user:
        messages.error(request, "You do not have permission to view this order.")
        return redirect('furniture_app:user_profile')

    order_items = order.items.select_related('product').all()
    _, cart_item_count = get_or_create_cart(request)

    context = {
        'order': order,
        'order_items': order_items,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'order_detail.html', context)


@require_GET
def api_health(request):
    return JsonResponse({
        'status': 'ok',
        'products_count': Product.objects.filter(is_available=True).count(),
    })


@require_GET
def api_product_list(request):
    products = Product.objects.filter(is_available=True).order_by('-created_at')

    category = request.GET.get('category')
    if category:
        products = products.filter(category=category)

    material = request.GET.get('material')
    if material:
        products = products.filter(material=material)

    on_sale = request.GET.get('on_sale')
    if on_sale == 'true':
        products = products.filter(on_sale=True)

    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))

    return JsonResponse({
        'count': products.count(),
        'products': [_serialize_product(p) for p in products],
    })


@require_GET
def api_product_detail(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found.'}, status=404)
    return JsonResponse(_serialize_product(product))
