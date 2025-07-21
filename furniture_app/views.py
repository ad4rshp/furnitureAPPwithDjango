import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db.models import Q, F, Sum
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

from .models import Product, SaleBanner, Cart, CartItem, Address, Order, OrderItem
from .forms import AddressForm, UserProfileForm


def get_or_create_cart(request):
    cart_id = request.session.get('cart_id')
    cart = None
    cart_item_count = 0

    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            if cart_id and str(cart.id) != cart_id:
                try:
                    anon_cart = Cart.objects.get(id=cart_id, user__isnull=True)
                    for item in anon_cart.items.all():
                        cart_item, created = CartItem.objects.get_or_create(
                            cart=cart,
                            product=item.product,
                            defaults={'quantity': item.quantity, 'price': item.price}
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


    category = request.GET.get('category')
    if category:
        products = products.filter(category=category)

    material = request.GET.get('material')
    if material:
        products = products.filter(material=material)

    min_price = request.GET.get('min_price')
    if min_price:
        try:
            min_price = float(min_price)
            products = products.filter(price__gte=min_price)
        except ValueError:
            pass

    max_price = request.GET.get('max_price')
    if max_price:
        try:
            max_price = float(max_price)
            products = products.filter(price__lte=max_price)
        except ValueError:
            pass

    requires_assembly = request.GET.get('requires_assembly')
    if requires_assembly == 'true':
        products = products.filter(requires_assembly=True)
    elif requires_assembly == 'false':
        products = products.filter(requires_assembly=False)

    is_available_param = request.GET.get('is_available')
    if is_available_param == 'true':
        products = products.filter(is_available=True)


    sort_by = request.GET.get('sort_by', '-created_at')
    if sort_by in [opt['value'] for opt in sort_options]:
        products = products.order_by(sort_by)
    else:
        products = products.order_by('-created_at')

    active_sale_banners = SaleBanner.objects.filter(
        is_active=True,
        sale_end_date__gte=timezone.now()
    ).order_by('-updated_at')

    cart, cart_item_count = get_or_create_cart(request)


    context = {
        'product_categories': product_categories,
        'product_materials': product_materials,
        'sort_options': sort_options,
        'products': products,
        'active_sale_banners': active_sale_banners,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'index.html', context)


def add_to_cart(request, product_pk):
    if not request.user.is_authenticated:
        messages.warning(request, "Please log in or create an account to add items to your cart.")
        return redirect('furniture_app:login')

    if request.method == 'POST':
        product = get_object_or_404(Product, pk=product_pk)
        quantity = int(request.POST.get('quantity', 1))

        cart, _ = get_or_create_cart(request)
        price_to_store = product.get_discounted_price() if product.on_sale else product.price

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity, 'price': price_to_store}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        request.session['cart_item_count'] = cart_item_count
        messages.success(request, f"{product.name} added to cart!")

        return JsonResponse({
            'success': True,
            'message': f'{product.name} added to cart!',
            'cart_item_count': cart_item_count
        })
    return JsonResponse({'success': False, 'message': 'Invalid request.'})


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    related_products = Product.objects.filter(
        category=product.category,
        is_available=True
    ).exclude(pk=product.pk).order_by('?')[:4]

    cart, cart_item_count = get_or_create_cart(request)

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


def remove_from_cart(request, item_pk):
    if request.method == 'POST':
        cart_item = get_object_or_404(CartItem, pk=item_pk)
        cart_item.delete()
        
        cart, cart_item_count = get_or_create_cart(request)
        cart_total_price = cart.get_total_price()

        messages.info(request, "Item removed from cart.")
        return JsonResponse({
            'success': True,
            'message': 'Item removed from cart.',
            'cart_item_count': cart_item_count,
            'cart_total_price': cart_total_price,
        })
    return JsonResponse({'success': False, 'message': 'Invalid request.'})


@login_required
def update_cart_item_quantity(request, item_pk):
    if request.method == 'POST':
        cart_item = get_object_or_404(CartItem, pk=item_pk)
        cart, _ = get_or_create_cart(request)

        current_quantity_before_change = cart_item.quantity

        if cart_item.cart != cart:
            return JsonResponse({'success': False, 'message': 'Unauthorized action.', 'current_quantity': current_quantity_before_change}, status=403)

        try:
            data = json.loads(request.body)
            new_quantity = int(data.get('quantity'))
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({'success': False, 'message': 'Invalid quantity provided.', 'current_quantity': current_quantity_before_change}, status=400)

        if new_quantity < 0:
            return JsonResponse({'success': False, 'message': 'Quantity cannot be negative.', 'current_quantity': current_quantity_before_change}, status=400)

        if new_quantity == 0:
            cart_item.delete()
            message = f"{cart_item.product.name} removed from cart."
        else:
            cart_item.quantity = new_quantity
            cart_item.save()
            message = f"Quantity for {cart_item.product.name} updated."

        cart_item_count = cart.items.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
        cart_total_price = cart.get_total_price()
        request.session['cart_item_count'] = cart_item_count

        return JsonResponse({
            'success': True,
            'message': message,
            'new_quantity': new_quantity,
            'item_total': float(cart_item.get_total()) if new_quantity > 0 else 0.0, # Ensure float
            'cart_item_count': cart_item_count,
            'cart_total_price': float(cart_total_price), # Ensure float
        })
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)


