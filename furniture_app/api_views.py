import logging
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Order, Product
from .services import CartService, CatalogService

logger = logging.getLogger(__name__)


def _parse_int(value, default, min_val=None, max_val=None):
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return default
    if min_val is not None and parsed < min_val:
        return min_val
    if max_val is not None and parsed > max_val:
        return max_val
    return parsed


@require_GET
def api_health(request):
    try:
        count = Product.objects.filter(is_available=True).count()
    except DatabaseError as exc:
        logger.exception('Health check database error: %s', exc)
        return JsonResponse({'status': 'error', 'message': 'Database unavailable'}, status=503)

    return JsonResponse({'status': 'ok', 'products_count': count})


@require_GET
def api_product_list(request):
    try:
        products, _ = CatalogService.filter_products(request.GET)
        limit = _parse_int(request.GET.get('limit', 50), 50, min_val=1, max_val=100)
        offset = _parse_int(request.GET.get('offset', 0), 0, min_val=0)
        total_count = products.count()
        page_items = products[offset:offset + limit]
        return JsonResponse({
            'count': total_count,
            'limit': limit,
            'offset': offset,
            'products': [CatalogService.serialize_product(p) for p in page_items],
        })
    except DatabaseError as exc:
        logger.exception('API product list error: %s', exc)
        return JsonResponse({'error': 'Unable to fetch products.'}, status=500)


@require_GET
def api_product_detail(request, pk):
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found.'}, status=404)
    except DatabaseError as exc:
        logger.exception('API product detail error: %s', exc)
        return JsonResponse({'error': 'Unable to fetch product.'}, status=500)
    return JsonResponse(CatalogService.serialize_product(product))


@require_GET
def api_cart_detail(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    cart, count, _ = CartService.get_or_create_cart(request)
    items = [
        {
            'id': item.pk,
            'product_id': item.product_id,
            'product_name': item.product.name,
            'quantity': item.quantity,
            'unit_price': float(item.price),
            'subtotal': float(item.get_total()),
        }
        for item in cart.items.select_related('product').all()
    ]
    return JsonResponse({
        'cart_id': cart.pk,
        'item_count': count,
        'total_price': float(cart.get_total_price()),
        'items': items,
    })


@require_GET
def api_order_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    orders = (
        Order.objects.filter(user=request.user)
        .select_related('shipping_address')
        .prefetch_related('items__product')
        .order_by('-order_date')
    )
    return JsonResponse({
        'count': orders.count(),
        'orders': [
            {
                'id': o.pk,
                'status': o.status,
                'status_display': o.get_status_display(),
                'total_price': float(o.total_price),
                'payment_method': o.payment_method,
                'order_date': o.order_date.isoformat(),
                'items_count': o.items.count(),
            }
            for o in orders
        ],
    })


@require_GET
def api_order_detail(request, order_pk):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    try:
        order = Order.objects.select_related('shipping_address').prefetch_related('items__product').get(pk=order_pk)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found.'}, status=404)

    if not request.user.is_staff and order.user_id != request.user.id:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    return JsonResponse({
        'id': order.pk,
        'status': order.status,
        'status_display': order.get_status_display(),
        'total_price': float(order.total_price),
        'payment_method': order.payment_method,
        'order_date': order.order_date.isoformat(),
        'items': [
            {
                'product_id': item.product_id,
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': float(item.price),
                'subtotal': float(item.get_total()),
            }
            for item in order.items.all()
        ],
    })
