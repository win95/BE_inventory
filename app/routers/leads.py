"""Lead form R1-2 (LEAD-01) + Contact Us + Newsletter.

POST /api/leads — lead form mới: validate E.164 + email (Pydantic),
xác minh Turnstile (giả lập khi chưa có secret), lưu lead + UTM + nhật ký
đồng ý theo mục đích, tạo OTP và gửi email giả lập (ghi log), chống trùng
(email chưa xác thực trong 10 phút thì dùng lại lead cũ thay vì tạo mới),
rate limit 5/phút/IP.
POST /api/leads/{id}/verify — xác thực OTP, cấp lead token (JWT 60 phút),
đẩy lead vào hàng đợi CRM (chỉ lead ĐÃ xác thực mới vào CRM).
POST /api/leads/{id}/resend — gửi lại OTP (cooldown 60s, tối đa 5 mã/ngày).
PATCH /api/leads/{id} — bổ sung hồ sơ (FE 21), cần Bearer lead token.
POST /api/contact — giữ nguyên (trang Contact).
POST /api/newsletter — đăng ký nhận tin ở footer (FE 18); double opt-in
ở BE 17 (R1-4).
"""

import datetime
import json
import sqlite3
import time

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import config, crm, db, email, otp, turnstile
from ..schemas import (
    ContactPayload,
    LeadPayload,
    LeadProfilePayload,
    NewsletterPayload,
    OtpVerifyPayload,
)

router = APIRouter()

# Rate limit tạo lead trong bộ nhớ (cùng mẫu giới hạn của guest chat):
# {ip: [thời điểm request trong 60s gần nhất]}.
_rate_buckets: dict[str, list[float]] = {}

# Tối đa 5 mã OTP/ngày/lead (kể cả mã đầu tiên).
MAX_RESENDS_PER_DAY = 5


def _error(status: int, code: str, message: str, details: dict | None = None):
    body: dict = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    bucket = [t for t in _rate_buckets.get(ip, []) if now - t < 60]
    if len(bucket) >= config.LEAD_RATE_LIMIT_PER_MINUTE:
        _rate_buckets[ip] = bucket
        return True
    bucket.append(now)
    _rate_buckets[ip] = bucket
    return False


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def _log_consents(conn, lead_id: int, contact: bool, marketing: bool) -> None:
    for purpose, granted in (("contact", contact), ("marketing", marketing)):
        conn.execute(
            "INSERT INTO lead_consents (lead_id, purpose, granted) VALUES (?, ?, ?)",
            (lead_id, purpose, 1 if granted else 0),
        )


def _issue_lead_token(lead_id: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "type": "lead",
            "lead_id": lead_id,
            "exp": now
            + datetime.timedelta(minutes=config.LEAD_TOKEN_EXPIRE_MINUTES),
        },
        config.JWT_SECRET,
        algorithm="HS256",
    )


def _check_lead_token(request: Request, lead_id: int) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    try:
        data = jwt.decode(auth[7:], config.JWT_SECRET, algorithms=["HS256"])
    except Exception:  # noqa: BLE001 - token sai/hết hạn đều từ chối
        return False
    return data.get("type") == "lead" and data.get("lead_id") == lead_id


def _lead_row(conn, lead_id: int):
    return conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()


