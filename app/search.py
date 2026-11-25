"""Tìm kiếm (BE 18-20, SRCH-01/02/03) — trên FastAPI, KHÔNG Meilisearch
(theo kiến trúc đã chốt 23/11/2026: search trên FastAPI thay Meilisearch,
CRM queue bằng tác vụ nền thay BullMQ).

Nguồn chỉ mục: nội dung công khai trên Strapi (single source of truth —
cùng dữ liệu giả đã seed ở cms/scripts/seed-fake-content.js). Đọc qua
REST, cache trong bộ nhớ 5 phút (STRAPI_URL trống hoặc Strapi không trả
lời thì dùng chỉ mục dự phòng: 6 sản phẩm + 26 solution, dữ liệu tĩnh
trong code — giống src/lib/products.ts của Frontend). Response luôn ghi
rõ "source": "strapi" | "fallback".

Khớp không dấu (giống POST /api/suggest): gấp dấu tiếng Việt rồi so
khớp mọi token của từ khóa trong tiêu đề + tóm tắt + tên.
"""

import json
import logging
import time
import unicodedata
import urllib.error
import urllib.request

from . import config

logger = logging.getLogger("awing.search")

TYPES = ("products", "solutions", "resources", "events", "news", "jobs")

# collection Strapi -> (loại kết quả, mẫu URL, trường tiêu đề, trường tóm tắt)
_COLLECTIONS = {
    "products": ("products", "/products/{slug}", "name", "tagline"),
    "solutions": ("solutions", "/products/{product}/{slug}", "name", "summary"),
    "resources": ("resources", "/resources/{slug}", "title", "summary"),
    "events": ("events", "/events/{slug}", "title", None),
    "articles": ("news", "/news/{slug}", "title", None),
    "jobs": ("jobs", "/careers/{slug}", "title", None),
}

# Chỉ mục dự phòng: 6 sản phẩm + 26 solution (khớp products.ts).
# Chỉ dùng khi Strapi không tới được — FE vẫn tìm được sản phẩm/solution.
_FALLBACK = [
    ("products", "location-based-channel", "Location-Based Channel",
     "The right people, in the right place, at the right moment."),
    ("products", "retail-media-activation", "Retail Media & Activation",
     "Put your brand next to the buying decision."),
    ("products", "measurement", "Measurement", "Prove impact with real numbers."),
    ("products", "insights", "Insights",
     "Understand consumers through real-world moments."),
    ("products", "network", "Network", "The network behind the moments."),
    ("products", "ads-manager", "Ads Manager", "Plan, track and optimise on your own."),
]
_FALLBACK_SOLUTIONS = [
    ("interactive-ad-experiences", "Interactive Ad Experiences", "location-based-channel"),
    ("geo-targeted-campaigns", "Geo-Targeted Campaigns", "location-based-channel"),
    ("place-based-audiences", "Place-Based Audiences", "location-based-channel"),
    ("wifi-splash-engagement", "Wi-Fi Splash Engagement", "location-based-channel"),
    ("always-on-reach", "Always-On Reach", "location-based-channel"),
    ("in-store-wifi-media", "In-Store Wi-Fi Media", "retail-media-activation"),
    ("shopper-activation", "Shopper Activation", "retail-media-activation"),
    ("mall-digital-promotions", "Mall Digital Promotions", "retail-media-activation"),
    ("sampling-and-coupons", "Sampling & Coupons", "retail-media-activation"),
    ("retail-partner-network", "Retail Partner Network", "retail-media-activation"),
    ("footfall-attribution", "Footfall Attribution", "measurement"),
    ("brand-lift", "Brand Lift", "measurement"),
    ("campaign-reporting", "Campaign Reporting", "measurement"),
    ("offline-conversion", "Offline Conversion", "measurement"),
    ("audience-insights", "Audience Insights", "insights"),
    ("location-trends", "Location Trends", "insights"),
    ("category-benchmarks", "Category Benchmarks", "insights"),
    ("custom-research", "Custom Research", "insights"),
    ("partner-network", "Partner Network", "network"),
    ("wifi-monetization", "Wi-Fi Monetization", "network"),
    ("venue-onboarding", "Venue Onboarding", "network"),
    ("network-health", "Network Health", "network"),
    ("campaign-builder", "Campaign Builder", "ads-manager"),
    ("audience-geo-targeting", "Audience & Geo Targeting", "ads-manager"),
    ("budget-and-bidding", "Budget & Bidding", "ads-manager"),
    ("live-reporting", "Live Reporting", "ads-manager"),
]
for _slug, _name, _product in _FALLBACK_SOLUTIONS:
    _FALLBACK.append(("solutions", _slug, _name, _name))

_cache: dict = {"at": 0.0, "items": [], "source": "fallback"}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Bỏ dấu gạch nối để "Wi-Fi" khớp token "wifi" (khớp chuỗi con).
    return stripped.replace("đ", "d").replace("Đ", "D").replace("-", "").lower()


