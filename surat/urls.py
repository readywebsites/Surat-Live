"""
URL configuration for surat project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView
from django.views.static import serve
from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.conf import settings
from django.http import Http404


def serve_static(request, path, **kwargs):
    """
    Directly serves static files (including Django admin CSS, JS, icons)
    using staticfiles finders dynamically without requiring collectstatic.
    Falls back to settings.STATIC_ROOT if needed.
    """
    try:
        return staticfiles_serve(request, path, insecure=True)
    except Http404:
        return serve(request, path, document_root=settings.STATIC_ROOT, **kwargs)


urlpatterns = [
    # Auto-redirect /admin without trailing slash to /admin/
    path("admin", RedirectView.as_view(url="/admin/", permanent=True)),
    path("admin/", admin.site.urls),
    path("api/", include("businesses.urls")),

    # Serve static files dynamically across all apps (admin, etc.) without requiring collectstatic
    re_path(r"^static/(?P<path>.*)$", serve_static),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),

    # React frontend static assets from dist
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": getattr(settings, 'FRONTEND_DIST', settings.BASE_DIR / "dist") / "assets"}),
    re_path(r"^(?P<path>.*\.(?:ico|png|svg|jpg|jpeg|json|txt|webmanifest))$", serve, {"document_root": getattr(settings, 'FRONTEND_DIST', settings.BASE_DIR / "dist")}),

    # Frontend Single Page Application fallback to dist/index.html
    re_path(r"^.*$", TemplateView.as_view(template_name="index.html")),
]