"""Gợi ý chiến dịch theo prompt (F02, F06, F07, F08)."""

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import config, db, locale_names, rate_limit, suggest as suggest_logic
from ..schemas import SuggestRequest, SuggestResponse

router = APIRouter()


@router.post("/api/suggest", response_model=SuggestResponse)
def post_suggest(
    payload: SuggestRequest,
    request: Request,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    # Không có danh tính trong payload nên giới hạn theo IP — sau BFF thì
    # đây là giới hạn chung qua proxy (xem app/rate_limit.py).
    if rate_limit.limited(rate_limit.ip_key(request), config.SUGGEST_RATE_LIMIT_PER_MINUTE):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "Gửi quá nhanh, thử lại sau 1 phút."}},
        )
    return suggest_logic.suggest(
        payload.prompt, conn, payload.page, payload.pageSize,
        locale_names.parse_locale(payload.locale), payload.logPrompt,
    )
