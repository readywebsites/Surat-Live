"""
URL configuration for surat project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("businesses.urls")),

    # React frontend static assets from dist
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.BASE_DIR / "dist" / "assets"}),
    re_path(r"^(?P<path>.*\.(?:ico|png|svg|jpg|jpeg|json|txt|webmanifest))$", serve, {"document_root": settings.BASE_DIR / "dist"}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    # Frontend Single Page Application fallback to dist/index.html
    re_path(r"^.*$", TemplateView.as_view(template_name="index.html")),
]