import os
import re
import uuid
import json
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify
from django.db import connection, models
from django.contrib.auth.models import User
from .models import (
    Category,
    Business,
    Product,
    Service,
    Review,
    VendorCredential,
    BusinessRegistration,
    VendorUpdateLog,
    Notification,
    UserProfile,
    UserCredential,
    ensure_notification_table,
    ensure_vendorupdatelog_table,
    ensure_userprofile_table,
    ensure_usercredential_table,
)




def categories_list(request):
    data = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(businesses_category)")
            columns = [col[1] for col in cursor.fetchall()]

        if "slug" in columns and "is_active" in columns:
            categories = Category.objects.filter(is_active=True)
            if "order" in columns:
                categories = categories.order_by("order", "name")
            for cat in categories:
                data.append({
                    "id": cat.id,
                    "name": cat.name,
                    "slug": cat.slug or slugify(cat.name),
                    "description": cat.description,
                    "icon": getattr(cat, "icon", ""),
                    "order": getattr(cat, "order", 0),
                    "show_in_navbar": bool(getattr(cat, "show_in_navbar", False)),
                    "count": cat.businesses.count(),
                })
        else:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, name, description FROM businesses_category")
                rows = cursor.fetchall()
            for r in rows:
                data.append({
                    "id": r[0],
                    "name": r[1],
                    "slug": slugify(r[1]),
                    "description": r[2] or "",
                    "icon": "",
                    "order": 0,
                    "show_in_navbar": False,
                    "count": Business.objects.filter(category_id=r[0]).count(),
                })
    except Exception as e:
        pass

    return JsonResponse(data, safe=False)


def format_safe_image_url(request, image_field):
    if not image_field:
        return None
    val = str(image_field)
    if val.startswith(("http://", "https://")):
        return val
    try:
        return request.build_absolute_uri(image_field.url)
    except Exception:
        return val


def parse_catalog_images(raw_image_field, request=None):
    if not raw_image_field:
        return "", []
    raw_str = str(raw_image_field).strip()
    if not raw_str:
        return "", []

    images_list = []
    if raw_str.startswith("[") and raw_str.endswith("]"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, list):
                images_list = [str(img).strip() for img in parsed if str(img).strip()][:5]
        except Exception:
            images_list = [raw_str]
    else:
        images_list = [raw_str]

    formatted_list = []
    for img in images_list:
        if img.startswith(("http://", "https://")):
            formatted_list.append(img)
        elif request and img.startswith("/"):
            formatted_list.append(request.build_absolute_uri(img))
        elif request:
            try:
                formatted_list.append(request.build_absolute_uri(f"/media/{img}"))
            except Exception:
                formatted_list.append(img)
        else:
            formatted_list.append(img)

    primary = formatted_list[0] if formatted_list else ""
    return primary, formatted_list



def get_safe_business_qs():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(businesses_business)")
        cols = [c[1] for c in cursor.fetchall()]
    unmigrated = [
        f for f in ["is_activated", "vendor_username", "vendor_password", "google_maps_link"] if f not in cols
    ]
    if unmigrated:
        return Business.objects.defer(*unmigrated).select_related("category"), cols
    return Business.objects.select_related("category"), cols


def businesses_list(request):
    qs, cols = get_safe_business_qs()

    # Filter by verified / activated (unverified pending registrations and vendor-paused offline stores are hidden from public)
    if "is_activated" in cols:
        businesses = qs.filter(is_verified=True, is_activated=True).order_by("-created_at")
    else:
        businesses = qs.filter(is_verified=True).order_by("-created_at")

    # Search filter (name, description, address, category, products, services)
    q = request.GET.get("search") or request.GET.get("q")
    if q:
        q = q.strip()
        businesses = (
            businesses.filter(
                models.Q(name__icontains=q)
                | models.Q(description__icontains=q)
                | models.Q(address__icontains=q)
                | models.Q(category__name__icontains=q)
                | models.Q(products__name__icontains=q)
                | models.Q(services__name__icontains=q)
            )
            .distinct()
            .annotate(
                search_rank=models.Case(
                    models.When(name__iexact=q, then=models.Value(100)),
                    models.When(name__istartswith=q, then=models.Value(90)),
                    models.When(name__icontains=" " + q, then=models.Value(80)),
                    models.When(category__name__iexact=q, then=models.Value(75)),
                    models.When(category__name__istartswith=q, then=models.Value(70)),
                    models.When(category__name__icontains=" " + q, then=models.Value(65)),
                    models.When(name__icontains=q, then=models.Value(60)),
                    models.When(category__name__icontains=q, then=models.Value(50)),
                    models.When(products__name__istartswith=q, then=models.Value(45)),
                    models.When(services__name__istartswith=q, then=models.Value(45)),
                    models.When(products__name__icontains=q, then=models.Value(35)),
                    models.When(services__name__icontains=q, then=models.Value(35)),
                    models.When(address__icontains=q, then=models.Value(20)),
                    models.When(description__icontains=q, then=models.Value(10)),
                    default=models.Value(0),
                    output_field=models.IntegerField(),
                )
            )
            .order_by("-search_rank", "-created_at")
        )

    # Category filter (id, name, or slug)
    category_param = request.GET.get("category") or request.GET.get("category_slug")
    if category_param:
        category_param = category_param.strip()
        if category_param.isdigit():
            businesses = businesses.filter(category_id=int(category_param))
        else:
            businesses = businesses.filter(
                models.Q(category__slug__iexact=category_param)
                | models.Q(category__name__iexact=category_param)
                | models.Q(category__slug__icontains=category_param)
                | models.Q(category__name__icontains=category_param)
            )

    data = []
    seen_ids = set()

    for business in businesses:
        if business.id in seen_ids:
            continue
        seen_ids.add(business.id)

        # Calculate rating and reviews
        approved_reviews = business.reviews.filter(is_approved=True)
        review_count = approved_reviews.count()
        avg_rating = (
            round(sum(r.rating for r in approved_reviews) / review_count, 1)
            if review_count > 0
            else 5.0
        )

        image_url = None
        if business.image:
            image_url = request.build_absolute_uri(business.image.url)

        cat_slug = getattr(business.category, "slug", "") or slugify(business.category.name)

        data.append({
            "id": business.id,
            "name": business.name,
            "category": business.category.name,
            "category_slug": cat_slug,
            "description": business.description,
            "address": business.address,
            "phone": business.phone,
            "email": business.email,
            "website": business.website,
            "google_maps_link": getattr(business, "google_maps_link", "") or "",
            "image": image_url,
            "is_verified": business.is_verified,
            "is_activated": getattr(business, "is_activated", True) if "is_activated" in cols else True,
            "rating": avg_rating,
            "reviews_count": review_count,
            "created_at": business.created_at.strftime("%Y-%m-%d") if business.created_at else "",
        })

    return JsonResponse(data, safe=False)


def business_detail(request, pk):
    qs, _ = get_safe_business_qs()
    try:
        business = qs.get(pk=pk)
    except Business.DoesNotExist:
        return JsonResponse({"error": "Business not found"}, status=404)

    approved_reviews = business.reviews.filter(is_approved=True).order_by("-created_at")
    review_count = approved_reviews.count()
    avg_rating = (
        round(sum(r.rating for r in approved_reviews) / review_count, 1)
        if review_count > 0
        else 5.0
    )

    image_url = format_safe_image_url(request, business.image)

    cat_slug = getattr(business.category, "slug", "") or slugify(business.category.name)

    products = []
    for p in business.products.filter(is_available=True).order_by("-created_at"):
        primary_img, img_list = parse_catalog_images(p.image, request)
        products.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": float(p.price) if p.price is not None else None,
            "image": primary_img,
            "images": img_list,
            "is_available": p.is_available,
        })

    services = []
    for s in business.services.filter(is_available=True).order_by("-created_at"):
        primary_img, img_list = parse_catalog_images(s.image, request)
        services.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price": float(s.price) if s.price is not None else None,
            "image": primary_img,
            "images": img_list,
            "is_available": s.is_available,
        })

    reviews = [
        {
            "id": r.id,
            "customer_name": r.customer_name,
            "rating": r.rating,
            "comment": r.comment,
            "created_at": r.created_at.strftime("%b %d, %Y") if r.created_at else "",
        }
        for r in approved_reviews
    ]

    data = {
        "id": business.id,
        "name": business.name,
        "category": business.category.name,
        "category_slug": cat_slug,
        "description": business.description,
        "address": business.address,
        "phone": business.phone,
        "email": business.email,
        "website": business.website,
        "google_maps_link": getattr(business, "google_maps_link", "") or "",
        "image": image_url,
        "is_verified": business.is_verified,
        "rating": avg_rating,
        "reviews_count": review_count,
        "created_at": business.created_at.strftime("%b %d, %Y") if business.created_at else "",
        "products": products,
        "services": services,
        "reviews": reviews,
    }

    return JsonResponse(data)


