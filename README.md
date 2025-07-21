# furnitureAPPwithDjango

#settings.py
INSTALLED_APPS = [
    # ... other Django apps
    'furniture_app', #our app name
]

#in terminal 
python manage.py makemigrations furniture_app
python manage.py migrate # database migrations to create the necessary tables

README: myfurniture_app
This is a Django-based web application for managing furniture, including products, users, and other related functionalities.

Project Structure
The project follows a standard Django project structure, with a single main application called furniture_app.

FURNITUREAPP/
└── myfurniture_app/
    ├── myfurniture_app/      # Inner project directory with settings, urls, etc.
    │   ├── __init__.py
    │   ├── asgi.py
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    ├── furniture_app/        # Your main 'furniture_app'
    │   ├── migrations/
    │   │   └── __init__.py
    │   ├── __init__.py
    │   ├── admin.py
    │   ├── apps.py
    │   ├── models.py
    │   ├── tests.py          # Currently set aside
    │   ├── views.py
    │   └── urls.py           # App-specific URL patterns
    └── manage.py             # Project's management script
Setup and Installation
Follow these steps to get the application up and running on your local machine:

1. Clone the Repository (or create the project)
If you have a Git repository, clone it:

Bash

git clone <repository_url>
cd FURNITUREAPP/myfurniture_app
If you are starting from scratch, navigate to your desired directory and create the project:

Bash

# In your desired parent directory (e.g., FURNITUREAPP)
django-admin startproject myfurniture_app
cd myfurniture_app
python manage.py startapp furniture_app
2. Configure settings.py
Open myfurniture_app/myfurniture_app/settings.py and ensure the following are configured:

INSTALLED_APPS: Make sure furniture_app is included.

Python

INSTALLED_APPS = [
    # ... other Django apps
    'furniture_app',
]
Template Paths: Ensure your TEMPLATES settings correctly point to your templates.

Media and Static Files: Configure MEDIA_URL, MEDIA_ROOT, STATIC_URL, and STATIC_ROOT as needed for serving user-uploaded content and static assets.

3. Configure urls.py
Open myfurniture_app/myfurniture_app/urls.py and include the URLs from your furniture_app:

Python

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('furniture_app.urls')), # Include your app's URLs
]
4. Database Migrations
Apply database migrations to create the necessary tables:

Bash

python manage.py makemigrations furniture_app
python manage.py migrate
5. Create a Superuser (Optional but Recommended)
To access the Django admin panel, create a superuser:

Bash

python manage.py createsuperuser
Follow the prompts to set up your username, email, and password.

Running the Application
To run the development server:

Bash

python manage.py runserver

Features
Product Display: Products are displayed on the homepage.

User Management: (Implied by the initial setup of a single app for both products and users).

Admin Interface: Django's built-in admin interface is available for managing models.

