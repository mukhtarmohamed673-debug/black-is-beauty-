# store/views/product_gallery.py
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count

from store.models import Product, Category, Brand


class ProductGalleryView(View):
    template_name = "store/product_gallery.html"
    paginate_by    = 12

    def get(self, request, slug=None):  # slug = category slug or None → all products
        # Base queryset
        products = Product.objects.filter(is_active=True).select_related("category", "brand")

        category = None
        category_slug = slug

        # Category filter
        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)
            products = products.filter(category=category)

        # ── GET parameters ──────────────────────────────────────────────
        # Sorting
        sort = request.GET.get("sort", "relevance")
        if sort == "price-asc":
            products = products.order_by("price")
        elif sort == "price-desc":
            products = products.order_by("-price")
        elif sort == "newest":
            products = products.order_by("-created_at")
        elif sort == "name":
            products = products.order_by("name")
        # default = newest or relevance (you decide)

        # Brand filter (multiple)
        selected_brands = request.GET.getlist("brand")
        if selected_brands:
            products = products.filter(brand__slug__in=selected_brands)

        # Price range filter
        min_price = request.GET.get("min_price")
        max_price = request.GET.get("max_price")
        if min_price:
            try:
                products = products.filter(price__gte=float(min_price))
            except ValueError:
                pass
        if max_price:
            try:
                products = products.filter(price__lte=float(max_price))
            except ValueError:
                pass

        # Pagination
        paginator = Paginator(products, self.paginate_by)
        page = request.GET.get("page", 1)

        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        # ── Sidebar data ────────────────────────────────────────────────
        all_categories = Category.objects.all().annotate(product_count=Count("product"))
        all_brands     = Brand.objects.all().annotate(product_count=Count("product"))

        # Current filters for "active" state in template
        current_filters = {
            "sort":          sort,
            "selected_brands": selected_brands,
            "min_price":     min_price,
            "max_price":     max_price,
            "page_size":     self.paginate_by,   # or read from ?per_page=
        }

        context = {
            "products":         page_obj,
            "page_obj":         page_obj,
            "paginator":        paginator,
            "category":         category,
            "all_categories":   all_categories,
            "all_brands":       all_brands,
            "current_filters":  current_filters,
            # Optional
            "sort_options":     ["relevance", "price-asc", "price-desc", "newest", "name"],
        }

        return render(request, self.template_name, context)