from django.contrib import admin
from .models import Category, Business, Product, Service, Review


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "phone", "is_verified", "created_at")
    list_filter = ("category", "is_verified")
    search_fields = ("name", "address", "phone", "email")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "price", "is_available", "created_at")
    list_filter = ("is_available",)
    search_fields = ("name", "business__name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "price", "is_available", "created_at")
    list_filter = ("is_available",)
    search_fields = ("name", "business__name")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "business",
        "customer_name",
        "rating",
        "is_approved",
        "created_at",
    )
    list_filter = ("rating", "is_approved")
    search_fields = ("customer_name", "business__name")