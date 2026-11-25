import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Address, Cart, CartItem, Order, OrderItem, Product, SaleBanner


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class FurnitureAppTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)
    def setUp(self):
        self.user = User.objects.create_user(
            username='customer1',
            email='customer1@example.com',
            password='StrongPassword123!',
            first_name='Alice',
            last_name='Smith',
        )
        self.other_user = User.objects.create_user(
            username='customer2',
            email='customer2@example.com',
            password='StrongPassword123!',
        )
        self.staff_user = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='StrongPassword123!',
            is_staff=True,
            is_superuser=True,
        )

        # Minimal valid 1x1 GIF for ImageField tests
        gif_bytes = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00'
            b'\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        )
        self.product = Product.objects.create(
            name='Oak Dining Table',
            description='Solid oak 6-seater dining table.',
            price=Decimal('10000.00'),
            category='DINING_ROOM',
            material='WOOD',
            stock_quantity=5,
            is_available=True,
            on_sale=True,
            discount_percentage=Decimal('15.00'),
            image=SimpleUploadedFile('table.gif', gif_bytes, content_type='image/gif'),
        )
        self.unavailable_product = Product.objects.create(
            name='Vintage Armchair',
            description='Limited edition.',
            price=Decimal('5000.00'),
            category='LIVING_ROOM',
            material='FABRIC',
            stock_quantity=0,
            is_available=False,
        )
        self.banner = SaleBanner.objects.create(
            title='Flash Sale',
            featured_product=self.product,
            sale_end_date=timezone.now() + timedelta(days=5),
            is_active=True,
        )

    def test_product_discounted_price_precision(self):
        self.assertEqual(self.product.get_discounted_price(), Decimal('8500.00'))

    def test_address_single_default_enforced(self):
        addr1 = Address.objects.create(
            user=self.user,
            first_name='Alice',
            last_name='Smith',
            street_address='123 Oak St',
            city='Mumbai',
            state='MH',
            zip_code='400001',
            country='India',
            is_default=True,
        )
        addr2 = Address.objects.create(
            user=self.user,
            first_name='Alice',
            last_name='Smith',
            street_address='456 Pine St',
            city='Pune',
            state='MH',
            zip_code='411001',
            country='India',
            is_default=True,
        )
        addr1.refresh_from_db()
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    def test_index_search_and_filters(self):
        resp = self.client.get(reverse('furniture_app:index'), {'q': 'Oak'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Oak Dining Table')
        self.assertNotContains(resp, 'Vintage Armchair')

    def test_signup_saves_custom_fields(self):
        resp = self.client.post(reverse('furniture_app:signup'), {
            'username': 'newbuyer',
            'email': 'newbuyer@example.com',
            'first_name': 'Bob',
            'last_name': 'Jones',
            'password1': 'ComplexPass987!',
            'password2': 'ComplexPass987!',
        })
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username='newbuyer')
        self.assertEqual(user.first_name, 'Bob')
        self.assertEqual(user.email, 'newbuyer@example.com')

    def test_add_to_cart_auth_and_validation(self):
        url = reverse('furniture_app:add_to_cart', args=[self.product.pk])
        # Unauthenticated AJAX -> 401 JSON
        resp = self.client.post(url, {'quantity': 1}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()['success'])

        self.client.force_login(self.user)
        # Invalid quantity -> 400
        resp = self.client.post(url, {'quantity': -2})
        self.assertEqual(resp.status_code, 400)

        # Unavailable product -> 400
        unavail_url = reverse('furniture_app:add_to_cart', args=[self.unavailable_product.pk])
        resp = self.client.post(unavail_url, {'quantity': 1})
        self.assertEqual(resp.status_code, 400)

        # Valid add
        resp = self.client.post(url, {'quantity': 2})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['cart_item_count'], 2)

    def test_remove_from_cart_idor_blocked(self):
        cart_a = Cart.objects.create(user=self.user)
        item_a = CartItem.objects.create(
            cart=cart_a,
            product=self.product,
            quantity=1,
            price=self.product.get_discounted_price(),
        )
        self.client.force_login(self.other_user)
        resp = self.client.post(reverse('furniture_app:remove_from_cart', args=[item_a.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(CartItem.objects.filter(pk=item_a.pk).exists())

    def test_checkout_creates_order_and_decrements_stock(self):
        self.client.force_login(self.user)
        addr = Address.objects.create(
            user=self.user,
            first_name='Alice',
            last_name='Smith',
            street_address='123 Oak St',
            city='Mumbai',
            state='MH',
            zip_code='400001',
            country='India',
            is_default=True,
        )
        self.client.post(reverse('furniture_app:add_to_cart', args=[self.product.pk]), {'quantity': 2})
        resp = self.client.post(reverse('furniture_app:checkout'), {'shipping_address': addr.pk})
        self.assertEqual(resp.status_code, 302)

        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_price, Decimal('17000.00'))
        self.assertEqual(order.items.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_user_profile_invalid_form_does_not_crash(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('furniture_app:user_profile'), {
            'update_profile_submit': 'true',
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'not-an-email',
        })
        self.assertEqual(resp.status_code, 200)

    def test_order_status_authorization(self):
        addr = Address.objects.create(
            user=self.user,
            first_name='Alice',
            last_name='Smith',
            street_address='123 Oak St',
            city='Mumbai',
            state='MH',
            zip_code='400001',
            country='India',
        )
        order = Order.objects.create(
            user=self.user,
            total_price=Decimal('8500.00'),
            shipping_address=addr,
            payment_method='COD',
            status='PENDING',
        )
        url = reverse('furniture_app:update_order_status', args=[order.pk])

        # Non-staff owner cannot mark DELIVERED
        self.client.force_login(self.user)
        resp = self.client.post(url, {'status': 'DELIVERED'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 403)

        # Non-staff other user cannot cancel
        self.client.force_login(self.other_user)
        resp = self.client.post(url, {'status': 'CANCELLED'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 403)

        # Staff can mark DELIVERED
        self.client.force_login(self.staff_user)
        resp = self.client.post(url, {'status': 'DELIVERED'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'DELIVERED')

    def test_admin_pages_render_for_staff(self):
        self.client.force_login(self.staff_user)
        resp_list = self.client.get('/admin/furniture_app/product/')
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, 'Oak Dining Table')

        resp_change = self.client.get(f'/admin/furniture_app/product/{self.product.pk}/change/')
        self.assertEqual(resp_change.status_code, 200)

        resp_orders = self.client.get(reverse('furniture_app:admin_view_all_orders'))
        self.assertEqual(resp_orders.status_code, 200)

    def test_api_endpoints(self):
        health = self.client.get(reverse('furniture_app:api_health'))
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()['status'], 'ok')

        plist = self.client.get(reverse('furniture_app:api_product_list'), {'category': 'DINING_ROOM'})
        self.assertEqual(plist.status_code, 200)
        data = plist.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['products'][0]['name'], 'Oak Dining Table')

        pdetail = self.client.get(reverse('furniture_app:api_product_detail', args=[self.product.pk]))
        self.assertEqual(pdetail.status_code, 200)
        self.assertEqual(pdetail.json()['discounted_price'], 8500.0)

        pmissing = self.client.get(reverse('furniture_app:api_product_detail', args=[99999]))
        self.assertEqual(pmissing.status_code, 404)
