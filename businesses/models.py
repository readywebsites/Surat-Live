from django.db import models, connection
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Lucide icon name or emoji")
    order = models.PositiveIntegerField(default=0, help_text="Display order in navbar")
    is_active = models.BooleanField(default=True, help_text="Show in navbar and site")

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Business(models.Model):
    name = models.CharField(max_length=200)

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="businesses"
    )

    description = models.TextField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    image = models.ImageField(
        upload_to="businesses/",
        blank=True,
        null=True
    )

    is_verified = models.BooleanField(
        default=False,
        help_text="Reviewed and approved by platform admin"
    )
    is_activated = models.BooleanField(
        default=False,
        help_text="Activated after vendor logs into the platform"
    )

    vendor_username = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        unique=True,
        help_text="Login username provided to vendor by admin"
    )
    vendor_password = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Login password provided to vendor by admin"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="products"
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )

    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True
    )

    is_available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Service(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="services"
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )

    image = models.ImageField(
        upload_to="services/",
        blank=True,
        null=True
    )

    is_available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Review(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    customer_name = models.CharField(max_length=100)

    rating = models.PositiveIntegerField(
        choices=[
            (1, "1 Star"),
            (2, "2 Stars"),
            (3, "3 Stars"),
            (4, "4 Stars"),
            (5, "5 Stars"),
        ]
    )

    comment = models.TextField()

    is_approved = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business.name} - {self.rating} Stars"


class VendorCredential(models.Model):
    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="login_credential",
        help_text="The business listing associated with these login credentials",
    )
    login_id = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique Login ID (Username, Phone, or Merchant ID) provided to vendor",
    )
    password = models.CharField(
        max_length=128,
        help_text="Password provided to vendor by admin for portal login",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable or disable login access for this vendor",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional internal notes by admin for this vendor account",
    )
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the vendor last logged in",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vendor Login Credential"
        verbose_name_plural = "Vendor Login Credentials"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.login_id} ({self.business.name})"


class BusinessRegistration(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("approved", "Approved & Verified"),
        ("rejected", "Rejected"),
    ]

    business_name = models.CharField(
        max_length=200,
        help_text="Name of the business or shop submitted for registration",
    )
    owner_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Full name of business owner or representative",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registrations",
        help_text="Selected industry category",
    )
    category_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Category name if not matched with an existing category",
    )
    phone = models.CharField(
        max_length=20,
        help_text="Primary phone or WhatsApp contact number",
    )
    email = models.EmailField(
        blank=True,
        help_text="Contact email address",
    )
    address = models.CharField(
        max_length=300,
        blank=True,
        help_text="Full address in Surat (market, road, area)",
    )
    description = models.TextField(
        blank=True,
        help_text="Details about business, products, services, or wholesale trade",
    )
    website = models.URLField(
        blank=True,
        help_text="Website or catalog URL",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Verification status evaluated by platform owners",
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes or verification logs by platform admin",
    )
    created_business = models.OneToOneField(
        Business,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registration_source",
        help_text="Verified business created once approved by admin",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pending Business Registration"
        verbose_name_plural = "Pending Business Registrations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.get_status_display()}) - {self.phone}"


class VendorUpdateLog(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="update_logs",
        help_text="The business listing that was updated by the vendor",
    )
    updated_at = models.DateTimeField(
        default=timezone.now,
        help_text="Exact date and time when the update occurred",
    )
    summary = models.TextField(
        blank=True,
        help_text="Summary of updated fields (e.g. Updated Phone, Address, Description)",
    )
    details = models.TextField(
        blank=True,
        help_text="Full before-and-after audit log of all updated fields",
    )

    class Meta:
        verbose_name = "Vendor Edit History"
        verbose_name_plural = "Vendor Edit Histories (Audit Logs)"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.business.name} - {self.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"


class BusinessCatalog(Business):
    """
    Proxy model representing merchant catalogs (products and services).
    Allows admin to browse businesses by title and manage all corresponding
    products, services, and catalog audit histories in one place without migrations.
    """
    class Meta:
        proxy = True
        verbose_name = "Merchant Catalog (Products & Services)"
        verbose_name_plural = "Merchant Catalogs (Products & Services)"


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ("inquiry", "Buyer Inquiry / Lead"),
        ("market", "Surat Market Update"),
        ("review", "Customer Review"),
        ("system", "System / Announcement"),
    ]
    TARGET_CHOICES = [
        ("all", "All (Users & Vendors)"),
        ("vendor", "Specific Vendor"),
        ("user", "Buyers / Public Users"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Target business listing if this notification is vendor-specific",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="inquiry")
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES, default="all")
    link = models.CharField(max_length=300, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Platform Notification"
        verbose_name_plural = "Platform Notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.category}] {self.title}"


def ensure_notification_table():
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS businesses_notification (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id BIGINT,
                    title VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    category VARCHAR(20) NOT NULL,
                    target_type VARCHAR(20) NOT NULL,
                    link VARCHAR(300) NOT NULL,
                    is_read BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(business_id) REFERENCES businesses_business(id) ON DELETE CASCADE
                )
            """)
    except Exception:
        pass


def ensure_vendorupdatelog_table():
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS businesses_vendorupdatelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id BIGINT NOT NULL,
                    updated_at DATETIME NOT NULL,
                    summary TEXT,
                    details TEXT,
                    FOREIGN KEY(business_id) REFERENCES businesses_business(id) ON DELETE CASCADE
                )
            """)
    except Exception:
        pass


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        help_text="The auth user account associated with this profile",
    )
    phone = models.CharField(max_length=20, blank=True, help_text="Contact phone or WhatsApp number")
    city = models.CharField(max_length=100, default="Surat", blank=True, help_text="City or neighborhood in Surat")
    saved_businesses = models.TextField(default="[]", blank=True, help_text="JSON list of bookmarked business IDs")

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} ({self.city})"


def ensure_userprofile_table():
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS businesses_userprofile (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    phone VARCHAR(20) DEFAULT '',
                    city VARCHAR(100) DEFAULT 'Surat',
                    saved_businesses TEXT DEFAULT '[]',
                    FOREIGN KEY(user_id) REFERENCES auth_user(id) ON DELETE CASCADE
                )
            """)
    except Exception:
        pass


class UserCredential(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="login_info",
        help_text="Linked Django auth user account",
    )
    login_id = models.CharField(
        max_length=150,
        help_text="Login ID / Username or Email used by customer to log in",
    )
    full_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Customer's full name",
    )
    email = models.EmailField(
        blank=True,
        help_text="Customer's email address",
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Customer's contact or WhatsApp number",
    )
    password = models.CharField(
        max_length=128,
        help_text="Password stored for admin reference and customer support",
    )
    city = models.CharField(
        max_length=100,
        default="Surat",
        blank=True,
        help_text="Surat neighborhood or city",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Account login status active or disabled",
    )
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the customer last logged in",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="Registration timestamp",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last profile or credential update",
    )

    class Meta:
        verbose_name = "Customer Login Credential"
        verbose_name_plural = "Customer Login Credentials (Users Login Info)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name or self.login_id} ({self.login_id})"


def ensure_usercredential_table():
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS businesses_usercredential (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    login_id VARCHAR(150) NOT NULL,
                    full_name VARCHAR(150),
                    email VARCHAR(254),
                    phone VARCHAR(20),
                    password VARCHAR(128) NOT NULL,
                    city VARCHAR(100) DEFAULT 'Surat',
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    last_login_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES auth_user(id) ON DELETE CASCADE
                )
            """)
    except Exception:
        pass


