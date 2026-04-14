# store/views/product_detail.py
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.core.paginator import Paginator
from django.db.models import Avg, Count
from django.conf import settings

from store.models import Product, Category, Review  # assuming you have a Review model


class ProductDetailView(View):
    template_name = "store/product_detail.html"

    def get(self, request, slug):
        product = get_object_or_404(
            Product.objects.select_related("category", "brand")
                           .prefetch_related("images", "reviews"),
            slug=slug,
            is_active=True
        )

        # Related products – same category, exclude current product, order by newest
        related_products = Product.objects.filter(
            category=product.category,
            is_active=True
        ).exclude(
            id=product.id
        ).order_by("-created_at")[:8]

        # Reviews – assuming you have a Review model with rating, body, author, etc.
        reviews = product.reviews.select_related("author").order_by("-created_at")

        # Aggregated rating stats
        rating_stats = product.reviews.aggregate(
            avg_rating=Avg("rating"),
            review_count=Count("id")
        )

        # For stars in template (can also be calculated in template)
        average_rating = rating_stats["avg_rating"] or 0
        review_count    = rating_stats["review_count"] or 0

        context = {
            "product":           product,
            "related_products":  related_products,
            "reviews":           reviews[:6],           # limit visible reviews
            "average_rating":    round(average_rating, 1),
            "review_count":      review_count,
            # Optional – pass stripe key if quick-buy / add-to-cart needs it
            "stripe_public_key": getattr(settings, "STRIPE_PUBLIC_KEY", ""),
        }

        return render(request, self.template_name, context)