def _fetch_collection(collection: str, locale: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        url = (
            f"{config.STRAPI_URL}/api/{collection}?locale={locale}"
            f"&pagination[page]={page}&pagination[pageSize]=100"
        )
        if collection == "solutions":
            url += "&populate=product"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                body = json.loads(res.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.warning("search: không đọc được %s (%s): %s", collection, locale, e)
            return []
        data = body.get("data") or []
        items.extend(data)
        pagination = (body.get("meta") or {}).get("pagination") or {}
        if len(data) < 100 or page >= (pagination.get("pageCount") or 1):
            break
        page += 1
    return items


def _build_index() -> tuple[list[dict], str]:
    if not config.STRAPI_URL:
        return _fallback_items(), "fallback"
    items: list[dict] = []
    for collection, (kind, url_tpl, title_field, summary_field) in _COLLECTIONS.items():
        for locale in ("vi", "en"):
            for entry in _fetch_collection(collection, locale):
                title = entry.get(title_field) or ""
                summary = entry.get(summary_field) if summary_field else ""
                slug = entry.get("slug") or ""
                if not title or not slug:
                    continue
                url = url_tpl.format(
                    slug=slug,
                    product=((entry.get("product") or {}).get("slug") or ""),
                )
                items.append({
                    "type": kind,
                    "slug": slug,
                    "title": title,
                    "summary": summary or "",
                    "url": url,
                    "locale": locale,
                    "market": entry.get("market") or "vn",
                    "date": entry.get("publishedDate") or entry.get("startDate"),
                    "_folded": _fold(f"{title} {summary} {slug}"),
                })
    if not items:
        logger.warning("search: Strapi không trả nội dung nào — dùng chỉ mục dự phòng")
        return _fallback_items(), "fallback"
    return items, "strapi"


def _fallback_items() -> list[dict]:
    # Tên sản phẩm/solution giữ tiếng Anh ở cả 2 locale (theo Figma) nên
    # mỗi mục mang locale "all" — khớp mọi locale đang xem.
    items = []
    for kind, slug, title, summary in _FALLBACK:
        url = f"/products/{slug}" if kind == "products" else ""
        if kind == "solutions":
            # _FALLBACK_SOLUTIONS là tuple (solution_slug, name,
            # product_slug): so theo solution_slug (phần tử thứ 1), lấy
            # product_slug (phần tử thứ 3). Trước đây so nhầm tên hiển thị
            # (phần tử thứ 2) với slug nên không bao giờ khớp và URL
            # thành /products//<slug>.
            product = next(
                (n for p, s, n in _FALLBACK_SOLUTIONS if p == slug), ""
            )
            url = f"/products/{product}/{slug}"
        items.append({
            "type": kind,
            "slug": slug,
            "title": title,
            "summary": summary,
            "url": url,
            "locale": "all",
            "market": "vn",
            "date": None,
            "_folded": _fold(f"{title} {summary} {slug}"),
        })
    return items


def _get_index() -> tuple[list[dict], str]:
    now = time.monotonic()
    if now - _cache["at"] > config.SEARCH_CACHE_TTL_SECONDS or not _cache["items"]:
        items, source = _build_index()
        _cache["at"] = now
        _cache["items"] = items
        _cache["source"] = source
    return _cache["items"], _cache["source"]


def search(
    q: str,
    *,
    locale: str = "vi",
    market: str = "vn",
    types: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    items, source = _get_index()
    tokens = [t for t in _fold(q).split() if t]
    wanted = set(types) if types else set(TYPES)
    # Lọc theo locale: mặc định locale đang xem; locale=all thì gộp cả 2
    # nhưng khử trùng theo (type, slug) — ưu tiên bản đúng locale UI.
    matched: dict[tuple[str, str], dict] = {}
    for item in items:
        if item["type"] not in wanted:
            continue
        if market != "all" and item["market"] != market:
            continue
        # SRCH-03: mặc định chỉ tìm trong locale đang xem; locale=all thì
        # tìm cả 2 ngôn ngữ, mỗi bản là một kết quả riêng (không khử trùng
        # chéo locale — người dùng đã chọn "mọi ngôn ngữ"). Mục locale="all"
        # (chỉ mục dự phòng) khớp mọi locale.
        if locale != "all" and item["locale"] not in (locale, "all"):
            continue
        if not all(tok in item["_folded"] for tok in tokens):
            continue
        key = (item["type"], item["slug"], item["locale"])
        matched[key] = item
    results = list(matched.values())
    # Sắp xếp: ngày mới nhất trước, rồi tiêu đề chứa cụm từ khóa lên đầu
    # (sort ổn định nên thứ tự ngày giữ nguyên trong từng nhóm).
    results.sort(key=lambda r: r["date"] or "", reverse=True)
    folded_q = _fold(q)
    results.sort(key=lambda r: 0 if folded_q in _fold(r["title"]) else 1)
    facets = {t: 0 for t in TYPES}
    facets["all"] = 0
    for r in results:
        facets[r["type"]] += 1
        facets["all"] += 1
    total = len(results)
    start = (page - 1) * page_size
    page_items = results[start:start + page_size]
    return {
        "results": [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in page_items
        ],
        "facets": facets,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "source": source,
    }
