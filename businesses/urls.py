from django.urls import path
from . import views

urlpatterns = [
    path("categories/", views.categories_list, name="categories-list"),
    path("businesses/", views.businesses_list, name="businesses-list"),
    path("businesses/register/", views.register_business, name="business-register"),
    path("businesses/track-status/", views.track_registration_status, name="business-track-status"),
    path("businesses/<int:pk>/", views.business_detail, name="business-detail"),
    path("businesses/<int:pk>/reviews/", views.submit_review, name="business-submit-review"),
    path("vendors/login/", views.vendor_login, name="vendor-login"),
    path("vendors/profile/", views.vendor_profile, name="vendor-profile"),
    path("vendors/catalog/item/", views.vendor_catalog_item, name="vendor-catalog-item"),
    path("vendors/catalog/delete/", views.vendor_catalog_delete, name="vendor-catalog-delete"),
    path("vendors/upload-image/", views.upload_vendor_image, name="vendor-upload-image"),
    path("vendors/toggle-live/", views.vendor_toggle_live, name="vendor-toggle-live"),
    path("notifications/", views.notifications_list, name="notifications-list"),
    path("notifications/mark-read/", views.mark_notification_read, name="notification-mark-read"),
    path("notifications/log-lead/", views.log_buyer_lead, name="notification-log-lead"),
    path("users/register/", views.user_register, name="user-register"),
    path("users/login/", views.user_login, name="user-login"),
    path("users/profile/", views.user_profile, name="user-profile"),
    path("users/dashboard-data/", views.user_dashboard_data, name="user-dashboard-data"),
    path("users/toggle-saved/", views.user_toggle_saved, name="user-toggle-saved"),
]
