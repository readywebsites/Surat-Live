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

                EnsureSchemaMiddleware._schema_verified = True
            except Exception:
                pass

        return self.get_response(request)
