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
    VerificationOTP,
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
    list_display = ("name", "slug", "show_in_navbar", "order", "is_active")
    list_editable = ("show_in_navbar", "order", "is_active")
    list_filter = ("show_in_navbar", "is_active")
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
                    "google_maps_link",
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


class CategorySourceFilter(admin.SimpleListFilter):
    title = "Category Type"
    parameter_name = "category_type"

    def lookups(self, request, model_admin):
        return (
            ("other", "🆕 'Other' Custom Category Requests"),
            ("catalog", "Standard Catalog Categories"),
        )

    def queryset(self, request, queryset):
        if self.value() == "other":
            return queryset.exclude(other_category="").exclude(other_category__isnull=True)
        if self.value() == "catalog":
            return queryset.filter(models.Q(other_category="") | models.Q(other_category__isnull=True))
        return queryset


@admin.register(BusinessRegistration)
class BusinessRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "owner_name",
        "phone",
        "get_phone_verification",
        "get_email_verification",
        "get_category_display",
        "is_other_category_request",
        "status",
        "created_business",
        "created_at",
    )
    list_filter = ("is_phone_verified", "is_email_verified", CategorySourceFilter, "status", "created_at")
    search_fields = ("business_name", "owner_name", "phone", "email", "address", "other_category")
    readonly_fields = ("category_action_helper", "created_at", "updated_at")
    actions = ["approve_and_create_businesses", "create_categories_from_other_requests"]

    fieldsets = (
        (
            "Registration Submission Details",
            {
                "fields": (
                    "business_name",
                    "owner_name",
                    "category",
                    "other_category",
                    "category_name",
                    "category_action_helper",
                    "phone",
                    "is_phone_verified",
                    "email",
                    "is_email_verified",
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

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:reg_id>/add-category/",
                self.admin_site.admin_view(self.add_category_view),
                name="businesses_businessregistration_add_cat",
            ),
            path(
                "<int:reg_id>/link-category/",
                self.admin_site.admin_view(self.link_category_view),
                name="businesses_businessregistration_link_cat",
            ),
        ]
        return custom_urls + urls

    def add_category_view(self, request, reg_id):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        from django.utils.text import slugify

        reg = get_object_or_404(BusinessRegistration, pk=reg_id)
        cat_name = (reg.other_category or "").strip()
        if not cat_name:
            messages.warning(request, "No custom 'Other' category was specified on this registration.")
            return redirect("../change/")

        cat = Category.objects.filter(name__iexact=cat_name).first()
        created = False
        if not cat:
            cat = Category.objects.create(
                name=cat_name,
                slug=slugify(cat_name),
                is_active=True,
                order=10,
            )
            created = True

        reg.category = cat
        reg.category_name = cat.name
        reg.save(update_fields=["category", "category_name"])

        if created:
            messages.success(request, f"Successfully created new Category '{cat.name}' and linked it to '{reg.business_name}'!")
        else:
            messages.info(request, f"Linked existing Category '{cat.name}' to '{reg.business_name}'.")

        return redirect("../change/")

    def link_category_view(self, request, reg_id):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages

        reg = get_object_or_404(BusinessRegistration, pk=reg_id)
        cat_id = request.GET.get("cat_id")
        if cat_id:
            cat = Category.objects.filter(pk=cat_id).first()
            if cat:
                reg.category = cat
                reg.category_name = cat.name
                reg.save(update_fields=["category", "category_name"])
                messages.success(request, f"Linked Category '{cat.name}' to '{reg.business_name}'!")
        return redirect("../change/")

    @admin.display(description="Category")
    def get_category_display(self, obj):
        if obj.other_category:
            if obj.category:
                return mark_safe(
                    f'<span style="color:#0f172a; font-weight:600;">{obj.category.name}</span> '
                    f'<br><small style="color:#b45309; background:#fef3c7; padding:1px 6px; border-radius:3px; font-weight:700;">(Requested: {obj.other_category})</small>'
                )
            return mark_safe(
                f'<span style="background:#fef3c7; color:#b45309; padding:2px 8px; border-radius:4px; font-weight:700; border:1px solid #fde68a;">'
                f'🆕 Other: {obj.other_category}'
                f'</span>'
            )
        return obj.category.name if obj.category else obj.category_name or "—"

    @admin.display(description="Custom Request?", boolean=True)
    def is_other_category_request(self, obj):
        return bool(obj.other_category)

    @admin.display(description="Phone Verified?")
    def get_phone_verification(self, obj):
        if getattr(obj, "is_phone_verified", False):
            return mark_safe('<span style="color:#16a34a; font-weight:700;">🟢 Phone Verified</span>')
        return mark_safe('<span style="color:#dc2626; font-weight:600;">❌ Unverified</span>')

    @admin.display(description="Email Verified?")
    def get_email_verification(self, obj):
        if getattr(obj, "is_email_verified", False):
            return mark_safe('<span style="color:#16a34a; font-weight:700;">🟢 Email Verified</span>')
        return mark_safe('<span style="color:#dc2626; font-weight:600;">❌ Unverified</span>')

    @admin.display(description="Category Review & Quick Actions")
    def category_action_helper(self, obj):
        if not obj or not obj.id:
            return "Save the registration first to review category actions."

        custom = (obj.other_category or "").strip()
        if not custom:
            return mark_safe(
                f'<div style="color:#475569; font-size:13px;">'
                f'Standard category selected: <strong>{obj.category.name if obj.category else "None"}</strong>. No custom category requested.'
                f'</div>'
            )

        existing = Category.objects.filter(name__iexact=custom).first()
        if existing:
            if obj.category_id == existing.id:
                return mark_safe(
                    f'<div style="padding:10px 14px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; color:#166534; font-size:13px; line-height:1.5;">'
                    f'✅ <strong>Linked to Category:</strong> "{existing.name}" is an active category and linked to this registration.'
                    f'</div>'
                )
            else:
                return mark_safe(
                    f'<div style="padding:10px 14px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; color:#1e40af; font-size:13px; line-height:1.5;">'
                    f'ℹ️ Category <strong>"{existing.name}"</strong> already exists in the system.<br>'
                    f'<a href="link-category/?cat_id={existing.id}" class="button" style="margin-top:6px; display:inline-block; background:#2563eb; color:#ffffff; font-weight:600; padding:4px 12px; border-radius:4px; text-decoration:none;">🔗 Link to "{existing.name}" Now</a>'
                    f'</div>'
                )

        return mark_safe(
            f'<div style="padding:12px 16px; background:#fffbeb; border:1px solid #fcd34d; border-radius:6px; color:#92400e; font-size:13px; line-height:1.6;">'
            f'⚠️ <strong>New Category Requested:</strong> Merchant entered custom category <strong style="color:#78350f; font-size:14px;">"{custom}"</strong>.<br>'
            f'This category does not yet exist in platform categories.<br>'
            f'<div style="margin-top:8px;">'
            f'<a href="add-category/" class="button" style="background:#16a34a; color:#ffffff; font-weight:700; padding:6px 14px; border-radius:4px; text-decoration:none; display:inline-block;">➕ Add "{custom}" to Platform Categories &amp; Link</a>'
            f'</div>'
            f'</div>'
        )

    @admin.action(description="➕ Create new Categories from selected 'Other' requests & link them")
    def create_categories_from_other_requests(self, request, queryset):
        from django.utils.text import slugify
        created_count = 0
        linked_count = 0
        for reg in queryset:
            cat_name = (reg.other_category or "").strip()
            if not cat_name:
                continue

            cat = Category.objects.filter(name__iexact=cat_name).first()
            if not cat:
                cat = Category.objects.create(
                    name=cat_name,
                    slug=slugify(cat_name),
                    is_active=True,
                    order=10,
                )
                created_count += 1
            reg.category = cat
            reg.category_name = cat.name
            reg.save(update_fields=["category", "category_name"])
            linked_count += 1

        self.message_user(
            request,
            f"Created {created_count} new category(ies) and linked {linked_count} registration(s).",
        )

    @admin.action(description="✓ Approve & convert selected registrations into Verified Businesses")
    def approve_and_create_businesses(self, request, queryset):
        from django.utils.text import slugify
        created_count = 0
        for reg in queryset.filter(status="pending"):
            full_desc = reg.description
            if reg.owner_name:
                full_desc = f"Owner: {reg.owner_name}. {reg.description}".strip()

            biz_cat = reg.category
            if not biz_cat and reg.other_category:
                cat_name = reg.other_category.strip()
                biz_cat = Category.objects.filter(name__iexact=cat_name).first()
                if not biz_cat:
                    biz_cat = Category.objects.create(
                        name=cat_name,
                        slug=slugify(cat_name),
                        is_active=True,
                        order=10,
                    )
                reg.category = biz_cat
                reg.category_name = biz_cat.name
                reg.save(update_fields=["category", "category_name"])

            if not biz_cat:
                biz_cat = Category.objects.first()

            biz = Business.objects.create(
                name=reg.business_name,
                category=biz_cat,
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


@admin.register(VerificationOTP)
class VerificationOTPAdmin(admin.ModelAdmin):
    list_display = (
        "target",
        "target_type",
        "otp_code",
        "get_verification_status",
        "attempts",
        "created_at",
        "expires_at",
        "verified_at",
    )
    list_filter = ("target_type", "is_verified", "created_at")
    search_fields = ("target", "otp_code", "ip_address")
    readonly_fields = ("created_at", "verified_at")

    @admin.display(description="Status")
    def get_verification_status(self, obj):
        from django.utils import timezone
        if obj.is_verified:
            return mark_safe('<span style="color:#16a34a; font-weight:700;">✅ Verified</span>')
        if obj.expires_at < timezone.now():
            return mark_safe('<span style="color:#64748b; font-weight:600;">⏱️ Expired</span>')
        return mark_safe('<span style="color:#d97706; font-weight:700;">🟡 Pending Code</span>')


