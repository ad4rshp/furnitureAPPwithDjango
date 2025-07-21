from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'furniture_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='furniture_app:login'), name='logout'),
    path('signup/', views.signup_view, name='signup'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('add_to_cart/<int:product_pk>/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.view_cart, name='view_cart'),
    path('remove_from_cart/<int:item_pk>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update_quantity/<int:item_pk>/', views.update_cart_item_quantity, name='update_cart_item_quantity'),
    path('profile/', views.user_profile, name='user_profile'),
    path('checkout/', views.checkout, name='checkout'),
    path('place_order/', views.checkout, name='place_order'),
    path('order/<int:order_pk>/', views.order_detail, name='order_detail'),
    path('admin-dashboard/orders/', views.admin_orders_dashboard, name='admin_view_all_orders'),
    path('order/<int:order_pk>/update_status/', views.update_order_status, name='update_order_status'),
    path('address/edit/<int:pk>/', views.edit_address, name='edit_address'),
    path('profile/add_address/', views.add_address, name='add_address'),
    path('profile/set_default_address/<int:pk>/', views.set_default_address, name='set_default_address'),
    path('profile/delete_address/<int:pk>/', views.delete_address, name='delete_address'),
    path('order/<int:order_pk>/delete/', views.delete_order, name='delete_order'),
]
