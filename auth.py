from django.http import HttpResponseRedirect
from django.urls import reverse

def auth_middleware(get_response):
    def middleware(request):
        if not request.user.is_authenticated:
            path = request.path
            protected = [reverse('cart'), reverse('checkout'), reverse('orders'), reverse('payment_success')]
            if path in protected:
                return HttpResponseRedirect(f"{reverse('login')}?next={path}")
        response = get_response(request)
        return response
    return middleware