@router.post("/api/leads", status_code=201)
def post_lead(
    payload: LeadPayload,
    request: Request,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    if _rate_limited(_client_ip(request)):
        return _error(429, "RATE_LIMITED", "Gửi quá nhanh, thử lại sau 1 phút.")
    turnstile_ok = turnstile.verify_turnstile_token(
        payload.turnstileToken, _client_ip(request)
    )
    if not turnstile_ok:
        return _error(400, "TURNSTILE_FAILED", "Xác minh chống spam không thành công.")
    regions_json = json.dumps(payload.regions or [], ensure_ascii=False)
    utm_json = json.dumps(payload.utm or {}, ensure_ascii=False)
    # Chống trùng: email chưa xác thực trong 10 phút thì dùng lại lead cũ
    # (cập nhật thông tin + gửi mã mới) thay vì tạo lead trùng.
    existing = conn.execute(
        "SELECT id FROM leads WHERE email = ? AND verified = 0 "
        "AND created_at > datetime('now', '-10 minutes') "
        "ORDER BY id DESC LIMIT 1",
        (payload.email,),
    ).fetchone()
    if existing:
        lead_id = existing["id"]
        conn.execute(
            "UPDATE leads SET name = ?, phone = ?, message = ?, company = ?, "
            "industry = ?, brand = ?, regions = ?, notes = ?, "
            "consent_contact = ?, consent_marketing = ?, language = ?, "
            "market = ?, source = ?, utm = ?, turnstile_checked = ? "
            "WHERE id = ?",
            (
                payload.name,
                payload.phone,
                payload.message or "",
                payload.company,
                payload.industry,
                payload.brand,
                regions_json,
                payload.notes,
                1 if payload.consentContact else 0,
                1 if payload.consentMarketing else 0,
                payload.language,
                payload.market,
                payload.source,
                utm_json,
                1 if turnstile_ok else 0,
                lead_id,
            ),
        )
    else:
        cur = conn.execute(
            "INSERT INTO leads (name, email, phone, message, company, "
            "industry, brand, regions, notes, consent_contact, "
            "consent_marketing, language, market, source, utm, "
            "turnstile_checked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?)",
            (
                payload.name,
                payload.email,
                payload.phone,
                payload.message or "",
                payload.company,
                payload.industry,
                payload.brand,
                regions_json,
                payload.notes,
                1 if payload.consentContact else 0,
                1 if payload.consentMarketing else 0,
                payload.language,
                payload.market,
                payload.source,
                utm_json,
                1 if turnstile_ok else 0,
            ),
        )
        lead_id = cur.lastrowid
    _log_consents(conn, lead_id, payload.consentContact, payload.consentMarketing)
    conn.commit()
    code = otp.create_otp(conn, lead_id)
    otp_sent = email.send_otp_email(payload.email, code, payload.language)
    return {"leadId": lead_id, "otpSent": otp_sent}


@router.post("/api/leads/{lead_id}/verify")
def verify_lead(
    lead_id: int,
    payload: OtpVerifyPayload,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    lead = _lead_row(conn, lead_id)
    if lead is None:
        return _error(404, "LEAD_NOT_FOUND", "Không tìm thấy lead này.")
    if lead["verified"]:
        return {"verified": True, "leadToken": _issue_lead_token(lead_id)}
    status, attempts_left = otp.verify_otp(conn, lead_id, payload.code)
    if status == "wrong":
        return _error(
            400,
            "OTP_WRONG",
            "Mã chưa đúng.",
            {"attemptsLeft": attempts_left},
        )
    if status == "expired":
        return _error(400, "OTP_EXPIRED", "Mã đã hết hạn. Gửi lại mã mới.")
    if status == "not_found":
        return _error(400, "OTP_NOT_FOUND", "Chưa có mã nào được gửi. Gửi lại mã mới.")
    if status == "locked":
        return _error(
            429, "OTP_LOCKED", "Nhập sai quá nhiều lần. Gửi lại mã mới."
        )
    conn.execute(
        "UPDATE leads SET verified = 1, verified_at = datetime('now') WHERE id = ?",
        (lead_id,),
    )
    conn.commit()
    # Chỉ lead đã xác thực mới vào CRM (BE 14).
    crm.queue_lead_sync(
        conn,
        lead_id,
        {
            "lead_id": lead_id,
            "name": lead["name"],
            "email": lead["email"],
            "phone": lead["phone"],
            "company": lead["company"],
            "industry": lead["industry"],
            "brand": lead["brand"],
            "regions": json.loads(lead["regions"] or "[]"),
            "notes": lead["notes"],
            "language": lead["language"],
            "market": lead["market"],
            "source": lead["source"],
            "utm": json.loads(lead["utm"] or "{}"),
        },
    )
    return {"verified": True, "leadToken": _issue_lead_token(lead_id)}


@router.post("/api/leads/{lead_id}/resend")
def resend_lead_otp(
    lead_id: int,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    lead = _lead_row(conn, lead_id)
    if lead is None:
        return _error(404, "LEAD_NOT_FOUND", "Không tìm thấy lead này.")
    if lead["verified"]:
        return _error(400, "LEAD_ALREADY_VERIFIED", "Email này đã được xác thực.")
    last = otp.last_otp_created_at(conn, lead_id)
    if last is not None:
        elapsed = (
            datetime.datetime.now(datetime.timezone.utc) - last
        ).total_seconds()
        if elapsed < config.OTP_RESEND_COOLDOWN_SECONDS:
            return _error(
                429,
                "RESEND_COOLDOWN",
                "Gửi lại quá nhanh, chờ thêm một lúc.",
                {
                    "retryAfter": int(
                        config.OTP_RESEND_COOLDOWN_SECONDS - elapsed
                    )
                },
            )
    if otp.otp_count_today(conn, lead_id) >= MAX_RESENDS_PER_DAY:
        return _error(429, "RESEND_LIMIT", "Đã gửi tối đa 5 mã hôm nay.")
    code = otp.create_otp(conn, lead_id)
    email.send_otp_email(lead["email"], code, lead["language"] or "vi")
    return {"sent": True}


@router.patch("/api/leads/{lead_id}")
def patch_lead(
    lead_id: int,
    payload: LeadProfilePayload,
    request: Request,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    if not _check_lead_token(request, lead_id):
        return _error(401, "LEAD_TOKEN_INVALID", "Token lead không hợp lệ.")
    lead = _lead_row(conn, lead_id)
    if lead is None:
        return _error(404, "LEAD_NOT_FOUND", "Không tìm thấy lead này.")
    updates: dict[str, object] = {}
    if payload.industry is not None:
        updates["industry"] = payload.industry
    if payload.brand is not None:
        updates["brand"] = payload.brand
    if payload.regions is not None:
        updates["regions"] = json.dumps(payload.regions, ensure_ascii=False)
    if payload.notes is not None:
        updates["notes"] = payload.notes
    if payload.consentMarketing is not None:
        updates["consent_marketing"] = 1 if payload.consentMarketing else 0
    if updates:
        assignments = ", ".join(f"{col} = ?" for col in updates)
        conn.execute(
            f"UPDATE leads SET {assignments} WHERE id = ?",
            (*updates.values(), lead_id),
        )
    if payload.consentMarketing is not None:
        conn.execute(
            "INSERT INTO lead_consents (lead_id, purpose, granted) "
            "VALUES (?, 'marketing', ?)",
            (lead_id, 1 if payload.consentMarketing else 0),
        )
    conn.commit()
    return {"ok": True}


@router.post("/api/contact", status_code=201)
def post_contact(payload: ContactPayload, conn: sqlite3.Connection = Depends(db.get_conn)):
    conn.execute(
        "INSERT INTO contact_messages (type, name, email, phone, message) VALUES (?, ?, ?, ?, ?)",
        (payload.type, payload.name, payload.email, payload.phone, payload.message),
    )
    conn.commit()
    return {"ok": True}


@router.post("/api/newsletter", status_code=202)
def post_newsletter(
    payload: NewsletterPayload, conn: sqlite3.Connection = Depends(db.get_conn)
):
    cur = conn.execute(
        "INSERT OR IGNORE INTO newsletter_subscribers (email, locale) VALUES (?, ?)",
        (payload.email, payload.locale),
    )
    conn.commit()
    if cur.rowcount > 0:
        email.send_newsletter_confirmation(payload.email, payload.locale)
    return {"subscribed": True}
