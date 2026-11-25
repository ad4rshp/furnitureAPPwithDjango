# Furniture Store (Django)

E-commerce furniture store built with Django and SQLite.

## Features

- Product catalog with search, category, material, availability, and price sorting
- Sale banners with countdown timers
- Session/user shopping cart with quantity updates
- Shipping address book and Cash on Delivery (COD) checkout
- Order tracking, cancellation, and staff order dashboard
- Django Admin product, order, and banner management
- Read-only JSON endpoints (`/api/health/`, `/api/products/`, `/api/products/<id>/`)

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_products
python manage.py createsuperuser
python manage.py runserver
```

## Tests

```bash
python manage.py test
```
