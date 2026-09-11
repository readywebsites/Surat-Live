from rest_framework import serializers
from .models import Category, Business


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"


class BusinessSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    class Meta:
        model = Business
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "description",
            "address",
            "phone",
            "email",
            "website",
            "image",
            "is_verified",
            "created_at",
        ]