def checkout(request):
    cart, cart_item_count = get_or_create_cart(request)
    if not cart.items.exists():
        messages.warning(request, "Your cart is empty. Please add items before checking out.")
        return redirect('furniture_app:view_cart')

    if request.method == 'POST':
        shipping_address_id = request.POST.get('shipping_address')
        shipping_address = None
        if shipping_address_id:
            try:
                shipping_address = Address.objects.get(pk=shipping_address_id, user=request.user)
            except Address.DoesNotExist:
                messages.error(request, "Selected shipping address is invalid.")
                return redirect('furniture_app:checkout')
        else:
            messages.error(request, "Please select a shipping address.")
            return redirect('furniture_app:checkout')

        total_price = cart.get_total_price()
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            total_price=total_price,
            status='PENDING',
            shipping_address=shipping_address,
            payment_method='COD'
        )
        for item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=item.product,
                quantity=item.quantity,
                price=item.price
            )
        cart.items.all().delete()
        request.session['cart_item_count'] = 0
        messages.success(request, f"Your order #{order.id} has been placed successfully!")
        return redirect('furniture_app:order_detail', order_pk=order.pk)

    user_addresses = []
    if request.user.is_authenticated:
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

    if request.method == 'POST':
        if 'update_profile_submit' in request.POST:
            user_profile_form = UserProfileForm(request.POST, instance=request.user)
            if user_profile_form.is_valid():
                user_profile_form.save()
                messages.success(request, "Profile updated successfully!")
                return redirect('furniture_app:user_profile')
            else:
                messages.error(request, "Please correct the errors in your profile form.")
        elif 'add_address_submit' in request.POST:
            address_form = AddressForm(request.POST)
            if address_form.is_valid():
                address = address_form.save(commit=False)
                address.user = request.user
                address.save()
                messages.success(request, "Address added successfully!")
                return redirect('furniture_app:user_profile')
            else:
                messages.error(request, "Please correct the errors in your address form.")
    else:
        user_profile_form = UserProfileForm(instance=request.user)
        address_form = AddressForm()

    cart, cart_item_count = get_or_create_cart(request)

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
    
    cart, cart_item_count = get_or_create_cart(request)
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
    
    cart, cart_item_count = get_or_create_cart(request)
    context = {
        'form': form,
        'address': address,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'edit_address.html', context)


@login_required
def set_default_address(request, pk):
    if request.method == 'POST':
        address_to_set_default = get_object_or_404(Address, pk=pk, user=request.user)
        request.user.addresses.filter(is_default=True).update(is_default=False)
        address_to_set_default.is_default = True
        address_to_set_default.save()
        messages.success(request, "Default address updated.")
    return redirect('furniture_app:user_profile')


@login_required
def delete_address(request, pk):
    if request.method == 'POST':
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

    cart, cart_item_count = get_or_create_cart(request)

    context = {
        'all_orders': all_orders,
        'status_choices': status_choices,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'admin_orders_dashboard.html', context)


@login_required 
def update_order_status(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk)

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or \
              request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    if not request.user.is_staff:
        if order.user != request.user:
            message = 'You do not have permission to update this order.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=403)
            else:
                messages.error(request, message)
                return redirect('furniture_app:user_profile')

        if order.status not in ['PENDING', 'PROCESSING']:
            message = 'Only pending or processing orders can be cancelled.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=400)
            else:
                messages.error(request, message)
                return redirect('furniture_app:user_profile')

    if request.method == 'POST':
        new_status = request.POST.get('status')

        if new_status and new_status in [choice[0] for choice in Order.STATUS_CHOICES]:
            order.status = new_status
            order.save()
            message = f"Order #{order.id} status updated to {order.get_status_display()}."

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'new_status_display': order.get_status_display(),
                    'new_status_value': order.status
                })
            else:
                messages.success(request, message)
                return redirect('furniture_app:admin_view_all_orders')
        else:
            message = "Invalid status provided."
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=400)
            else:
                messages.error(request, message)
                return redirect('furniture_app:admin_view_all_orders')
    
    if is_ajax:
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)
    else:
        if request.user.is_staff:
            return redirect('furniture_app:admin_orders_dashboard')
        else:
            return redirect('furniture_app:order_detail', order_pk=order_pk)


@login_required
def delete_order(request, order_pk):
    if request.method == 'POST':
        order = get_object_or_404(Order, pk=order_pk)
        if order.user != request.user and not request.user.is_staff:
            return JsonResponse({'success': False, 'message': 'You do not have permission to delete this order.'}, status=403)
        
        if order.status != 'CANCELLED' and not request.user.is_staff:
            return JsonResponse({'success': False, 'message': 'Only cancelled orders can be removed from your list.'}, status=400)
        
        order.delete()
        return JsonResponse({'success': True, 'message': f'Order #{order_pk} has been removed from your list.'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)


def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect('furniture_app:index')
    else:
        form = UserCreationForm()
    
    cart, cart_item_count = get_or_create_cart(request)
    context = {
        'form': form,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'signup.html', context)


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('furniture_app:index')
    else:
        form = AuthenticationForm()
    
    cart, cart_item_count = get_or_create_cart(request)
    context = {
        'form': form,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'login.html', context)


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    # Redirect to the login page after logout
    return redirect('furniture_app:login')


def order_detail(request, order_pk):
    order = get_object_or_404(Order.objects.select_related('user', 'shipping_address'), pk=order_pk)
    if not request.user.is_staff and order.user != request.user:
        messages.error(request, "You do not have permission to view this order.")
        return redirect('furniture_app:user_profile')

    order_items = order.items.select_related('product').all()
    
    cart, cart_item_count = get_or_create_cart(request)

    context = {
        'order': order,
        'order_items': order_items,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'order_detail.html', context)
