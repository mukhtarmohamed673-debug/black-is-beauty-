# AJAX endpoints handle cart / wishlist / checkout dynamically
from django.urls import path
from store import views

urlpatterns = [
    path('', views.Index.as_view(), name='homepage'),
    path('signup/', views.Signup.as_view(), name='signup'),
    path('login/', views.Login.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('contact/', views.contact, name='contact'),
    path('faqs/', views.faqs, name='faqs'),
    path('orders/', views.orders, name='orders'),
    path('returns-policy/', views.returns_policy, name='returns_policy'),
    path('cookie-policy/', views.cookie_policy, name='cookie_policy'),
    path('about/', views.about_us, name='about_us'),
    path('sitemap/', views.sitemap, name='sitemap'),
    path('terms/', views.terms, name='terms'),
    path('wishlist/', views.wishlist, name='wishlist'),
    path('cart/', views.cart, name='cart'),
    path('ajax-add-to-cart/', views.ajax_add_to_cart, name='ajax_add_to_cart'),
    path('ajax-remove-from-cart/', views.ajax_remove_from_cart, name='ajax_remove_from_cart'),
    path('ajax-cart-data/', views.ajax_cart_data, name='ajax_cart_data'),
    path('review/', views.review_page, name='review'),
    path('ajax-wishlist-data/', views.ajax_wishlist_data, name='ajax_wishlist_data'),
    path('ajax-wishlist-to-cart/', views.ajax_wishlist_to_cart, name='ajax_wishlist_to_cart'),
    path('ajax-orders/', views.ajax_orders, name='ajax_orders'),
    path('create-checkout-session/', views.CreateCheckoutSession.as_view(), name='create_checkout_session'),
    path('success/', views.PaymentSuccess.as_view(), name='payment_success'),
    path('stripe-webhook/', views.stripe_webhook, name='stripe_webhook'),
]