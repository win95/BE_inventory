"""Đăng nhập Google cho người dùng cuối (F13).

Luồng OAuth 2.0 chuẩn, đi qua Next.js (BFF — trình duyệt chỉ nói chuyện
với Next.js): /api/backend/auth/google (Next.js proxy sang đây) chuyển tới
Google, Google callback về /api/backend/auth/google/callback (Next.js proxy
sang đây), backend đổi code lấy token, lấy thông tin người dùng, lưu/cập
nhật vào bảng users rồi phát JWT (24h) và chuyển về Frontend kèm token.
Frontend lưu token và gửi kèm các request cần xác thực (phần Frontend xử
lý token là việc tiếp theo sau khi backend này chạy).

Redirect URI đăng ký trong Google Cloud console phải là
{FRONTEND_ORIGIN}/api/backend/auth/google/callback (xem .env.example).

Chưa cấu hình GOOGLE_CLIENT_ID/SECRET thì endpoint trả lỗi cấu hình rõ ràng
(503), không crash. Hai hệ phiên độc lập: editor đăng nhập Strapi admin
bằng tài khoản Strapi riêng, không dùng JWT này.
"""

import datetime
import json
import secrets
import sqlite3
import urllib.parse
import urllib.request

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import config, db
from ..schemas import ErrorResponse

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Tên cookie lưu `state` chống login CSRF (xem auth_google). Cookie này do
# backend đặt qua proxy Next.js nên thuộc origin của Frontend; proxy phải
# chuyển tiếp header Cookie/Set-Cookie (xem src/app/api/backend/[...path]).
_STATE_COOKIE = "oauth_state"


def _callback_url() -> str:
    # OAuth đi qua Next.js (BFF): Google redirect về
    # {frontend}/api/backend/auth/google/callback, Next.js proxy sang
    # endpoint này. Redirect URI này phải đăng ký trong Google Cloud console
    # (OAuth client) thì Google mới chấp nhận.
    frontend = config.FRONTEND_ORIGINS[0] if config.FRONTEND_ORIGINS else "http://localhost:3000"
    return f"{frontend}/api/backend/auth/google/callback"


def _not_configured():
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Đăng nhập Google chưa được cấu hình: thiếu GOOGLE_CLIENT_ID hoặc GOOGLE_CLIENT_SECRET.",
            }
        },
    )


@router.get("/api/auth/google")
def auth_google():
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return _not_configured()
    # `state` chống login CSRF: sinh ngẫu nhiên, lưu vào cookie HttpOnly
    # (SameSite=Lax, 10 phút) rồi đối chiếu ở callback. Trước đây state
    # sinh ra nhưng không lưu/kiểm tra nên không có tác dụng.
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": _callback_url(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")
    response.set_cookie(
        _STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600, path="/"
    )
    return response


@router.get("/api/auth/google/callback")
def auth_google_callback(
    request: Request,
    code: str = "",
    error: str = "",
    state: str = "",
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    if error:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "OAUTH_DENIED", "message": "Google từ chối đăng nhập."}},
        )
    # Đối chiếu `state` Google trả về với cookie đã đặt ở /api/auth/google.
    # Không khớp (hoặc thiếu) thì từ chối — chống login CSRF.
    expected_state = request.cookies.get(_STATE_COOKIE)
    if not state or not expected_state or state != expected_state:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "OAUTH_STATE_MISMATCH", "message": "Phiên đăng nhập không hợp lệ, thử lại."}},
        )
    if not code:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "OAUTH_NO_CODE", "message": "Thiếu mã xác thực từ Google."}},
        )
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return _not_configured()

    token_data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": _callback_url(),
            "grant_type": "authorization_code",
        }
    ).encode()
    token_req = urllib.request.Request(
        GOOGLE_TOKEN_URL, data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(token_req, timeout=15) as resp:
            token = json.loads(resp.read())
    except Exception:  # noqa: BLE001 - lỗi mạng/Google thì báo rõ, không lộ chi tiết
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "OAUTH_TOKEN_FAILED", "message": "Không đổi được mã xác thực với Google."}},
        )
    access_token = token.get("access_token")
    if not access_token:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "OAUTH_TOKEN_FAILED", "message": "Google không trả access token."}},
        )
    info_req = urllib.request.Request(
        GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
    )
    try:
        with urllib.request.urlopen(info_req, timeout=15) as resp:
            userinfo = json.loads(resp.read())
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "OAUTH_USERINFO_FAILED", "message": "Không lấy được thông tin người dùng từ Google."}},
        )

    google_sub = str(userinfo.get("sub", ""))
    email = str(userinfo.get("email", ""))
    if not google_sub or not email:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "OAUTH_USERINFO_FAILED", "message": "Google không trả đủ thông tin người dùng."}},
        )
    if userinfo.get("email_verified") is False:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "OAUTH_EMAIL_UNVERIFIED", "message": "Email Google chưa được xác minh."}},
        )
    conn.execute(
        "INSERT INTO users (google_sub, email, name, picture, last_login_at) VALUES (?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email, name=excluded.name, "
        "picture=excluded.picture, last_login_at=datetime('now')",
        (google_sub, email, userinfo.get("name"), userinfo.get("picture")),
    )
    conn.commit()

    now = datetime.datetime.now(datetime.timezone.utc)
    token_jwt = jwt.encode(
        {
            "sub": google_sub,
            "email": email,
            "iat": now,
            "exp": now + datetime.timedelta(hours=config.JWT_EXPIRE_HOURS),
        },
        config.JWT_SECRET,
        algorithm="HS256",
    )
    frontend = config.FRONTEND_ORIGINS[0] if config.FRONTEND_ORIGINS else "http://localhost:3000"
    response = RedirectResponse(f"{frontend}/?auth_token={token_jwt}")
    response.delete_cookie(_STATE_COOKIE, path="/")
    return response
