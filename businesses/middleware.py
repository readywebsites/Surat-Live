from django.db import connection


class EnsureSchemaMiddleware:
    """
    Automatically verifies and heals the SQLite schema on the first incoming request
    (e.g. adding show_in_navbar, google_maps_link if missing) so storefronts, APIs,
    and admin panels never crash with OperationalError, even if a migration was
    interrupted on the live server.
    """
    _schema_verified = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not EnsureSchemaMiddleware._schema_verified:
            try:
                with connection.cursor() as cursor:
                    # 1. Ensure businesses_category columns (show_in_navbar)
                    cursor.execute("PRAGMA table_info(businesses_category)")
                    cat_cols = [c[1] for c in cursor.fetchall()]
                    if cat_cols and "show_in_navbar" not in cat_cols:
                        cursor.execute("ALTER TABLE businesses_category ADD COLUMN show_in_navbar BOOLEAN DEFAULT 0")

                    # 2. Ensure businesses_business columns (google_maps_link)
                    cursor.execute("PRAGMA table_info(businesses_business)")
                    biz_cols = [c[1] for c in cursor.fetchall()]
                    if biz_cols and "google_maps_link" not in biz_cols:
                        cursor.execute("ALTER TABLE businesses_business ADD COLUMN google_maps_link VARCHAR(500) DEFAULT ''")

                    # 3. Auto-seed default categories if empty so they immediately appear in admin and APIs
                    cursor.execute("SELECT count(*) FROM businesses_category")
                    if cursor.fetchone()[0] == 0:
                        default_categories = [
                            ("Business Consultancy & Digital Marketing", "website-development-digital-marketing", "Surat business consultancy, branding, digital marketing & web development.", "Briefcase", 1, 1, 1),
                            ("Textiles & Sarees", "textiles-sarees", "Direct Surat Jacquard looms, silk saree manufacturers, and fabric wholesalers.", "Scissors", 2, 1, 1),
                            ("Diamonds & Jewelry", "diamonds-jewelry", "Certified CVD lab-grown diamonds, natural diamond bourses, and jewelry artisans.", "Gem", 3, 1, 1),
                            ("Surti Street Food", "surti-street-food", "Authentic Surti Butter Locho, Ghari sweets, Khaman, and catering specialists.", "Utensils", 4, 1, 1),
                            ("Local Services", "local-services", "Logistics, cargo dispatch, machinery spares, and industrial support.", "Truck", 5, 1, 0),
                        ]
                        cursor.executemany(
                            """
                            INSERT INTO businesses_category (name, slug, description, icon, "order", is_active, show_in_navbar)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            default_categories,
                        )

                EnsureSchemaMiddleware._schema_verified = True
            except Exception:
                pass

        return self.get_response(request)
