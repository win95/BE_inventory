"""Tìm kiếm (BE 18-20, SRCH-01/02/03).

GET /api/search?q=...&locale=vi|en|all&market=vn|all&type=products,news
    &page=1&pageSize=20
Trả { results: [{type, slug, title, summary, url, locale, market, date}],
      facets: {all, products, solutions, resources, events, news, jobs},
      total, page, pageSize, source }.
- source "strapi": chỉ mục đọc live từ Strapi (cache 5 phút).
- source "fallback": Strapi không tới được — chỉ có 6 sản phẩm + 26 solution.
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .. import search as engine

router = APIRouter()


@router.get("/api/search")
def search_api(
    q: str = Query(min_length=1, max_length=200),
    locale: str = Query(default="vi", pattern=r"^(vi|en|all)$"),
    market: str = Query(default="vn", pattern=r"^(vn|global|id|th|all)$"),
    type: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
):
    types = None
    if type:
        wanted = [t.strip() for t in type.split(",") if t.strip()]
        unknown = [t for t in wanted if t not in engine.TYPES]
        if unknown:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "SEARCH_TYPE_INVALID",
                        "message": f"Loại không hợp lệ: {', '.join(unknown)}.",
                    }
                },
            )
        types = wanted
    return engine.search(
        q, locale=locale, market=market, types=types, page=page, page_size=pageSize
    )
