import logging
from django.db import DatabaseError
from django.db.models import Sum
from .models import Cart

logger = logging.getLogger(__name__)


def cart_context(request):
    """Provide cart_item_count to all templates without duplicating queries in every view."""
    cart_item_count = 0
    try:
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user).first()
            if cart:
                cart_item_count = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
        else:
            cart_id = request.session.get('cart_id')
            if cart_id:
                cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()
                if cart:
                    cart_item_count = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
    except DatabaseError as exc:
        logger.warning("Failed to load cart item count: %s", exc)
    return {'cart_item_count': cart_item_count}
