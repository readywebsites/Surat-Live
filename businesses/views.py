from django.http import JsonResponse
from .models import Category, Business


def categories_list(request):
    categories = Category.objects.all()

    data = []

    for category in categories:
        data.append({
            "id": category.id,
            "name": category.name,
            "description": category.description,
        })

    return JsonResponse(data, safe=False)


def businesses_list(request):
    businesses = Business.objects.all().order_by("-created_at")

    data = []

    for business in businesses:
        data.append({
            "id": business.id,
            "name": business.name,
            "category": business.category.name,
            "description": business.description,
            "address": business.address,
            "phone": business.phone,
            "email": business.email,
            "website": business.website,
            "is_verified": business.is_verified,
        })

    return JsonResponse(data, safe=False)