# Single-page architecture: index.html is the only template.
# Cart, wishlist, checkout, orders all run via AJAX JSON endpoints.

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
import stripe
import json

from store.models import Product, Category, Brand, Cart, Order, Customer, Wishlist, Review

stripe.api_key = settings.STRIPE_SECRET_KEY

# ── STATIC PAGES ─────────────────────────────────────────────────────

def contact(request):
    return render(request, 'contact.html')

def faqs(request):
    return render(request, 'faqs.html')

def returns_policy(request):
    return render(request, 'returns_policy.html')

def cookie_policy(request):
    return render(request, 'cookie_policy.html')

def about_us(request):
    return render(request, 'about_us.html')

def sitemap(request):
    return render(request, 'sitemap.html')

def terms(request):
    return render(request, 'terms.html')

def orders(request):
    return render(request, 'orders.html')

def wishlist(request):
    return redirect('homepage')

def cart(request):
    return redirect('homepage')

# ── HELPERS ──────────────────────────────────────────────────────────

def _get_csrf(request):
    from django.middleware.csrf import get_token
    return get_token(request)


def _cart_count(user):
    if user.is_authenticated:
        return Cart.objects.filter(customer=user).count()
    return 0


# ── INDEX (single page) ──────────────────────────────────────────────

class Index(View):
    def get(self, request):
        categories   = Category.objects.all()
        brands       = Brand.objects.all()
        all_products = Product.objects.select_related('category', 'brand').all()

        q             = request.GET.get('q', '').strip()
        category_id   = request.GET.get('category', '')
        gender        = request.GET.get('gender', '')
        max_price     = request.GET.get('max_price', '').strip()
        brand_filter  = request.GET.get('brand', '').strip()
        category_name = request.GET.get('category_name', '').strip()

        if q:
            all_products = all_products.filter(name__icontains=q)
        if category_id:
            all_products = all_products.filter(category_id=category_id)
        if gender:
            all_products = all_products.filter(gender=gender)
        if max_price:
            try:
                all_products = all_products.filter(price__lte=float(max_price))
            except ValueError:
                pass
        if brand_filter:
            all_products = all_products.filter(brand__name__icontains=brand_filter)
        if category_name:
            all_products = all_products.filter(category__name__icontains=category_name)

        cart_product_ids = []
        cart_items       = []
        cart_total       = 0
        if request.user.is_authenticated:
            user_cart        = Cart.objects.filter(customer=request.user).select_related('product')
            cart_product_ids = list(user_cart.values_list('product_id', flat=True))
            cart_items       = [
                {
                    'product':  item.product,
                    'quantity': item.quantity,
                    'subtotal': item.product.price * item.quantity,
                }
                for item in user_cart
            ]
            cart_total = sum(i['subtotal'] for i in cart_items)

        wishlist_product_ids = []
        if request.user.is_authenticated:
            wishlist_product_ids = list(
                Wishlist.objects.filter(customer=request.user).values_list('product_id', flat=True)
            )

        selected_product = None
        product_id_param = request.GET.get('product')
        if product_id_param:
            selected_product = Product.objects.filter(id=product_id_param).first()

        # Fetch approved homepage reviews to display at the bottom of the page
        homepage_reviews = Review.objects.filter(approved=True).select_related('customer').order_by('-created_at')[:5]

        return render(request, 'index.html', {
            'products':            all_products,
            'categories':          categories,
            'brands':              brands,
            'selected_category':   category_id,
            'selected_gender':     gender,
            'q':                   q,
            'max_price':           max_price,
            'brand_filter':        brand_filter,
            'category_name':       category_name,
            'cart_product_ids':    cart_product_ids,
            'cart_items':          cart_items,
            'cart_total':          cart_total,
            'wishlist_product_ids': wishlist_product_ids,
            'selected_product':    selected_product,
            'stripe_public_key':   settings.STRIPE_PUBLIC_KEY,
            'homepage_reviews':    homepage_reviews,
        })


# ── AUTH ─────────────────────────────────────────────────────────────

class Signup(View):
    def get(self, request):
        return render(request, 'signup.html')

    def post(self, request):
        d          = request.POST
        first_name = d.get('firstname', '').strip()
        last_name  = d.get('lastname', '').strip()
        phone      = d.get('phone', '').strip()
        email      = d.get('email', '').strip()
        password   = d.get('password', '')

        if Customer.objects.filter(email=email).exists():
            return render(request, 'signup.html', {
                'error': 'An account with this email already exists.',
                'values': d,
            })
        if not password:
            return render(request, 'signup.html', {
                'error': 'Password is required.',
                'values': d,
            })

        user = Customer.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
        )
        login(request, user)
        return redirect('homepage')


