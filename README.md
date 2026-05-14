# Adarsh Furniture

A full-stack e-commerce web app I built with Django to manage furniture inventory, shopping carts, and user orders. 

I built this project to get hands-on experience with Django's ORM, session management (for the shopping cart), and handling user authentication flows.

### What it does:
- Browse furniture products with dynamic filtering (by category, material, stock status).
- Add items to a session-based shopping cart so users don't lose items before logging in.
- Secure checkout flow allowing users to manage multiple shipping addresses and pick a default.
- Admin dashboard to track orders and update their status.

### Built with:
- **Backend:** Python, Django 5.2, SQLite
- **Frontend:** HTML, Vanilla CSS (custom light-grey theme), vanilla JavaScript (for AJAX cart updates without reloading the page).

### Running it locally
1. Clone the repo and navigate into the folder.
2. Install Django:
   `pip install django`
3. Run the migrations to set up the database:
   `python manage.py migrate`
4. I included a quick python script to populate the database with some placeholder products so the site isn't empty:
   `python seed_db.py`
5. Start the dev server:
   `python manage.py runserver`

You can then view the app at http://127.0.0.1:8000/
