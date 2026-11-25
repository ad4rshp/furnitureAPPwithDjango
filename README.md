# My Furniture Store (Django)

A full-stack e-commerce furniture web application built with Django, featuring a product catalog, category/material/search filtering, sale countdown banners, shopping cart, address book, checkout, order tracking, JSON API endpoints, and a customized Django Admin panel.

## Features

- **Product Catalog & Filtering:** Browse furniture by category, material, price, stock availability, and search query.
- **Sale Banners:** Active promotional carousel with live countdown timers.
- **Cart & Checkout:** Authenticated AJAX cart updates, quantity validation, atomic order creation, and stock decrement.
- **User Profile & Addresses:** Profile management, multiple shipping addresses with a single default address, and order history.
- **Admin & Staff Tools:**
  - `/admin/` with product image thumbnails, live image previews, inline order items, and inventory editing.
  - `/admin-dashboard/orders/` for staff order status management.
- **JSON API:**
  - `GET /api/health/` — Service health and available product count
  - `GET /api/products/` — Filterable product catalog (`category`, `material`, `on_sale`, `q`)
  - `GET /api/products/<id>/` — Single product details

## Quick Start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_products
python manage.py createsuperuser
python manage.py runserver
```

## Running Tests

```bash
python manage.py test
```
