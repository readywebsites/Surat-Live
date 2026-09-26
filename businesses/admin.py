from django.contrib import admin
from django.db import connection
from django.utils.html import format_html, mark_safe
from .models import (
    Category,
    Business,
    Product,
    Service,
    Review,
    VendorCredential,
    BusinessRegistration,
    VendorUpdateLog,
    BusinessCatalog,
    Notification,
    UserProfile,
    UserCredential,
    ensure_notification_table,
    ensure_vendorupdatelog_table,
    ensure_userprofile_table,
    ensure_usercredential_table,
)




class ProductInline(admin.TabularInline):
    model = Product
    extra = 0
    can_delete = True
    fields = ("name", "price", "is_available", "description", "image")
    show_change_link = True


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0
    can_delete = True
    fields = ("name", "price", "is_available", "description", "image")
    show_change_link = True


class VendorCredentialInline(admin.StackedInline):
    model = VendorCredential
    extra = 0
    can_delete = True
    fields = ("login_id", "password", "is_active", "notes", "last_login_at")
    readonly_fields = ("last_login_at",)


@admin.register(VendorCredential)
class VendorCredentialAdmin(admin.ModelAdmin):
    list_display = (
        "login_id",
        "business",
        "is_active",
        "get_business_verified",
        "last_login_at",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("login_id", "business__name", "business__phone", "business__email")
    readonly_fields = ("created_at", "updated_at", "last_login_at")
    fieldsets = (
        (
            "Vendor Login Credentials",
            {
                "fields": ("business", "login_id", "password", "is_active"),
                "description": "Provide this Login ID and Password to the vendor after verifying their business.",
            },
        ),
        (
            "Account Notes & Activity",
            {
                "fields": ("notes", "last_login_at", "created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Business Verified?", boolean=True)
    def get_business_verified(self, obj):
        return obj.business.is_verified


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "phone",
        "get_vendor_login_id",
        "is_verified",
        "get_store_status",
        "created_at",
    )
    list_filter = ("is_verified", "is_activated", "category")
    search_fields = ("name", "phone", "email", "address")
    readonly_fields = ("vendor_update_history_display",)

    @admin.display(description="Storefront Status")
    def get_store_status(self, obj):
        if getattr(obj, "is_activated", False):
            return mark_safe('<span style="color:#16a34a; font-weight:700;">🟢 Live</span>')
        return mark_safe('<span style="color:#d97706; font-weight:700; background:#fef3c7; padding:2px 8px; border-radius:4px;">⏸️ Offline</span>')

    fieldsets = (
        (
            "Business Information",
            {
                "fields": (
                    "name",
                    "category",
                    "description",
                    "image",
                    "address",
                    "phone",
                    "email",
                    "website",
                )
            },
        ),
        (
            "Admin Review & Verification",
            {
                "fields": ("is_verified", "is_activated"),
                "description": "Mark 'Is verified' to approve listing. 'Is activated' turns on when the vendor logs in to the platform.",
            },
        ),
        (
            "Vendor Edit History & Audit Logs",
            {
                "fields": ("vendor_update_history_display",),
                "description": "All modifications made by the vendor through their dashboard are permanently logged here with timestamps and before/after details.",
            },
        ),
        (
            "Legacy Vendor Credentials (Optional)",
            {
                "classes": ("collapse",),
                "fields": ("vendor_username", "vendor_password"),
                "description": "Legacy fields. Recommended: Use the 'Vendor Login Credentials' section below or the dedicated menu.",
            },
        ),
    )

    def get_inlines(self, request, obj):
        inlines = []
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='businesses_vendorcredential'"
                )
                if cursor.fetchone():
                    inlines.append(VendorCredentialInline)
        except Exception:
            pass
        inlines.extend([ProductInline, ServiceInline])
        return inlines

    @admin.display(description="Vendor Updates (Before vs After)")
    def vendor_update_history_display(self, obj):
        ensure_vendorupdatelog_table()
        if not obj or not obj.id:
            return "Save the business first to view edit history."
        logs = VendorUpdateLog.objects.filter(business=obj).order_by("-updated_at")
        if not logs.exists():
            return mark_safe("<em style='color:#64748b;'>No dashboard updates have been made by this vendor yet.</em>")

        items = []
        for log in logs[:25]:
            items.append(f"""
            <div style="margin-bottom:14px; padding:12px 16px; background:#f8fafc; border-left:4px solid #4f46e5; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-weight:700; color:#0f172a; margin-bottom:4px; font-size:13px;">
                    📅 {log.updated_at.strftime('%d %b %Y at %I:%M:%S %p')} &nbsp;•&nbsp; <span style="color:#4f46e5;">{log.summary}</span>
                </div>
                <pre style="margin:6px 0 0 0; background:#ffffff; padding:10px 12px; border-radius:4px; border:1px solid #e2e8f0; font-family:Consolas, monospace; font-size:12px; line-height:1.5; white-space:pre-wrap; color:#1e293b;">{log.details}</pre>
            </div>
            """)
        return mark_safe("".join(items))

    @admin.display(description="Vendor Login ID")
    def get_vendor_login_id(self, obj):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='businesses_vendorcredential'"
                )
                if cursor.fetchone():
                    if hasattr(obj, "login_credential") and obj.login_credential:
                        return obj.login_credential.login_id
        except Exception:
            pass
        return getattr(obj, "vendor_username", None) or "—"


@admin.register(VendorUpdateLog)
class VendorUpdateLogAdmin(admin.ModelAdmin):
    list_display = ("business", "updated_at", "summary")
    list_filter = ("business", "updated_at")
    search_fields = ("business__name", "business__phone", "summary", "details")
    readonly_fields = ("business", "updated_at", "summary", "formatted_details")
    fields = ("business", "updated_at", "summary", "formatted_details")

    @admin.display(description="Audit Log Details (Before vs After)")
    def formatted_details(self, obj):
        if not obj.details:
            return "No details recorded."
        return format_html("<pre style='background:#f8fafc; padding:14px; border-radius:8px; border:1px solid #e2e8f0; font-family:Consolas, monospace; white-space:pre-wrap; font-size:13px; line-height:1.5; color:#1e293b;'>{}</pre>", obj.details)


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


@admin.register(BusinessRegistration)
class BusinessRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "owner_name",
        "phone",
        "get_category_display",
        "status",
        "created_business",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("business_name", "owner_name", "phone", "email", "address")
    readonly_fields = ("created_at", "updated_at")
    actions = ["approve_and_create_businesses"]

    fieldsets = (
        (
            "Registration Submission Details",
            {
                "fields": (
                    "business_name",
                    "owner_name",
                    "category",
                    "category_name",
                    "phone",
                    "email",
                    "address",
                    "description",
                    "website",
                ),
            },
        ),
        (
            "Admin Verification & Review",
            {
                "fields": ("status", "admin_notes", "created_business"),
                "description": "Review merchant details. Change status to 'Approved & Verified' after verification, or use the Action dropdown to automatically create the verified Business listing.",
            },
        ),
        (
            "Submission Timestamps",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Category")
    def get_category_display(self, obj):
        return obj.category.name if obj.category else obj.category_name or "—"

    @admin.action(description="✓ Approve & convert selected registrations into Verified Businesses")
    def approve_and_create_businesses(self, request, queryset):
        created_count = 0
        for reg in queryset.filter(status="pending"):
            full_desc = reg.description
            if reg.owner_name:
                full_desc = f"Owner: {reg.owner_name}. {reg.description}".strip()

            biz = Business.objects.create(
                name=reg.business_name,
                category=reg.category,
                phone=reg.phone,
                email=reg.email,
                address=reg.address,
                description=full_desc,
                website=reg.website,
                is_verified=True,
                is_activated=False,
            )
            reg.status = "approved"
            reg.created_business = biz
            reg.save()
            created_count += 1

        self.message_user(
            request,
            f"Successfully approved {created_count} registration(s) and created verified business record(s). You can now assign them Vendor Login Credentials.",
        )


@admin.register(BusinessCatalog)
class BusinessCatalogAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "get_store_status",
        "get_products_count",
        "get_services_count",
        "phone",
        "is_verified",
    )
    list_filter = ("is_activated", "is_verified", "category")
    search_fields = ("name", "phone", "email", "address")
    inlines = [ProductInline, ServiceInline]
    readonly_fields = ("catalog_business_overview", "vendor_update_history_display")
    fieldsets = (
        (
            "Merchant Information & Storefront",
            {
                "fields": ("catalog_business_overview",),
                "description": "Products and services offered by this merchant are listed in the tables below. You can view, add, modify, or remove catalog items directly.",
            },
        ),
        (
            "Vendor Catalog Edit History & Audit Logs",
            {
                "fields": ("vendor_update_history_display",),
                "description": "Every product or service added, updated, or deleted by the vendor from their dashboard is permanently recorded here with date and time.",
            },
        ),
    )

    @admin.display(description="Storefront Live?")
    def get_store_status(self, obj):
        if getattr(obj, "is_activated", False):
            return mark_safe('<span style="color:#16a34a; font-weight:700;">🟢 Live on Platform</span>')
        return mark_safe('<span style="color:#d97706; font-weight:700; background:#fef3c7; padding:2px 8px; border-radius:4px;">⏸️ Offline (Paused)</span>')

    @admin.display(description="Total Products")
    def get_products_count(self, obj):
        count = obj.products.count()
        return f"{count} product{'s' if count != 1 else ''}"

    @admin.display(description="Total Services")
    def get_services_count(self, obj):
        count = obj.services.count()
        return f"{count} service{'s' if count != 1 else ''}"

    @admin.display(description="Business Details")
    def catalog_business_overview(self, obj):
        if not obj:
            return ""
        return format_html(
            """
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px 20px; line-height:1.7;">
                <h3 style="margin:0 0 8px 0; color:#0f172a; font-size:17px;">🏢 <strong>{}</strong></h3>
                <div><strong>Industry Category:</strong> {}</div>
                <div><strong>Primary Phone:</strong> {}</div>
                <div><strong>Business Email:</strong> {}</div>
                <div><strong>Full Address:</strong> {}</div>
                <div style="margin-top:6px;"><strong>Status:</strong> <span style="color:#16a34a; font-weight:700;">{}</span> &nbsp;•&nbsp; <span style="color:#0284c7; font-weight:700;">{}</span></div>
            </div>
            """,
            obj.name,
            obj.category.name if obj.category else "Uncategorized",
            obj.phone or "—",
            obj.email or "—",
            obj.address or "—",
            "Verified Vendor" if obj.is_verified else "Pending Review",
            "🟢 Storefront Active & Live" if getattr(obj, "is_activated", False) else "⏸️ Storefront Paused / Offline by Vendor",
        )

    @admin.display(description="Vendor Updates (Before vs After)")
    def vendor_update_history_display(self, obj):
        ensure_vendorupdatelog_table()
        if not obj or not obj.id:
            return "Save the business first to view edit history."
        logs = VendorUpdateLog.objects.filter(business=obj).order_by("-updated_at")
        if not logs.exists():
            return mark_safe("<em style='color:#64748b;'>No dashboard updates have been made by this vendor yet.</em>")

        items = []
        for log in logs[:30]:
            items.append(f"""
            <div style="margin-bottom:14px; padding:12px 16px; background:#f8fafc; border-left:4px solid #4f46e5; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                <div style="font-weight:700; color:#0f172a; margin-bottom:4px; font-size:13px;">
                    📅 {log.updated_at.strftime('%d %b %Y at %I:%M:%S %p')} &nbsp;•&nbsp; <span style="color:#4f46e5;">{log.summary}</span>
                </div>
                <pre style="margin:6px 0 0 0; background:#ffffff; padding:10px 12px; border-radius:4px; border:1px solid #e2e8f0; font-family:Consolas, monospace; font-size:12px; line-height:1.5; white-space:pre-wrap; color:#1e293b;">{log.details}</pre>
            </div>
            """)
        return mark_safe("".join(items))


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "target_type", "business", "is_read", "created_at")
    list_filter = ("category", "target_type", "is_read", "created_at")
    search_fields = ("title", "message", "business__name")
    readonly_fields = ("created_at",)
    fieldsets = (
        (
            "Notification Details",
            {
                "fields": ("title", "message", "category", "target_type", "business", "link", "is_read", "created_at"),
                "description": "Dynamic notifications delivered to vendors, buyers, and platform visitors.",
            },
        ),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("get_username", "get_full_name", "get_email", "phone", "city", "get_date_joined")
    search_fields = ("user__username", "user__first_name", "user__email", "phone", "city")
    list_filter = ("city",)

    @admin.display(description="Username")
    def get_username(self, obj):
        return obj.user.username

    @admin.display(description="Full Name")
    def get_full_name(self, obj):
        return obj.user.first_name or "—"

    @admin.display(description="Email")
    def get_email(self, obj):
        return obj.user.email or "—"

    @admin.display(description="Member Since")
    def get_date_joined(self, obj):
        return obj.user.date_joined.strftime("%d %b %Y") if obj.user.date_joined else "—"


@admin.register(UserCredential)
class UserCredentialAdmin(admin.ModelAdmin):
    list_display = (
        "login_id",
        "full_name",
        "email",
        "phone",
        "password",
        "city",
        "is_active",
        "last_login_at",
        "created_at",
    )
    list_filter = ("is_active", "city", "created_at")
    search_fields = ("login_id", "full_name", "email", "phone", "city")
    readonly_fields = ("created_at", "updated_at", "last_login_at")
    fieldsets = (
        (
            "Customer Account & Login Credentials",
            {
                "fields": ("user", "login_id", "full_name", "email", "phone", "password", "city", "is_active"),
                "description": "Every registered user login ID, password, phone, and Surat area is saved and managed here.",
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("last_login_at", "created_at", "updated_at"),
            },
        ),
    )

