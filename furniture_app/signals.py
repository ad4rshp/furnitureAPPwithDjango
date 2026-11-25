import logging
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Cart, Order

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def ensure_user_cart(sender, instance, created, **kwargs):
    """Ensure newly registered users have an associated Cart."""
    if created:
        Cart.objects.get_or_create(user=instance)


@receiver(post_save, sender=Order)
def log_order_activity(sender, instance, created, **kwargs):
    """Audit-log order creation and status updates."""
    action = 'created' if created else 'updated'
    logger.info('Order #%s %s (user=%s, status=%s, total=%s)', instance.pk, action, instance.user_id, instance.status, instance.total_price)
