from django.urls import path
from . import views

urlpatterns = [
    path("categories/", views.categories_list, name="categories-list"),
    path("businesses/", views.businesses_list, name="businesses-list"),
]