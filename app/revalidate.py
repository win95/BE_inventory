"""Cầu revalidate sang Next.js (BE 8).

Strapi publish/unpublish/update → webhook tới FastAPI → FastAPI gọi
POST /api/revalidate của Frontend với secret chung, xóa tag cache
`strapi:<collection>` (quy ước của src/lib/strapi.ts). Không trỏ webhook
Strapi thẳng vào Next.js vì payload Strapi không mang secret/tag dạng này.

Không bao giờ raise khi revalidate lỗi: webhook vẫn trả 200 (Strapi khỏi
retry vô ích) và SSE content-updated đã đẩy nên Frontend vẫn fetch lại;
lỗi chỉ ghi log để theo dõi.
"""

import json
import logging
import urllib.error
import urllib.request

from . import config

logger = logging.getLogger(__name__)

# model (số ít, Strapi webhook) -> REST collection (số nhiều, tag FE dùng).
# Single type (home/global/data-snapshot) giữ nguyên tên.
MODEL_TO_COLLECTION = {
    "article": "articles",
    "case-study": "case-studies",
    "product": "products",
    "solution": "solutions",
    "ad-format": "ad-formats",
    "resource": "resources",
    "event": "events",
    "job": "jobs",
    "partner": "partners",
    "customer": "customers",
    "faq": "faqs",
    "home": "home",
    "global": "global",
    "data-snapshot": "data-snapshot",
}


def tag_for_model(model: str | None) -> str | None:
    if not model:
        return None
    collection = MODEL_TO_COLLECTION.get(model)
    if collection is None:
        # Model lạ: đoán số nhiều kiểu Anh (study -> studies, còn lại + s).
        collection = model[:-1] + "ies" if model.endswith("y") else model + "s"
    return f"strapi:{collection}"


def revalidate_frontend(tag: str) -> bool:
    """Gọi POST /api/revalidate của Frontend. Trả True khi 2xx."""
    if not config.REVALIDATE_SECRET:
        logger.info("revalidate: bỏ qua (chưa có REVALIDATE_SECRET)")
        return False
    url = f"{config.FRONTEND_URL}/api/revalidate"
    body = json.dumps({"secret": config.REVALIDATE_SECRET, "tag": tag}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            ok = 200 <= res.status < 300
            logger.info("revalidate: %s -> %s", tag, res.status)
            return ok
    except urllib.error.HTTPError as e:
        logger.warning("revalidate: %s -> HTTP %s", tag, e.code)
        return False
    except Exception as e:  # noqa: BLE001 - lỗi mạng thì chỉ log
        logger.warning("revalidate: %s -> lỗi %s", tag, e)
        return False