import json
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def submit_review(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        business = Business.objects.get(pk=pk)
    except Business.DoesNotExist:
        return JsonResponse({"error": "Business not found"}, status=404)

    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
            customer_name = body.get("customer_name", "").strip()
            rating = int(body.get("rating", 5))
            comment = body.get("comment", "").strip()
        else:
            customer_name = request.POST.get("customer_name", "").strip()
            rating = int(request.POST.get("rating", 5))
            comment = request.POST.get("comment", "").strip()

        if not customer_name:
            return JsonResponse({"error": "Name is required"}, status=400)
        if not comment:
            return JsonResponse({"error": "Review comment is required"}, status=400)

        if rating < 1 or rating > 5:
            rating = 5

        review = Review.objects.create(
            business=business,
            customer_name=customer_name,
            rating=rating,
            comment=comment,
            is_approved=True,
        )

        try:
            ensure_notification_table()
            stars_str = "★" * rating
            Notification.objects.create(
                business=business,
                title=f"New {rating}★ Review from {customer_name}",
                message=f"{customer_name} rated your store {stars_str}: \"{comment[:90]}\"",
                category="review",
                target_type="vendor",
                link=f"/business/{business.id}",
                is_read=False,
                created_at=timezone.now(),
            )
        except Exception:
            pass

        return JsonResponse({
            "success": True,
            "message": "Thank you! Your review has been posted.",
            "review": {
                "id": review.id,
                "customer_name": review.customer_name,
                "rating": review.rating,
                "comment": review.comment,
                "created_at": review.created_at.strftime("%b %d, %Y") if review.created_at else "Just now",
            },
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def register_business(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        name = (body.get("businessName") or body.get("name") or "").strip()
        owner_name = (body.get("ownerName") or "").strip()
        category_name = (body.get("category") or "").strip()
        phone = (body.get("phone") or "").strip()
        email = (body.get("email") or "").strip()
        address = (body.get("address") or "").strip()
        description = (body.get("description") or "").strip()
        website = (body.get("website") or "").strip()

        if not name:
            return JsonResponse({"error": "Business name is required"}, status=400)
        if not phone:
            return JsonResponse({"error": "Phone number is required"}, status=400)

        # Match category or fallback to first
        category = None
        if category_name:
            category = Category.objects.filter(
                models.Q(name__iexact=category_name)
                | models.Q(slug__iexact=category_name)
                | models.Q(name__icontains=category_name)
            ).first()
        if not category:
            category = Category.objects.first()

        # Check if BusinessRegistration table exists in SQLite
        has_reg_table = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='businesses_businessregistration'"
                )
                has_reg_table = bool(cursor.fetchone())
        except Exception:
            has_reg_table = False

        if has_reg_table:
            reg = BusinessRegistration.objects.create(
                business_name=name,
                owner_name=owner_name,
                category=category,
                category_name=category_name,
                phone=phone,
                email=email,
                address=address,
                description=description,
                website=website,
                status="pending",
            )
            return JsonResponse({
                "success": True,
                "message": "Business registration submitted successfully! Pending verification in admin portal.",
                "registration": {
                    "id": reg.id,
                    "reference_id": f"OS-REG-{reg.id:04d}",
                    "business_name": reg.business_name,
                    "owner_name": reg.owner_name,
                    "category": category.name if category else category_name,
                    "phone": reg.phone,
                    "status": "pending",
                },
            })

        # Fallback if unmigrated: create in Business table with is_verified=False
        full_desc = description
        if owner_name:
            full_desc = f"Owner: {owner_name}. {description}".strip()

        try:
            business = Business.objects.create(
                name=name,
                category=category,
                phone=phone,
                email=email,
                address=address,
                description=full_desc,
                website=website,
                is_verified=False,
            )
            biz_id = business.id
            biz_name = business.name
            biz_cat = business.category.name if business.category else ""
            biz_verified = business.is_verified
        except Exception:
            # Fallback if unmigrated columns exist in model before migrate is run
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO businesses_business (name, category_id, phone, email, address, description, website, is_verified, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, 0, datetime('now'))",
                    [name, category.id if category else 1, phone, email, address, full_desc, website]
                )
                biz_id = cursor.lastrowid
                biz_name = name
                biz_cat = category.name if category else ""
                biz_verified = False

        return JsonResponse({
            "success": True,
            "message": "Business listing submitted successfully! Pending verification in admin portal.",
            "business": {
                "id": biz_id,
                "reference_id": f"OS-REG-{biz_id:04d}",
                "name": biz_name,
                "category": biz_cat,
                "is_verified": biz_verified,
            },
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def mask_phone_number(p):
    if not p:
        return ""
    p_clean = str(p).strip()
    if len(p_clean) <= 4:
        return p_clean
    if len(p_clean) >= 10:
        return p_clean[:5] + " **** " + p_clean[-2:]
    return p_clean[:2] + " **** " + p_clean[-2:]


def track_registration_status(request):
    """
    Public lookup endpoint allowing vendors to check their listing/registration status
    without logging in, using their phone number or Application Reference ID (e.g. OS-REG-0001).
    """
    if request.method != "GET":
        return JsonResponse({"error": "Only GET allowed"}, status=405)

    raw_query = (
        request.GET.get("query")
        or request.GET.get("phone")
        or request.GET.get("id")
        or ""
    ).strip()

    if not raw_query:
        return JsonResponse(
            {"success": False, "found": False, "error": "Please enter your registered phone number or reference ID."},
            status=400,
        )

    # Clean digits
    digits_only = re.sub(r"\D", "", raw_query)
    last10 = digits_only[-10:] if len(digits_only) >= 10 else digits_only

    # Extract ID if formatted as OS-REG-0042, OS-BIZ-0042, REG-42, #42, or short integer
    parsed_id = None
    id_match = re.search(r"(?:OS-REG-|OS-BIZ-|REG-|#)?(\d+)", raw_query, re.IGNORECASE)
    if id_match and not digits_only.startswith("98") and not digits_only.startswith("91") and len(digits_only) < 7:
        try:
            parsed_id = int(id_match.group(1))
        except ValueError:
            parsed_id = None

    reg = None

    # 1. Search in BusinessRegistration table
    has_reg_table = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='businesses_businessregistration'"
            )
            has_reg_table = bool(cursor.fetchone())
    except Exception:
        has_reg_table = False

    if has_reg_table:
        qs = BusinessRegistration.objects.all().select_related("category", "created_business")

        # Priority 1: Match parsed ID if small integer / ref
        if parsed_id:
            reg = qs.filter(id=parsed_id).first()

        # Priority 2: Match phone
        if not reg and last10 and len(last10) >= 7:
            reg = qs.filter(phone__icontains=last10).order_by("-created_at").first()

        # Priority 3: Match raw phone or exact input
        if not reg:
            reg = qs.filter(phone__iexact=raw_query).order_by("-created_at").first()

        # Priority 4: Match business name if query matches exactly
        if not reg and len(raw_query) >= 3:
            reg = qs.filter(business_name__iexact=raw_query).order_by("-created_at").first()

    if reg:
        status = reg.status or "pending"
        has_creds = False
        biz_id = None
        if reg.created_business:
            biz_id = reg.created_business.id
            try:
                has_creds = VendorCredential.objects.filter(business=reg.created_business).exists()
            except Exception:
                has_creds = False

        status_display = "Pending Review"
        stepper_step = 2  # 1: Submitted, 2: Market Review, 3: Admin Approval, 4: Live & Dispatched
        if status == "approved":
            status_display = "Approved & Live"
            stepper_step = 4
        elif status == "rejected":
            status_display = "Needs Attention"
            stepper_step = 2

        return JsonResponse({
            "success": True,
            "found": True,
            "registration": {
                "id": reg.id,
                "reference_id": f"OS-REG-{reg.id:04d}",
                "business_name": reg.business_name,
                "owner_name": reg.owner_name or "Business Owner",
                "category": reg.category.name if reg.category else (reg.category_name or "General Trade"),
                "phone_masked": mask_phone_number(reg.phone),
                "address": reg.address or "Surat, Gujarat",
                "status": status,
                "status_display": status_display,
                "stepper_step": stepper_step,
                "admin_notes": reg.admin_notes or "",
                "submitted_at": reg.created_at.strftime("%d %b %Y, %I:%M %p") if reg.created_at else "",
                "business_id": biz_id,
                "has_credentials": has_creds,
            },
        })

    # 2. Fallback check: Search in Business table
    biz = None
    if parsed_id:
        biz = Business.objects.filter(id=parsed_id).first()
    if not biz and last10 and len(last10) >= 7:
        biz = Business.objects.filter(phone__icontains=last10).first()
    if not biz:
        biz = Business.objects.filter(phone__iexact=raw_query).first()

    if biz:
        is_verified = getattr(biz, "is_verified", False)
        status = "approved" if is_verified else "pending"
        has_creds = False
        try:
            has_creds = VendorCredential.objects.filter(business=biz).exists()
        except Exception:
            has_creds = False

        return JsonResponse({
            "success": True,
            "found": True,
            "registration": {
                "id": biz.id,
                "reference_id": f"OS-BIZ-{biz.id:04d}",
                "business_name": biz.name,
                "owner_name": "Business Owner",
                "category": biz.category.name if biz.category else "General Trade",
                "phone_masked": mask_phone_number(biz.phone),
                "address": biz.address or "Surat, Gujarat",
                "status": status,
                "status_display": "Approved & Live" if is_verified else "Pending Review",
                "stepper_step": 4 if is_verified else 2,
                "admin_notes": "",
                "submitted_at": biz.created_at.strftime("%d %b %Y, %I:%M %p") if getattr(biz, "created_at", None) else "",
                "business_id": biz.id if is_verified else None,
                "has_credentials": has_creds,
            },
        })

    return JsonResponse({
        "success": True,
        "found": False,
        "message": f"No listing registration found for '{raw_query}'. Please verify your 10-digit registered phone number or Application Reference ID.",
    })


@csrf_exempt
def vendor_login(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()

        if not username or not password:
            return JsonResponse(
                {"error": "Please provide both vendor Login ID / Username and Password."},
                status=400,
            )

        # 1. First attempt: Authenticate via dedicated VendorCredential model if migrated
        has_cred_table = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='businesses_vendorcredential'"
                )
                has_cred_table = bool(cursor.fetchone())
        except Exception:
            has_cred_table = False

        if has_cred_table:
            cred = VendorCredential.objects.select_related("business", "business__category").filter(
                models.Q(login_id__iexact=username)
                | models.Q(business__phone__iexact=username)
                | models.Q(business__email__iexact=username),
                password=password,
            ).first()

            if cred:
                # Check active status of credentials
                if not cred.is_active:
                    return JsonResponse(
                        {
                            "error": "This vendor account is currently inactive. Please contact the platform admin for assistance."
                        },
                        status=403,
                    )

                business = cred.business

                # Check if business is approved/verified by admin
                if not business.is_verified:
                    return JsonResponse(
                        {
                            "error": f"Your business '{business.name}' is currently pending review by our admin team. Login access will be granted once your listing is approved."
                        },
                        status=403,
                    )

                # Record last login time
                cred.last_login_at = timezone.now()
                cred.save(update_fields=["last_login_at"])

                # Activate newly registered business on their first login, otherwise preserve vendor's chosen live/offline status
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA table_info(businesses_business)")
                    cols = [c[1] for c in cursor.fetchall()]

                if "is_activated" in cols and not cred.last_login_at:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE businesses_business SET is_activated = 1 WHERE id = %s",
                            [business.id],
                        )
                    is_active_val = True
                else:
                    is_active_val = bool(getattr(business, "is_activated", True)) if "is_activated" in cols else True

                cat_slug = getattr(business.category, "slug", "") or slugify(business.category.name)

                return JsonResponse({
                    "success": True,
                    "message": f"Welcome back, {business.name}! Your account is active.",
                    "business": {
                        "id": business.id,
                        "name": business.name,
                        "category": business.category.name if business.category else "",
                        "category_slug": cat_slug,
                        "phone": business.phone,
                        "email": business.email,
                        "address": business.address,
                        "is_verified": business.is_verified,
                        "is_activated": is_active_val,
                        "login_id": cred.login_id,
                    },
                })

        # 2. Fallback attempt: Authenticate via legacy Business fields or pre-migration fallback
        qs, cols = get_safe_business_qs()

        business = None
        if "vendor_username" in cols and "vendor_password" in cols:
            business = qs.filter(
                models.Q(vendor_username__iexact=username)
                | models.Q(phone__iexact=username)
                | models.Q(email__iexact=username),
                vendor_password=password,
            ).first()
        else:
            business = qs.filter(
                models.Q(phone__iexact=username) | models.Q(email__iexact=username)
            ).first()

        if not business:
            return JsonResponse(
                {
                    "error": "Invalid vendor credentials. The Login ID or Password provided does not match any registered business in our records."
                },
                status=401,
            )

        # Check if approved by admin
        if not business.is_verified:
            return JsonResponse(
                {
                    "error": f"Your business '{business.name}' is currently pending review by our admin team. Login access will be granted once your listing is approved."
                },
                status=403,
            )

        is_active_val = bool(getattr(business, "is_activated", True)) if "is_activated" in cols else True
        cat_slug = getattr(business.category, "slug", "") or slugify(business.category.name)

        return JsonResponse({
            "success": True,
            "message": f"Welcome back, {business.name}!",
            "business": {
                "id": business.id,
                "name": business.name,
                "category": business.category.name if business.category else "",
                "category_slug": cat_slug,
                "phone": business.phone,
                "email": business.email,
                "address": business.address,
                "google_maps_link": getattr(business, "google_maps_link", "") or "",
                "is_verified": business.is_verified,
                "is_activated": is_active_val,
            },
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def vendor_profile(request):
    ensure_vendorupdatelog_table()

    if request.method == "GET":
        vendor_id = request.GET.get("vendor_id")
        if not vendor_id:
            return JsonResponse({"error": "vendor_id parameter is required"}, status=400)

        try:
            business = Business.objects.select_related("category").get(pk=vendor_id)
        except Business.DoesNotExist:
            return JsonResponse({"error": "Business not found"}, status=404)

        img_str = str(business.image) if business.image else ""
        if img_str.startswith(("http://", "https://")):
            image_url = img_str
        elif business.image:
            try:
                image_url = request.build_absolute_uri(business.image.url)
            except Exception:
                image_url = img_str
        else:
            image_url = ""

        logs_data = []
        try:
            logs = VendorUpdateLog.objects.filter(business=business).order_by("-updated_at")[:50]
            for l in logs:
                logs_data.append({
                    "id": l.id,
                    "updated_at": l.updated_at.strftime("%d %b %Y, %I:%M %p"),
                    "summary": l.summary,
                    "details": l.details,
                })
        except Exception:
            pass

        products_data = []
        try:
            for p in business.products.all().order_by("-created_at"):
                primary_img, img_list = parse_catalog_images(p.image, request)
                products_data.append({
                    "id": p.id,
                    "name": p.name,
                    "description": p.description or "",
                    "price": float(p.price) if p.price is not None else None,
                    "image": primary_img,
                    "images": img_list,
                    "is_available": p.is_available,
                    "created_at": p.created_at.strftime("%d %b %Y") if p.created_at else "",
                })
        except Exception:
            pass

        services_data = []
        try:
            for s in business.services.all().order_by("-created_at"):
                primary_img, img_list = parse_catalog_images(s.image, request)
                services_data.append({
                    "id": s.id,
                    "name": s.name,
                    "description": s.description or "",
                    "price": float(s.price) if s.price is not None else None,
                    "image": primary_img,
                    "images": img_list,
                    "is_available": s.is_available,
                    "created_at": s.created_at.strftime("%d %b %Y") if s.created_at else "",
                })
        except Exception:
            pass

        cat_slug = getattr(business.category, "slug", "") or (slugify(business.category.name) if business.category else "")

        return JsonResponse({
            "success": True,
            "business": {
                "id": business.id,
                "name": business.name,
                "category_id": business.category_id,
                "category_name": business.category.name if business.category else "",
                "category_slug": cat_slug,
                "description": business.description or "",
                "address": business.address or "",
                "google_maps_link": getattr(business, "google_maps_link", "") or "",
                "phone": business.phone or "",
                "email": business.email or "",
                "website": business.website or "",
                "image": image_url,
                "is_verified": business.is_verified,
                "is_activated": business.is_activated,
            },
            "products": products_data,
            "services": services_data,
            "update_logs": logs_data,
        })

    elif request.method in ["POST", "PUT"]:
        try:
            if request.content_type == "application/json":
                body = json.loads(request.body.decode("utf-8"))
            else:
                body = request.POST

            vendor_id = body.get("vendor_id") or body.get("id")
            if not vendor_id:
                return JsonResponse({"error": "vendor_id is required"}, status=400)

            try:
                business = Business.objects.select_related("category").get(pk=vendor_id)
            except Business.DoesNotExist:
                return JsonResponse({"error": "Business not found"}, status=404)

            new_name = (body.get("name") or "").strip()
            new_phone = (body.get("phone") or "").strip()
            new_email = (body.get("email") or "").strip()
            new_address = (body.get("address") or "").strip()
            new_google_maps_link = (body.get("google_maps_link") or "").strip()
            new_website = (body.get("website") or "").strip()
            new_description = (body.get("description") or "").strip()
            new_image = (body.get("image") or "").strip()
            new_category_id = body.get("category_id")

            if not new_name:
                return JsonResponse({"error": "Business name cannot be empty"}, status=400)
            if not new_phone:
                return JsonResponse({"error": "Phone number cannot be empty"}, status=400)

            changes = []
            update_kwargs = {}

            # Check Business Name
            if new_name != (business.name or ""):
                changes.append({
                    "field": "Business Name",
                    "before": business.name or "(empty)",
                    "after": new_name,
                })
                update_kwargs["name"] = new_name

            # Check Phone
            if new_phone != (business.phone or ""):
                changes.append({
                    "field": "Phone",
                    "before": business.phone or "(empty)",
                    "after": new_phone,
                })
                update_kwargs["phone"] = new_phone

            # Check Email
            if new_email != (business.email or ""):
                changes.append({
                    "field": "Email",
                    "before": business.email or "(empty)",
                    "after": new_email,
                })
                update_kwargs["email"] = new_email

            # Check Address
            if new_address != (business.address or ""):
                changes.append({
                    "field": "Address",
                    "before": business.address or "(empty)",
                    "after": new_address,
                })
                update_kwargs["address"] = new_address

            # Check Google Maps Link
            current_maps = getattr(business, "google_maps_link", "") or ""
            if new_google_maps_link != current_maps:
                changes.append({
                    "field": "Google Maps Link",
                    "before": current_maps or "(empty)",
                    "after": new_google_maps_link or "(cleared)",
                })
                update_kwargs["google_maps_link"] = new_google_maps_link

            # Check Website
            if new_website != (business.website or ""):
                changes.append({
                    "field": "Website",
                    "before": business.website or "(empty)",
                    "after": new_website,
                })
                update_kwargs["website"] = new_website

            # Check Description
            if new_description != (business.description or ""):
                changes.append({
                    "field": "Description",
                    "before": business.description or "(empty)",
                    "after": new_description,
                })
                update_kwargs["description"] = new_description

            # Check Image
            current_img_str = str(business.image) if business.image else ""
            if new_image and new_image != current_img_str:
                changes.append({
                    "field": "Image URL",
                    "before": current_img_str or "(empty)",
                    "after": new_image,
                })
                update_kwargs["image"] = new_image

            # Check Category
            if new_category_id is not None and new_category_id != "":
                try:
                    cat_id_int = int(new_category_id)
                    if cat_id_int != business.category_id:
                        new_cat = Category.objects.filter(pk=cat_id_int).first()
                        if new_cat:
                            changes.append({
                                "field": "Category",
                                "before": business.category.name if business.category else "(none)",
                                "after": new_cat.name,
                            })
                            update_kwargs["category_id"] = new_cat.id
                except (ValueError, TypeError):
                    pass

            # Check Storefront Live / Offline status
            if "is_activated" in body or "is_live" in body:
                raw_act = body.get("is_activated") if "is_activated" in body else body.get("is_live")
                new_act = bool(raw_act) if raw_act not in [0, "0", False, "false", "offline", "False"] else False
                curr_act = bool(getattr(business, "is_activated", True))
                if new_act != curr_act:
                    changes.append({
                        "field": "Storefront Visibility",
                        "before": "LIVE (Online)" if curr_act else "OFFLINE (Paused)",
                        "after": "LIVE (Online)" if new_act else "OFFLINE (Paused)",
                    })
                    update_kwargs["is_activated"] = 1 if new_act else 0

            if not changes:
                img_str = str(business.image) if business.image else ""
                if img_str.startswith(("http://", "https://")):
                    image_url = img_str
                elif business.image:
                    try:
                        image_url = request.build_absolute_uri(business.image.url)
                    except Exception:
                        image_url = img_str
                else:
                    image_url = ""

                return JsonResponse({
                    "success": True,
                    "message": "No changes detected. Business details are already up to date.",
                    "business": {
                        "id": business.id,
                        "name": business.name,
                        "category_id": business.category_id,
                        "category_name": business.category.name if business.category else "",
                        "category_slug": getattr(business.category, "slug", "") or (slugify(business.category.name) if business.category else ""),
                        "description": business.description or "",
                        "address": business.address or "",
                        "google_maps_link": getattr(business, "google_maps_link", "") or "",
                        "phone": business.phone or "",
                        "email": business.email or "",
                        "website": business.website or "",
                        "image": image_url,
                        "is_verified": business.is_verified,
                        "is_activated": business.is_activated,
                    },
                })

            # Apply updates directly to DB table
            Business.objects.filter(pk=business.id).update(**update_kwargs)
            business.refresh_from_db()

            # Record Audit Log
            now_dt = timezone.now()
            changed_labels = [c["field"] for c in changes]
            summary = f"Updated {', '.join(changed_labels)}"

            details_lines = [
                f"Timestamp: {now_dt.strftime('%d %b %Y, %I:%M:%S %p UTC')}",
                f"Modified Fields: {', '.join(changed_labels)}",
                "--------------------------------------------------",
            ]
            for c in changes:
                details_lines.append(f"• {c['field']}:")
                details_lines.append(f"  Before:     {c['before']}")
                details_lines.append(f"  Updated to: {c['after']}")
                details_lines.append("")

            details_text = "\n".join(details_lines).strip()

            try:
                VendorUpdateLog.objects.create(
                    business=business,
                    updated_at=now_dt,
                    summary=summary,
                    details=details_text,
                )
            except Exception:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO businesses_vendorupdatelog (business_id, updated_at, summary, details) VALUES (%s, %s, %s, %s)",
                        [business.id, now_dt, summary, details_text]
                    )

            # Fresh logs list
            logs_data = []
            try:
                logs = VendorUpdateLog.objects.filter(business=business).order_by("-updated_at")[:50]
                for l in logs:
                    logs_data.append({
                        "id": l.id,
                        "updated_at": l.updated_at.strftime("%d %b %Y, %I:%M %p"),
                        "summary": l.summary,
                        "details": l.details,
                    })
            except Exception:
                pass

            img_str = str(business.image) if business.image else ""
            if img_str.startswith(("http://", "https://")):
                image_url = img_str
            elif business.image:
                try:
                    image_url = request.build_absolute_uri(business.image.url)
                except Exception:
                    image_url = img_str
            else:
                image_url = ""

            cat_slug = getattr(business.category, "slug", "") or (slugify(business.category.name) if business.category else "")

            return JsonResponse({
                "success": True,
                "message": f"Successfully updated business details! Changes have been permanently saved and recorded in admin history.",
                "business": {
                    "id": business.id,
                    "name": business.name,
                    "category_id": business.category_id,
                    "category_name": business.category.name if business.category else "",
                    "category_slug": cat_slug,
                    "description": business.description or "",
                    "address": business.address or "",
                    "google_maps_link": getattr(business, "google_maps_link", "") or "",
                    "phone": business.phone or "",
                    "email": business.email or "",
                    "website": business.website or "",
                    "image": image_url,
                    "is_verified": business.is_verified,
                    "is_activated": business.is_activated,
                },
                "update_logs": logs_data,
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def vendor_toggle_live(request):
    """
    Toggles the business between Live (Online) and Offline (Paused).
    Provides vendors full control to take their store offline for a week, month, or holiday,
    and turn it back live anytime with 1 click.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        vendor_id = body.get("vendor_id") or body.get("id")
        if not vendor_id:
            return JsonResponse({"error": "vendor_id is required"}, status=400)

        try:
            business = Business.objects.get(pk=vendor_id)
        except Business.DoesNotExist:
            return JsonResponse({"error": "Business not found"}, status=404)

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(businesses_business)")
            cols = [c[1] for c in cursor.fetchall()]

        curr_act = bool(getattr(business, "is_activated", True)) if "is_activated" in cols else True

        # Target status: explicitly passed or flip current
        if "is_live" in body or "is_activated" in body:
            raw_target = body.get("is_live") if "is_live" in body else body.get("is_activated")
            new_status = bool(raw_target) if raw_target not in [0, "0", False, "false", "offline", "False"] else False
        else:
            new_status = not curr_act

        if "is_activated" in cols:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE businesses_business SET is_activated = %s WHERE id = %s",
                    [1 if new_status else 0, business.id],
                )

        business.refresh_from_db()

        # Record audit log
        ensure_vendorupdatelog_table()
        now_dt = timezone.now()
        status_label_old = "LIVE (Online)" if curr_act else "OFFLINE (Paused)"
        status_label_new = "LIVE (Online)" if new_status else "OFFLINE (Paused)"
        summary = f"Storefront Status changed to {status_label_new}"
        details = (
            f"Timestamp: {now_dt.strftime('%d %b %Y, %I:%M:%S %p UTC')}\n"
            f"Action: Vendor toggled storefront visibility\n"
            f"Previous Status: {status_label_old}\n"
            f"New Status: {status_label_new}\n"
            f"Note: {'Storefront is now live and discoverable to customers across Surat.' if new_status else 'Storefront is paused and hidden from public search & category listings.'}"
        )
        VendorUpdateLog.objects.create(
            business=business,
            summary=summary,
            details=details,
        )

        logs_data = [
            {
                "id": l.id,
                "updated_at": l.updated_at.strftime("%d %b %Y, %I:%M %p"),
                "summary": l.summary,
                "details": l.details,
            }
            for l in VendorUpdateLog.objects.filter(business=business).order_by("-updated_at")[:25]
        ]

        msg = (
            "Your store is now LIVE and visible to buyers across Surat!"
            if new_status
            else "Your store is now OFFLINE. Public listing is hidden while you are on break."
        )

        return JsonResponse({
            "success": True,
            "message": msg,
            "is_activated": new_status,
            "is_live": new_status,
            "update_logs": logs_data,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def vendor_catalog_item(request):
    ensure_vendorupdatelog_table()

    if request.method not in ["POST", "PUT"]:
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        vendor_id = body.get("vendor_id")
        if not vendor_id:
            return JsonResponse({"error": "vendor_id is required"}, status=400)

        try:
            business = Business.objects.get(pk=vendor_id)
        except Business.DoesNotExist:
            return JsonResponse({"error": "Business not found"}, status=404)

        item_type = (body.get("item_type") or "product").strip().lower()
        if item_type not in ["product", "service"]:
            return JsonResponse({"error": "item_type must be 'product' or 'service'"}, status=400)

        item_id = body.get("id") or body.get("item_id")
        name = (body.get("name") or "").strip()
        description = (body.get("description") or "").strip()
        raw_price = body.get("price")
        price = None
        if raw_price is not None and str(raw_price).strip() != "":
            try:
                price = float(raw_price)
            except (ValueError, TypeError):
                price = None

        images_raw = body.get("images")
        if isinstance(images_raw, list):
            clean_images = [str(x).strip() for x in images_raw if str(x).strip()][:5]
            image = json.dumps(clean_images) if clean_images else ""
        else:
            image = (body.get("image") or "").strip()

        is_available = body.get("is_available", True)
        if isinstance(is_available, str):
            is_available = is_available.lower() in ["true", "1", "yes"]

        if not name:
            return JsonResponse({"error": f"{item_type.capitalize()} name cannot be empty"}, status=400)

        now_dt = timezone.now()

        if item_id:
            # Updating existing item
            if item_type == "product":
                item = Product.objects.filter(pk=item_id, business=business).first()
            else:
                item = Service.objects.filter(pk=item_id, business=business).first()

            if not item:
                return JsonResponse({"error": f"{item_type.capitalize()} item not found"}, status=404)

            changes = []
            update_kwargs = {}

            if name != item.name:
                changes.append({
                    "field": "Name",
                    "before": item.name,
                    "after": name,
                })
                update_kwargs["name"] = name

            old_price = float(item.price) if item.price is not None else None
            if price != old_price:
                changes.append({
                    "field": "Price",
                    "before": f"₹{old_price:,.2f}" if old_price is not None else "Price on Inquiry",
                    "after": f"₹{price:,.2f}" if price is not None else "Price on Inquiry",
                })
                update_kwargs["price"] = price

            if bool(is_available) != bool(item.is_available):
                changes.append({
                    "field": "Availability Status",
                    "before": "Available / In Stock" if item.is_available else "Out of Stock / Unavailable",
                    "after": "Available / In Stock" if is_available else "Out of Stock / Unavailable",
                })
                update_kwargs["is_available"] = is_available

            if description != (item.description or ""):
                changes.append({
                    "field": "Description",
                    "before": item.description or "(empty)",
                    "after": description or "(empty)",
                })
                update_kwargs["description"] = description

            old_img = str(item.image) if item.image else ""
            if image and image != old_img:
                changes.append({
                    "field": "Product Images",
                    "before": f"{len(json.loads(old_img))} photo(s)" if (old_img.startswith('[') and old_img.endswith(']')) else ("1 photo" if old_img else "No photo"),
                    "after": f"{len(json.loads(image))} photo(s)" if (image.startswith('[') and image.endswith(']')) else ("1 photo" if image else "No photo"),
                })
                update_kwargs["image"] = image

            if changes:
                if item_type == "product":
                    Product.objects.filter(pk=item.id).update(**update_kwargs)
                else:
                    Service.objects.filter(pk=item.id).update(**update_kwargs)

                # Record audit log in VendorUpdateLog
                changed_labels = [c["field"] for c in changes]
                summary = f"Updated {item_type.capitalize()}: {name} ({', '.join(changed_labels)})"
                details_lines = [
                    f"Timestamp: {now_dt.strftime('%d %b %Y, %I:%M:%S %p UTC')}",
                    f"Action: Vendor Updated {item_type.capitalize()} '{name}'",
                    f"Modified Fields: {', '.join(changed_labels)}",
                    "--------------------------------------------------",
                ]
                for c in changes:
                    details_lines.append(f"• {c['field']}:")
                    details_lines.append(f"  Before:     {c['before']}")
                    details_lines.append(f"  Updated to: {c['after']}")
                    details_lines.append("")

                details_text = "\n".join(details_lines).strip()

                try:
                    VendorUpdateLog.objects.create(
                        business=business,
                        updated_at=now_dt,
                        summary=summary,
                        details=details_text,
                    )
                except Exception:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO businesses_vendorupdatelog (business_id, updated_at, summary, details) VALUES (%s, %s, %s, %s)",
                            [business.id, now_dt, summary, details_text],
                        )

            message = f"Successfully updated {item_type} '{name}'."
            saved_id = item.id

        else:
            # Creating new item
            if item_type == "product":
                item = Product.objects.create(
                    business=business,
                    name=name,
                    description=description,
                    price=price,
                    image=image,
                    is_available=is_available,
                )
            else:
                item = Service.objects.create(
                    business=business,
                    name=name,
                    description=description,
                    price=price,
                    image=image,
                    is_available=is_available,
                )

            summary = f"Added New {item_type.capitalize()}: {name}"
            details_lines = [
                f"Timestamp: {now_dt.strftime('%d %b %Y, %I:%M:%S %p UTC')}",
                f"Action: Vendor Added New {item_type.capitalize()}",
                "--------------------------------------------------",
                f"• Item Name: {name}",
                f"• Price: {f'₹{price:,.2f}' if price is not None else 'Price on Inquiry'}",
                f"• Status: {'Available / In Stock' if is_available else 'Out of Stock'}",
                f"• Description: {description or '(none)'}",
                f"• Image URL: {image or '(none)'}",
            ]
            details_text = "\n".join(details_lines).strip()

            try:
                VendorUpdateLog.objects.create(
                    business=business,
                    updated_at=now_dt,
                    summary=summary,
                    details=details_text,
                )
            except Exception:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO businesses_vendorupdatelog (business_id, updated_at, summary, details) VALUES (%s, %s, %s, %s)",
                        [business.id, now_dt, summary, details_text],
                    )

            message = f"Successfully added {item_type} '{name}' to your storefront showcase!"
            saved_id = item.id

        # Return fresh lists of products and services
        products_data = []
        for p in business.products.all().order_by("-created_at"):
            primary_img, img_list = parse_catalog_images(p.image, request)
            products_data.append({
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "price": float(p.price) if p.price is not None else None,
                "image": primary_img,
                "images": img_list,
                "is_available": p.is_available,
                "created_at": p.created_at.strftime("%d %b %Y") if p.created_at else "",
            })

        services_data = []
        for s in business.services.all().order_by("-created_at"):
            primary_img, img_list = parse_catalog_images(s.image, request)
            services_data.append({
                "id": s.id,
                "name": s.name,
                "description": s.description or "",
                "price": float(s.price) if s.price is not None else None,
                "image": primary_img,
                "images": img_list,
                "is_available": s.is_available,
                "created_at": s.created_at.strftime("%d %b %Y") if s.created_at else "",
            })

        logs_data = []
        try:
            logs = VendorUpdateLog.objects.filter(business=business).order_by("-updated_at")[:50]
            for l in logs:
                logs_data.append({
                    "id": l.id,
                    "updated_at": l.updated_at.strftime("%d %b %Y, %I:%M %p"),
                    "summary": l.summary,
                    "details": l.details,
                })
        except Exception:
            pass

        return JsonResponse({
            "success": True,
            "message": message,
            "saved_id": saved_id,
            "item_type": item_type,
            "products": products_data,
            "services": services_data,
            "update_logs": logs_data,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def vendor_catalog_delete(request):
    ensure_vendorupdatelog_table()

    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        vendor_id = body.get("vendor_id")
        item_type = (body.get("item_type") or "product").strip().lower()
        item_id = body.get("id") or body.get("item_id")

        if not vendor_id or not item_id:
            return JsonResponse({"error": "vendor_id and item_id are required"}, status=400)

        try:
            business = Business.objects.get(pk=vendor_id)
        except Business.DoesNotExist:
            return JsonResponse({"error": "Business not found"}, status=404)

        if item_type == "product":
            item = Product.objects.filter(pk=item_id, business=business).first()
        else:
            item = Service.objects.filter(pk=item_id, business=business).first()

        if not item:
            return JsonResponse({"error": f"{item_type.capitalize()} item not found"}, status=404)

        item_name = item.name
        old_price = float(item.price) if item.price is not None else None
        now_dt = timezone.now()

        summary = f"Removed {item_type.capitalize()}: {item_name}"
        details_lines = [
            f"Timestamp: {now_dt.strftime('%d %b %Y, %I:%M:%S %p UTC')}",
            f"Action: Vendor Removed {item_type.capitalize()} from Storefront",
            "--------------------------------------------------",
            f"• Name: {item_name}",
            f"• Previous Price: {f'₹{old_price:,.2f}' if old_price is not None else 'Price on Inquiry'}",
            f"• Description: {item.description or '(none)'}",
        ]
        details_text = "\n".join(details_lines).strip()

        # Delete item from database
        item.delete()

        try:
            VendorUpdateLog.objects.create(
                business=business,
                updated_at=now_dt,
                summary=summary,
                details=details_text,
            )
        except Exception:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO businesses_vendorupdatelog (business_id, updated_at, summary, details) VALUES (%s, %s, %s, %s)",
                    [business.id, now_dt, summary, details_text],
                )

        products_data = []
        for p in business.products.all().order_by("-created_at"):
            primary_img, img_list = parse_catalog_images(p.image, request)
            products_data.append({
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "price": float(p.price) if p.price is not None else None,
                "image": primary_img,
                "images": img_list,
                "is_available": p.is_available,
                "created_at": p.created_at.strftime("%d %b %Y") if p.created_at else "",
            })

        services_data = []
        for s in business.services.all().order_by("-created_at"):
            primary_img, img_list = parse_catalog_images(s.image, request)
            services_data.append({
                "id": s.id,
                "name": s.name,
                "description": s.description or "",
                "price": float(s.price) if s.price is not None else None,
                "image": primary_img,
                "images": img_list,
                "is_available": s.is_available,
                "created_at": s.created_at.strftime("%d %b %Y") if s.created_at else "",
            })

        logs_data = []
        try:
            logs = VendorUpdateLog.objects.filter(business=business).order_by("-updated_at")[:50]
            for l in logs:
                logs_data.append({
                    "id": l.id,
                    "updated_at": l.updated_at.strftime("%d %b %Y, %I:%M %p"),
                    "summary": l.summary,
                    "details": l.details,
                })
        except Exception:
            pass

        return JsonResponse({
            "success": True,
            "message": f"Successfully removed {item_type} '{item_name}'.",
            "products": products_data,
            "services": services_data,
            "update_logs": logs_data,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def upload_vendor_image(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    files = request.FILES.getlist("images") or request.FILES.getlist("file") or request.FILES.getlist("image")
    if not files and "file" in request.FILES:
        files = [request.FILES["file"]]

    if not files:
        return JsonResponse({"error": "No image file provided for upload."}, status=400)

    # Max 1MB = 1024 * 1024 bytes (1,048,576 bytes)
    MAX_SIZE = 1 * 1024 * 1024

    for f in files:
        if f.size > MAX_SIZE:
            size_mb = round(f.size / (1024 * 1024), 2)
            return JsonResponse({
                "error": f"The image '{f.name}' is {size_mb} MB, which exceeds our maximum upload limit of 1 MB per image. Please upload a compressed image under 1 MB.",
                "file_name": f.name,
                "file_size": f.size,
                "max_size": MAX_SIZE,
            }, status=400)

    upload_dir = os.path.join(settings.BASE_DIR, "media", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    saved_urls = []
    for f in files:
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            ext = ".jpg"

        filename = f"img_{uuid.uuid4().hex[:10]}{ext}"
        filepath = os.path.join(upload_dir, filename)

        with open(filepath, "wb") as dest:
            for chunk in f.chunks():
                dest.write(chunk)

        url = f"/media/uploads/{filename}"
        saved_urls.append(request.build_absolute_uri(url))

    return JsonResponse({
        "success": True,
        "urls": saved_urls,
        "url": saved_urls[0] if saved_urls else "",
        "message": f"Successfully uploaded {len(saved_urls)} image(s)."
    })


def format_time_ago(dt):
    if not dt:
        return "Just now"
    try:
        diff = timezone.now() - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "Just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 7:
            return f"{days}d ago"
        return dt.strftime("%d %b")
    except Exception:
        return "Recent"


def seed_default_notifications_if_empty():
    try:
        ensure_notification_table()
        if Notification.objects.count() == 0:
            now = timezone.now()
            defaults = [
                {
                    "title": "Wholesale Jacquard Saree Inquiry",
                    "message": "Boutique buyer from Ahmedabad requested price quotation for 80 Jacquard Silk Sarees.",
                    "category": "inquiry",
                    "target_type": "all",
                    "link": "/textiles",
                    "is_read": False,
                    "created_at": now - timezone.timedelta(minutes=5),
                },
                {
                    "title": "Surat Diamond Bourse CVD Rates",
                    "message": "Daily polished diamond trading prices updated for Mahidharpura & Varachha diamond markets.",
                    "category": "market",
                    "target_type": "all",
                    "link": "/diamonds",
                    "is_read": False,
                    "created_at": now - timezone.timedelta(minutes=25),
                },
                {
                    "title": "New Verified Review Posted",
                    "message": "Rajesh Patel posted a 5-star review: 'Excellent quality silk sarees and fast response!'",
                    "category": "review",
                    "target_type": "all",
                    "link": "/textiles",
                    "is_read": False,
                    "created_at": now - timezone.timedelta(hours=1),
                },
                {
                    "title": "Surti Wedding Catering Inquiry",
                    "message": "New inquiry received for 200 plates authentic butter locho live counter for a wedding reception in Vesu.",
                    "category": "inquiry",
                    "target_type": "all",
                    "link": "/food",
                    "is_read": True,
                    "created_at": now - timezone.timedelta(hours=3),
                },
                {
                    "title": "Ring Road Logistics Dispatch",
                    "message": "Express parcel cargo truck departs from Sahara Darwaja to Delhi & Mumbai markets today at 7 PM.",
                    "category": "market",
                    "target_type": "all",
                    "link": "/services",
                    "is_read": True,
                    "created_at": now - timezone.timedelta(hours=6),
                },
                {
                    "title": "Biz499 Verified Merchant Program",
                    "message": "Get lifetime direct WhatsApp leads and zero commission merchant listing with OnlineSurat Biz499.",
                    "category": "system",
                    "target_type": "all",
                    "link": "/biz499-services",
                    "is_read": True,
                    "created_at": now - timezone.timedelta(days=1),
                },
            ]
            for item in defaults:
                Notification.objects.create(**item)
    except Exception:
        pass


def notifications_list(request):
    """
    Returns dynamic notifications list.
    - If vendor_id provided: includes vendor-specific leads, reviews + public market feeds.
    - If no vendor_id: includes public user feeds (market rates, platform announcements).
    """
    ensure_notification_table()
    seed_default_notifications_if_empty()

    vendor_id = request.GET.get("vendor_id")
    try:
        qs = Notification.objects.all().order_by("-created_at")
        if vendor_id and str(vendor_id).strip().isdigit():
            v_id = int(vendor_id)
            qs = qs.filter(
                models.Q(business_id=v_id) |
                models.Q(target_type="all") |
                models.Q(business__isnull=True, target_type="vendor")
            )
        else:
            qs = qs.filter(target_type__in=["all", "user"])

        items = []
        for n in qs[:50]:
            items.append({
                "id": f"notif_{n.id}",
                "title": n.title,
                "message": n.message,
                "time": format_time_ago(n.created_at),
                "category": n.category,
                "isRead": bool(n.is_read),
                "link": n.link or "",
                "target_type": n.target_type,
                "business_id": n.business_id,
                "created_at": n.created_at.isoformat() if n.created_at else "",
            })
        return JsonResponse(items, safe=False)
    except Exception as e:
        return JsonResponse([], safe=False)


@csrf_exempt
def mark_notification_read(request):
    """
    Marks a specific notification or all notifications as read.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    ensure_notification_table()
    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        notif_id = body.get("id")
        mark_all = body.get("all", False)
        vendor_id = body.get("vendor_id")

        if mark_all:
            qs = Notification.objects.filter(is_read=False)
            if vendor_id and str(vendor_id).strip().isdigit():
                qs = qs.filter(models.Q(business_id=int(vendor_id)) | models.Q(target_type="all"))
            qs.update(is_read=True)
            return JsonResponse({"success": True, "message": "All notifications marked as read."})

        if notif_id:
            clean_id = str(notif_id).replace("notif_", "").strip()
            if clean_id.isdigit():
                Notification.objects.filter(pk=int(clean_id)).update(is_read=True)
            return JsonResponse({"success": True, "message": "Notification marked as read."})

        return JsonResponse({"error": "No notification id or action specified."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def log_buyer_lead(request):
    """
    Records a real dynamic lead/inquiry notification when a buyer clicks
    'Inquire Price' (WhatsApp), 'Book Service', or 'Call Vendor'.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    ensure_notification_table()
    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        biz_id = body.get("business_id")
        if not biz_id:
            return JsonResponse({"error": "business_id is required"}, status=400)

        business = Business.objects.filter(pk=biz_id).first()
        if not business:
            return JsonResponse({"error": "Business not found"}, status=404)

        item_name = (body.get("item_name") or "").strip()
        channel = (body.get("channel") or "WhatsApp").strip()

        if item_name:
            title = f"{item_name} Lead ({channel})"
            message = f"Buyer initiated a direct {channel} inquiry for '{item_name}'."
        else:
            title = f"Storefront Inquiry ({channel})"
            message = f"Buyer clicked to contact your store via {channel} from OnlineSurat directory."

        notif = Notification.objects.create(
            business=business,
            title=title,
            message=message,
            category="inquiry",
            target_type="vendor",
            link=f"/business/{business.id}",
            is_read=False,
            created_at=timezone.now(),
        )

        return JsonResponse({
            "success": True,
            "message": "Lead recorded successfully.",
            "notification_id": f"notif_{notif.id}",
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def get_user_profile_safe(user):
    """
    Safely retrieves or creates a UserProfile for a User without failing on DB quirks.
    """
    ensure_userprofile_table()
    try:
        profile = UserProfile.objects.filter(user=user).first()
        if not profile:
            profile = UserProfile.objects.create(
                user=user,
                phone="",
                city="Surat",
                saved_businesses="[]",
            )
        return profile
    except Exception:
        # Raw SQL fallback
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, phone, city, saved_businesses FROM businesses_userprofile WHERE user_id = %s", [user.id])
                row = cursor.fetchone()
                if not row:
                    cursor.execute(
                        "INSERT INTO businesses_userprofile (user_id, phone, city, saved_businesses) VALUES (%s, %s, %s, %s)",
                        [user.id, "", "Surat", "[]"]
                    )
            return UserProfile.objects.filter(user=user).first()
        except Exception:
            return None


@csrf_exempt
def user_register(request):
    """
    Registers a new regular customer / buyer account on OnlineSurat.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    ensure_userprofile_table()
    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        name = (body.get("name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        phone = (body.get("phone") or "").strip()
        password = (body.get("password") or "").strip()
        city = (body.get("city") or "Surat").strip()

        if not name:
            return JsonResponse({"error": "Full name is required."}, status=400)
        if not email:
            return JsonResponse({"error": "Email address is required."}, status=400)
        if not password or len(password) < 6:
            return JsonResponse({"error": "Password must be at least 6 characters long."}, status=400)

        # Check existing user
        if User.objects.filter(models.Q(email__iexact=email) | models.Q(username__iexact=email)).exists():
            return JsonResponse({
                "error": f"An account with email '{email}' already exists. Please log in instead."
            }, status=400)

        # Unique username generator
        base_username = email.split("@")[0].replace(".", "_")[:20]
        unique_username = f"{base_username}_{uuid.uuid4().hex[:5]}"

        user = User.objects.create_user(
            username=unique_username,
            email=email,
            password=password,
            first_name=name,
        )

        profile = get_user_profile_safe(user)
        if profile:
            profile.phone = phone
            profile.city = city
            profile.save()

        # Save customer credentials for admin panel visibility
        try:
            ensure_usercredential_table()
            UserCredential.objects.create(
                user=user,
                login_id=email,
                full_name=name,
                email=email,
                phone=phone,
                password=password,
                city=city,
                is_active=True,
                created_at=timezone.now(),
            )
        except Exception:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO businesses_usercredential (user_id, login_id, full_name, email, phone, password, city, is_active, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [user.id, email, name, email, phone, password, city, 1, timezone.now(), timezone.now()]
                    )
            except Exception:
                pass

        # Welcome notification
        try:
            ensure_notification_table()
            Notification.objects.create(
                title=f"Welcome to OnlineSurat, {name}!",
                message="Your customer account has been created. Start exploring Surat diamond bourses, textile markets, and local services.",
                category="system",
                target_type="user",
                link="/user-dashboard",
                is_read=False,
                created_at=timezone.now(),
            )
        except Exception:
            pass


        return JsonResponse({
            "success": True,
            "message": f"Welcome to OnlineSurat, {name}!",
            "user": {
                "id": user.id,
                "username": user.username,
                "name": user.first_name,
                "email": user.email,
                "phone": phone,
                "city": city,
                "date_joined": user.date_joined.strftime("%B %Y"),
                "saved_count": 0,
            },
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def user_login(request):
    """
    Logs in an existing customer / buyer by Email, Username, or Phone.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    ensure_userprofile_table()
    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        username_input = (body.get("username") or body.get("email") or "").strip()
        password = (body.get("password") or "").strip()

        if not username_input or not password:
            return JsonResponse({"error": "Please provide your login email/username and password."}, status=400)

        user = User.objects.filter(
            models.Q(email__iexact=username_input) |
            models.Q(username__iexact=username_input)
        ).first()

        # If not found by email or username, try looking up by phone number in UserProfile
        if not user:
            prof = UserProfile.objects.filter(phone__iexact=username_input).first()
            if prof:
                user = prof.user

        if not user or not user.check_password(password):
            return JsonResponse({
                "error": "Invalid credentials. The email or password entered does not match our customer records."
            }, status=401)

        # Update last_login_at on UserCredential
        try:
            ensure_usercredential_table()
            UserCredential.objects.filter(user=user).update(last_login_at=timezone.now())
        except Exception:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE businesses_usercredential SET last_login_at = %s WHERE user_id = %s",
                        [timezone.now(), user.id]
                    )
            except Exception:
                pass

        profile = get_user_profile_safe(user)
        phone = profile.phone if profile else ""
        city = profile.city if profile else "Surat"

        saved_ids = []
        if profile and profile.saved_businesses:
            try:
                saved_ids = json.loads(profile.saved_businesses)
            except Exception:
                saved_ids = []

        return JsonResponse({
            "success": True,
            "message": f"Welcome back, {user.first_name or user.username}!",
            "user": {
                "id": user.id,
                "username": user.username,
                "name": user.first_name or user.username,
                "email": user.email,
                "phone": phone,
                "city": city,
                "date_joined": user.date_joined.strftime("%B %Y") if user.date_joined else "Recent",
                "saved_count": len(saved_ids),
                "saved_business_ids": saved_ids,
            },
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def user_profile(request):
    """
    Retrieves or updates customer profile details.
    """
    ensure_userprofile_table()
    user_id = request.GET.get("user_id") or request.POST.get("user_id")

    if request.method in ["POST", "PUT"]:
        try:
            if request.content_type == "application/json":
                body = json.loads(request.body.decode("utf-8"))
            else:
                body = request.POST

            user_id = body.get("user_id") or body.get("id")
            if not user_id:
                return JsonResponse({"error": "user_id is required."}, status=400)

            user = User.objects.filter(pk=user_id).first()
            if not user:
                return JsonResponse({"error": "User not found."}, status=404)

            name = (body.get("name") or "").strip()
            phone = (body.get("phone") or "").strip()
            city = (body.get("city") or "").strip()
            new_password = (body.get("new_password") or "").strip()

            if name:
                user.first_name = name
            if new_password and len(new_password) >= 6:
                user.set_password(new_password)
            user.save()

            profile = get_user_profile_safe(user)
            if profile:
                if phone:
                    profile.phone = phone
                if city:
                    profile.city = city
                profile.save()

            # Also sync with UserCredential if exists
            try:
                ensure_usercredential_table()
                cred = UserCredential.objects.filter(user=user).first()
                if cred:
                    if name:
                        cred.full_name = name
                    if phone:
                        cred.phone = phone
                    if city:
                        cred.city = city
                    if new_password and len(new_password) >= 6:
                        cred.password = new_password
                    cred.updated_at = timezone.now()
                    cred.save()
            except Exception:
                pass

            return JsonResponse({
                "success": True,
                "message": "Your profile has been updated successfully.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "name": user.first_name or user.username,
                    "email": user.email,
                    "phone": profile.phone if profile else "",
                    "city": profile.city if profile else "Surat",
                    "date_joined": user.date_joined.strftime("%B %Y") if user.date_joined else "Recent",
                },
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    # GET
    if not user_id:
        return JsonResponse({"error": "user_id is required."}, status=400)

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return JsonResponse({"error": "User not found."}, status=404)

    profile = get_user_profile_safe(user)
    saved_ids = []
    if profile and profile.saved_businesses:
        try:
            saved_ids = json.loads(profile.saved_businesses)
        except Exception:
            saved_ids = []

    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "name": user.first_name or user.username,
        "email": user.email,
        "phone": profile.phone if profile else "",
        "city": profile.city if profile else "Surat",
        "date_joined": user.date_joined.strftime("%B %Y") if user.date_joined else "Recent",
        "saved_count": len(saved_ids),
        "saved_business_ids": saved_ids,
    })


@csrf_exempt
def user_dashboard_data(request):
    """
    Returns aggregated data for the customer dashboard:
    - Saved bookmarked businesses
    - Inquiries sent
    - Reviews submitted by this customer
    """
    ensure_userprofile_table()
    user_id = request.GET.get("user_id")
    if not user_id:
        return JsonResponse({"error": "user_id is required."}, status=400)

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return JsonResponse({"error": "User not found."}, status=404)

    profile = get_user_profile_safe(user)
    saved_ids = []
    if profile and profile.saved_businesses:
        try:
            saved_ids = json.loads(profile.saved_businesses)
        except Exception:
            saved_ids = []

    # Fetch full business objects for saved list
    saved_businesses_data = []
    if saved_ids:
        qs, _ = get_safe_business_qs()
        saved_qs = qs.filter(id__in=saved_ids)
        for b in saved_qs:
            approved_reviews = b.reviews.filter(is_approved=True)
            r_count = approved_reviews.count()
            avg_rating = round(sum(r.rating for r in approved_reviews) / r_count, 1) if r_count > 0 else 5.0

            img_url = format_safe_image_url(request, b.image)
            cat_slug = getattr(b.category, "slug", "") or slugify(b.category.name) if b.category else ""

            saved_businesses_data.append({
                "id": b.id,
                "name": b.name,
                "category": b.category.name if b.category else "Merchant",
                "category_slug": cat_slug,
                "address": b.address or "",
                "phone": b.phone or "",
                "image": img_url,
                "rating": avg_rating,
                "reviews_count": r_count,
                "is_verified": b.is_verified,
            })

    # Fetch reviews submitted by this customer (matched by customer name or email)
    user_reviews_data = []
    try:
        user_reviews = Review.objects.filter(
            models.Q(customer_name__iexact=user.first_name) |
            models.Q(customer_name__iexact=user.username)
        ).select_related("business").order_by("-created_at")[:20]

        for r in user_reviews:
            user_reviews_data.append({
                "id": r.id,
                "business_id": r.business_id,
                "business_name": r.business.name if r.business else "Store",
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.strftime("%d %b %Y") if r.created_at else "Recent",
            })
    except Exception:
        pass

    # Fetch inquiries / leads
    inquiries_data = []
    try:
        ensure_notification_table()
        notifs = Notification.objects.filter(category="inquiry").order_by("-created_at")[:15]
        for n in notifs:
            inquiries_data.append({
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "time": format_time_ago(n.created_at),
                "link": n.link or "",
            })
    except Exception:
        pass

    return JsonResponse({
        "success": True,
        "saved_businesses": saved_businesses_data,
        "reviews": user_reviews_data,
        "inquiries": inquiries_data,
        "stats": {
            "saved_count": len(saved_businesses_data),
            "reviews_count": len(user_reviews_data),
            "inquiries_count": len(inquiries_data),
        },
    })


@csrf_exempt
def user_toggle_saved(request):
    """
    Bookmarks or un-bookmarks a business in the customer's saved list.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    ensure_userprofile_table()
    try:
        if request.content_type == "application/json":
            body = json.loads(request.body.decode("utf-8"))
        else:
            body = request.POST

        user_id = body.get("user_id")
        business_id = body.get("business_id")

        if not user_id or not business_id:
            return JsonResponse({"error": "user_id and business_id are required."}, status=400)

        user = User.objects.filter(pk=user_id).first()
        if not user:
            return JsonResponse({"error": "User not found."}, status=404)

        try:
            biz_id_int = int(business_id)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Invalid business_id."}, status=400)

        profile = get_user_profile_safe(user)
        saved_list = []
        if profile and profile.saved_businesses:
            try:
                saved_list = json.loads(profile.saved_businesses)
            except Exception:
                saved_list = []

        is_now_saved = False
        if biz_id_int in saved_list:
            saved_list.remove(biz_id_int)
            is_now_saved = False
            msg = "Store removed from your saved list."
        else:
            saved_list.append(biz_id_int)
            is_now_saved = True
            msg = "Store saved to your favorites!"

        if profile:
            profile.saved_businesses = json.dumps(saved_list)
            profile.save()

        return JsonResponse({
            "success": True,
            "is_saved": is_now_saved,
            "saved_business_ids": saved_list,
            "message": msg,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)








