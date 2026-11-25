from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from furniture_app.models import Product, SaleBanner


SEED_PRODUCTS = [
    {
        'name': '2-Seat Modern Sofa',
        'description': 'Compact upholstered 2-seater sofa with plush cushions and solid wood legs, ideal for modern living rooms.',
        'price': Decimal('6000.00'),
        'image': 'product_images/living_room_sofa.jpg',
        'category': 'LIVING_ROOM',
        'material': 'FABRIC',
        'stock_quantity': 14,
        'is_available': True,
        'requires_assembly': False,
        'on_sale': True,
        'discount_percentage': Decimal('15.00'),
    },
    {
        'name': 'Single Bed in Wenge Finish',
        'description': 'Minimalist single bed frame crafted in engineered wood with a rich wenge finish and sturdy slatted support.',
        'price': Decimal('10000.00'),
        'image': 'product_images/singlebed.jpg',
        'category': 'BEDROOM',
        'material': 'WOOD',
        'stock_quantity': 9,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
    {
        'name': 'King Size Bed',
        'description': 'Spacious king size platform bed with padded headboard and reinforced frame for lasting comfort.',
        'price': Decimal('20000.00'),
        'image': 'product_images/double_bed.jpg',
        'category': 'BEDROOM',
        'material': 'WOOD',
        'stock_quantity': 6,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': True,
        'discount_percentage': Decimal('10.00'),
    },
    {
        'name': 'Oak 6-Seater Dining Table',
        'description': 'Hand-finished solid oak dining table comfortably seating six, built for everyday family meals and gatherings.',
        'price': Decimal('18500.00'),
        'image': 'product_images/dining_table.jpg',
        'category': 'DINING_ROOM',
        'material': 'WOOD',
        'stock_quantity': 5,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': True,
        'discount_percentage': Decimal('12.00'),
    },
    {
        'name': 'Ergonomic Mesh Office Chair',
        'description': 'Breathable high-back mesh task chair with adjustable lumbar support, armrests, and smooth-rolling casters.',
        'price': Decimal('7500.00'),
        'image': 'product_images/office_chair.jpg',
        'category': 'OFFICE',
        'material': 'FABRIC',
        'stock_quantity': 20,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
    {
        'name': 'Minimalist Writing Desk',
        'description': 'Clean-lined study and home office desk with a wide solid wood top and powder-coated steel frame.',
        'price': Decimal('9200.00'),
        'image': 'product_images/office_desk.jpg',
        'category': 'OFFICE',
        'material': 'METAL',
        'stock_quantity': 11,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
    {
        'name': 'Accent Lounge Armchair',
        'description': 'Mid-century inspired lounge armchair with contoured backrest and soft woven upholstery.',
        'price': Decimal('8400.00'),
        'image': 'product_images/armchair.jpg',
        'category': 'LIVING_ROOM',
        'material': 'FABRIC',
        'stock_quantity': 8,
        'is_available': True,
        'requires_assembly': False,
        'on_sale': True,
        'discount_percentage': Decimal('20.00'),
    },
    {
        'name': '5-Tier Timber Bookshelf',
        'description': 'Open-frame 5-tier shelving unit for books, plants, and decor in living rooms or home offices.',
        'price': Decimal('6800.00'),
        'image': 'product_images/bookshelf.jpg',
        'category': 'LIVING_ROOM',
        'material': 'WOOD',
        'stock_quantity': 12,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
    {
        'name': 'Walnut Coffee Table',
        'description': 'Low-profile walnut veneer coffee table with beveled edges and lower storage shelf.',
        'price': Decimal('5400.00'),
        'image': 'product_images/coffee_table.jpg',
        'category': 'LIVING_ROOM',
        'material': 'WOOD',
        'stock_quantity': 15,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
    {
        'name': 'All-Weather Patio Lounge Set',
        'description': 'Weather-resistant outdoor lounge set with UV-protected cushions, perfect for balconies and gardens.',
        'price': Decimal('24000.00'),
        'image': 'product_images/outdoor_patio.jpg',
        'category': 'OUTDOOR',
        'material': 'FABRIC',
        'stock_quantity': 4,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
    {
        'name': 'Butcher-Block Kitchen Island',
        'description': 'Freestanding kitchen prep island with solid wood countertop, deep drawers, and open lower storage.',
        'price': Decimal('16500.00'),
        'image': 'product_images/kitchen_island.jpg',
        'category': 'KITCHEN',
        'material': 'WOOD',
        'stock_quantity': 7,
        'is_available': True,
        'requires_assembly': True,
        'on_sale': False,
        'discount_percentage': Decimal('0.00'),
    },
]


class Command(BaseCommand):
    help = 'Seed the database with real furniture products and an active sale banner.'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        # Update legacy product names if present
        legacy_map = {
            '2-seat sofa': '2-Seat Modern Sofa',
        }
        for old_name, new_name in legacy_map.items():
            Product.objects.filter(name=old_name).update(name=new_name)

        for data in SEED_PRODUCTS:
            product, created = Product.objects.update_or_create(
                name=data['name'],
                defaults=data,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        on_sale_products = list(Product.objects.filter(on_sale=True).order_by('id'))
        SaleBanner.objects.filter(sale_end_date__lt=timezone.now()).update(is_active=False)

        banner_specs = [
            ('Living Room Sofa Event', 0, 21),
            ('Dining & Bedroom Savings', 1, 14),
            ('Accent Chair Flash Deal', 2, 7),
        ]
        for title, idx, days in banner_specs:
            if idx < len(on_sale_products):
                prod = on_sale_products[idx]
                SaleBanner.objects.update_or_create(
                    title=title,
                    defaults={
                        'featured_product': prod,
                        'custom_message': f'Save {int(prod.discount_percentage)}% on {prod.name}',
                        'sale_end_date': timezone.now() + timedelta(days=days),
                        'is_active': True,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Seed complete: {created_count} created, {updated_count} updated. Total products: {Product.objects.count()}'
            )
        )