class Login(View):
    def get(self, request):
        return render(request, 'login.html')

    def post(self, request):
        email    = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        user     = authenticate(username=email, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', '')
            return redirect(next_url if next_url else 'homepage')
        return render(request, 'login.html', {'error': 'Invalid email or password.'})


@login_required
def logout_view(request):
    logout(request)
    return redirect('homepage')


# ── CART AJAX ─────────────────────────────────────────────────────────

def ajax_add_to_cart(request):
    """POST JSON { product_id, quantity }  →  { success, cart_count }"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    product_id = data.get('product_id')
    quantity   = int(data.get('quantity', 1))

    if not product_id:
        return JsonResponse({'success': False, 'error': 'Missing product_id'}, status=400)

    product = get_object_or_404(Product, id=product_id)

    if request.user.is_authenticated:
        item, created = Cart.objects.get_or_create(customer=request.user, product=product)
        if not created:
            item.quantity += quantity
        else:
            item.quantity = quantity
        item.save()
        cart_count = Cart.objects.filter(customer=request.user).count()
    else:
        cart = request.session.get('cart', {})
        pid  = str(product_id)
        cart[pid] = cart.get(pid, 0) + quantity
        request.session['cart'] = cart
        cart_count = len(cart)

    return JsonResponse({'success': True, 'cart_count': cart_count})


def ajax_remove_from_cart(request):
    """POST JSON { product_id }  →  { success, cart_count, cart_total }"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    product_id = str(data.get('product_id'))

    if request.user.is_authenticated:
        Cart.objects.filter(customer=request.user, product_id=product_id).delete()
        cart_items = Cart.objects.filter(customer=request.user).select_related('product')
        cart_total = sum(i.product.price * i.quantity for i in cart_items)
        cart_count = cart_items.count()
    else:
        cart = request.session.get('cart', {})
        cart.pop(product_id, None)
        request.session['cart'] = cart
        products   = Product.objects.filter(id__in=cart.keys())
        cart_total = sum(p.price * cart[str(p.id)] for p in products)
        cart_count = len(cart)

    return JsonResponse({'success': True, 'cart_count': cart_count, 'cart_total': str(cart_total)})


def ajax_cart_data(request):
    """GET  →  full cart item list as JSON (used to refresh cart drawer)"""
    if request.user.is_authenticated:
        cart_items = Cart.objects.filter(customer=request.user).select_related('product')
        items = []
        for item in cart_items:
            items.append({
                'product_id': item.product.id,
                'name':       item.product.name,
                'price':      str(item.product.price),
                'quantity':   item.quantity,
                'subtotal':   str(item.product.price * item.quantity),
                'image':      item.product.image.url if item.product.image else '',
            })
        total = sum(item.product.price * item.quantity for item in cart_items)
        return JsonResponse({'items': items, 'total': str(total), 'count': cart_items.count()})
    else:
        cart     = request.session.get('cart', {})
        products = Product.objects.filter(id__in=cart.keys())
        items    = []
        total    = 0
        for p in products:
            qty      = cart[str(p.id)]
            subtotal = p.price * qty
            total   += subtotal
            items.append({
                'product_id': p.id,
                'name':       p.name,
                'price':      str(p.price),
                'quantity':   qty,
                'subtotal':   str(subtotal),
                'image':      p.image.url if p.image else '',
            })
        return JsonResponse({'items': items, 'total': str(total), 'count': len(items)})


# ── WISHLIST AJAX ─────────────────────────────────────────────────────

def ajax_add_to_wishlist(request):
    """POST JSON { product_id }  →  { success, created }"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    product_id = str(data.get('product_id'))
    product    = get_object_or_404(Product, id=product_id)

    if request.user.is_authenticated:
        _, created = Wishlist.objects.get_or_create(customer=request.user, product=product)
    else:
        wishlist  = request.session.get('wishlist', [])
        created   = product_id not in wishlist
        if created:
            wishlist.append(product_id)
            request.session['wishlist'] = wishlist

    return JsonResponse({'success': True, 'created': created})


def ajax_remove_from_wishlist(request):
    """POST JSON { product_id }  →  { success }"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    product_id = str(data.get('product_id'))

    if request.user.is_authenticated:
        Wishlist.objects.filter(customer=request.user, product_id=product_id).delete()
    else:
        wishlist = request.session.get('wishlist', [])
        request.session['wishlist'] = [i for i in wishlist if i != product_id]

    return JsonResponse({'success': True})


def ajax_wishlist_data(request):
    """GET  →  full wishlist item list as JSON (used to populate wishlist panel)"""
    if request.user.is_authenticated:
        wishlist_items = Wishlist.objects.filter(customer=request.user).select_related('product')
        items = []
        for entry in wishlist_items:
            p = entry.product
            items.append({
                'product_id': p.id,
                'name':       p.name,
                'price':      str(p.price),
                'image':      p.image.url if p.image else '',
            })
        return JsonResponse({'items': items, 'count': len(items)})
    else:
        wishlist = request.session.get('wishlist', [])
        products = Product.objects.filter(id__in=wishlist)
        items = []
        for p in products:
            items.append({
                'product_id': p.id,
                'name':       p.name,
                'price':      str(p.price),
                'image':      p.image.url if p.image else '',
            })
        return JsonResponse({'items': items, 'count': len(items)})


def ajax_wishlist_to_cart(request):
    """POST JSON { product_id } or { move_all: true }
       Moves one or all wishlist items to the cart, then removes them from the wishlist.
       Returns { success, cart_count }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    move_all   = data.get('move_all', False)
    product_id = data.get('product_id')

    if request.user.is_authenticated:
        if move_all:
            wishlist_items = Wishlist.objects.filter(customer=request.user).select_related('product')
            for entry in wishlist_items:
                item, created = Cart.objects.get_or_create(customer=request.user, product=entry.product)
                if not created:
                    item.quantity += 1
                    item.save()
                else:
                    item.quantity = 1
                    item.save()
            wishlist_items.delete()
        else:
            if not product_id:
                return JsonResponse({'success': False, 'error': 'Missing product_id'}, status=400)
            product = get_object_or_404(Product, id=product_id)
            item, created = Cart.objects.get_or_create(customer=request.user, product=product)
            if not created:
                item.quantity += 1
                item.save()
            else:
                item.quantity = 1
                item.save()
            Wishlist.objects.filter(customer=request.user, product=product).delete()
        cart_count = Cart.objects.filter(customer=request.user).count()
    else:
        wishlist = request.session.get('wishlist', [])
        cart     = request.session.get('cart', {})
        if move_all:
            for pid in wishlist:
                cart[pid] = cart.get(pid, 0) + 1
            request.session['wishlist'] = []
        else:
            if not product_id:
                return JsonResponse({'success': False, 'error': 'Missing product_id'}, status=400)
            pid = str(product_id)
            cart[pid] = cart.get(pid, 0) + 1
            request.session['wishlist'] = [i for i in wishlist if i != pid]
        request.session['cart'] = cart
        cart_count = len(cart)

    return JsonResponse({'success': True, 'cart_count': cart_count})


# ── ORDERS AJAX ───────────────────────────────────────────────────────

def ajax_orders(request):
    """GET  →  order list as JSON (used by orders panel on index.html)"""
    if not request.user.is_authenticated:
        return JsonResponse({'orders': []})

    orders = Order.objects.filter(customer=request.user).select_related('product').order_by('-created_at')
    data = []
    for o in orders:
        data.append({
            'id':         o.id,
            'product':    o.product.name,
            'quantity':   o.quantity,
            'price':      str(o.price),
            'total':      str(o.price * o.quantity),
            'address':    o.address,
            'paid':       o.paid,
            'created_at': o.created_at.strftime('%d %b %Y'),
        })
    return JsonResponse({'orders': data})


# ── STRIPE CHECKOUT ───────────────────────────────────────────────────

class CreateCheckoutSession(View):
    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            body = {}

        request.session['checkout_info'] = {
            'address': body.get('address', ''),
            'phone':   body.get('phone', ''),
        }

        line_items = []

        if request.user.is_authenticated:
            cart_items = Cart.objects.filter(customer=request.user).select_related('product')
            if not cart_items.exists():
                return JsonResponse({'error': 'Cart is empty'}, status=400)
            for item in cart_items:
                line_items.append({
                    'price_data': {
                        'currency':     'gbp',
                        'product_data': {'name': item.product.name},
                        'unit_amount':  int(round(item.product.price * 100)),
                    },
                    'quantity': item.quantity,
                })
        else:
            cart = request.session.get('cart', {})
            if not cart:
                return JsonResponse({'error': 'Cart is empty'}, status=400)
            products = Product.objects.filter(id__in=cart.keys())
            for p in products:
                line_items.append({
                    'price_data': {
                        'currency':     'gbp',
                        'product_data': {'name': p.name},
                        'unit_amount':  int(round(p.price * 100)),
                    },
                    'quantity': cart[str(p.id)],
                })

        customer_email = request.user.email if request.user.is_authenticated else body.get('email', '')

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            customer_email=customer_email or None,
            success_url=(
                request.build_absolute_uri('/success/')
                + '?session_id={CHECKOUT_SESSION_ID}'
            ),
            cancel_url=request.build_absolute_uri('/'),
            metadata={'user_id': str(request.user.id) if request.user.is_authenticated else ''},
        )

        request.session['stripe_session_id'] = session.id
        return JsonResponse({'url': session.url})

    def get(self, request):
        return redirect('homepage')


class PaymentSuccess(View):
    def get(self, request):
        session_id        = request.GET.get('session_id')
        stored_session_id = request.session.get('stripe_session_id')

        if not session_id or session_id != stored_session_id:
            return redirect('homepage')

        try:
            stripe_session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.StripeError:
            return redirect('homepage')

        if stripe_session.payment_status != 'paid':
            return redirect('homepage')

        info = request.session.get('checkout_info', {})

        if request.user.is_authenticated:
            cart_items = Cart.objects.filter(customer=request.user).select_related('product')
            for item in cart_items:
                Order.objects.create(
                    customer=request.user,
                    product=item.product,
                    quantity=item.quantity,
                    price=item.product.price,
                    address=info.get('address', ''),
                    phone=info.get('phone', ''),
                    paid=True,
                )
            cart_items.delete()

            try:
                html_content = render_to_string(
                    'emails/order_confirmation.html', {'user': request.user}
                )
                msg = EmailMultiAlternatives(
                    subject='Your Order Confirmation – Beauty in Black',
                    body='Thank you for your order at Beauty in Black!',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[request.user.email],
                )
                msg.attach_alternative(html_content, 'text/html')
                msg.send(fail_silently=True)
            except Exception:
                pass
        else:
            request.session.pop('cart', None)

        request.session.pop('checkout_info', None)
        request.session.pop('stripe_session_id', None)

        return render(request, 'index.html', {
            'payment_success':      True,
            'categories':           Category.objects.all(),
            'products':             Product.objects.select_related('category', 'brand').all(),
            'cart_product_ids':     [],
            'cart_items':           [],
            'cart_total':           0,
            'wishlist_product_ids': [],
            'stripe_public_key':    settings.STRIPE_PUBLIC_KEY,
            'homepage_reviews':     Review.objects.filter(approved=True).select_related('customer').order_by('-created_at')[:5],
        })


# ── STRIPE WEBHOOK ────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload    = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        if session.get('payment_status') == 'paid':
            user_id = session.get('metadata', {}).get('user_id')
            if user_id:
                Order.objects.filter(customer_id=user_id, paid=False).update(paid=True)

    return HttpResponse(status=200)


# ── REVIEW ────────────────────────────────────────────────────────────

@login_required
def review_page(request):
    """GET  →  render review.html
       POST →  save the review and redirect to homepage
    """
    if request.method == 'POST':
        product_id      = request.POST.get('product_id', '').strip()
        overall_rating  = request.POST.get('overall_rating', '')
        quality_rating  = request.POST.get('quality_rating', '')
        value_rating    = request.POST.get('value_rating', '')
        delivery_rating = request.POST.get('delivery_rating', '')
        title           = request.POST.get('title', '').strip()
        body            = request.POST.get('body', '').strip()
        recommend       = request.POST.get('recommend', '').strip()

        if not product_id or not overall_rating or not body:
            product = Product.objects.filter(id=product_id).first() if product_id else None
            return render(request, 'review.html', {
                'error':   'Please fill in all required fields.',
                'product': product,
            })

        product = get_object_or_404(Product, id=product_id)

        Review.objects.create(
            customer        = request.user,
            product         = product,
            overall_rating  = overall_rating,
            quality_rating  = quality_rating,
            value_rating    = value_rating,
            delivery_rating = delivery_rating,
            title           = title[:200],
            body            = body[:2000],
            recommend       = recommend,
            approved        = False,
        )

        return redirect('homepage')

    product_id = request.GET.get('product_id', '')
    product    = Product.objects.filter(id=product_id).first() if product_id else None
    return render(request, 'review.html', {'product': product})