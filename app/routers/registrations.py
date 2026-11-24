"""Đăng ký sự kiện (BE 15, EVT-02) + nộp CV (BE 16, JOB-02) + xác nhận
newsletter (BE 17, double opt-in).

Chế độ GIẢ LẬP (tran cho phép fake API/data, 23/11/2026): email xác nhận
chỉ ghi log; đẩy CRM/HR qua hàng đợi crm_outbox (worker xử lý cùng vòng
lặp CRM, BE 14); quét virus CV chỉ ghi log (chưa có ClamAV — xem ghi chú
trong _fake_virus_scan).
"""

import hashlib
import logging
import re
import secrets
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import config, crm, db, email, ics
from ..schemas import EventRegistrationPayload

logger = logging.getLogger("awing.registrations")
router = APIRouter()

MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB (JOB-02)
_CV_TYPES = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
}
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _error(status: int, code: str, message: str, details: dict | None = None):
    body: dict = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def _fake_virus_scan(path: Path, size: int) -> None:
    # GIẢ LẬP R1: chưa có ClamAV trong môi trường này. Khi có ClamAV (daemon
    # hoặc `clamdscan`), thay thân hàm bằng lệnh quét thật và raise khi
    # phát hiện virus — router và DB không đổi.
    logger.info("[FAKE VIRUS SCAN] %s (%s bytes): bỏ qua, chưa có ClamAV", path.name, size)


@router.post("/api/events/{event_slug}/register", status_code=201)
def register_event(
    event_slug: str,
    payload: EventRegistrationPayload,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    if not _SLUG_RE.match(event_slug):
        return _error(400, "EVENT_NOT_FOUND", "Không tìm thấy sự kiện này.")
    if not payload.consent:
        return _error(400, "CONSENT_REQUIRED", "Cần đồng ý xử lý dữ liệu để đăng ký.")
    # Chống trùng: cùng email + sự kiện trong 24h thì trả lại đăng ký cũ.
    existing = conn.execute(
        "SELECT id FROM event_registrations WHERE event_slug = ? AND email = ? "
        "AND created_at > datetime('now', '-1 day') ORDER BY id DESC LIMIT 1",
        (event_slug, payload.email),
    ).fetchone()
    if existing:
        return {"registrationId": existing["id"], "registered": True, "duplicate": True}
    cur = conn.execute(
        "INSERT INTO event_registrations (event_slug, event_title, name, email, "
        "phone, consent, locale, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_slug,
            payload.eventTitle,
            payload.name,
            payload.email,
            payload.phone,
            1,
            payload.locale,
            payload.startDate,
            payload.endDate,
        ),
    )
    reg_id = cur.lastrowid
    conn.commit()
    title = payload.eventTitle or event_slug
    ics_text = (
        ics.build_ics(
            uid=f"event-{reg_id}",
            title=title,
            start=payload.startDate,
            end=payload.endDate,
        )
        if payload.startDate
        else None
    )
    email.send_event_confirmation(
        payload.email,
        event_title=title,
        name=payload.name,
        start=payload.startDate,
        end=payload.endDate,
        ics=ics_text,
        locale=payload.locale,
    )
    crm.queue_outbox(
        conn,
        "event_registration",
        reg_id,
        {
            "registration_id": reg_id,
            "event_slug": event_slug,
            "event_title": title,
            "name": payload.name,
            "email": payload.email,
            "phone": payload.phone,
            "locale": payload.locale,
        },
    )
    return {"registrationId": reg_id, "registered": True, "duplicate": False}


@router.post("/api/jobs/{job_slug}/apply", status_code=201)
async def apply_job(
    job_slug: str,
    request: Request,
    name: str = Form(min_length=1, max_length=200),
    email_address: str = Form(min_length=1, max_length=200, alias="email"),
    phone: str | None = Form(default=None, max_length=20),
    cover_note: str | None = Form(default=None, max_length=5000, alias="coverNote"),
    consent: str = Form(default="false"),
    locale: str = Form(default="vi"),
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    if not _SLUG_RE.match(job_slug):
        return _error(400, "JOB_NOT_FOUND", "Không tìm thấy vị trí này.")
    if consent.lower() not in ("true", "1", "yes"):
        return _error(400, "CONSENT_REQUIRED", "Cần đồng ý xử lý dữ liệu để nộp hồ sơ.")
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email_address):
        return _error(422, "INVALID_EMAIL", "Email không hợp lệ.")
    original = file.filename or ""
    ext = Path(original).suffix.lower()
    if ext not in _CV_TYPES:
        return _error(
            400, "FILE_TYPE_INVALID", "Chỉ nhận file PDF hoặc DOCX (≤ 5 MB)."
        )
    content = await file.read()
    if len(content) > MAX_CV_BYTES:
        return _error(400, "FILE_TOO_LARGE", "File vượt quá 5 MB.")
    if not content.startswith(_CV_TYPES[ext]):
        return _error(
            400, "FILE_TYPE_INVALID", "Nội dung file không khớp định dạng đã chọn."
        )
    upload_dir = Path(config.UPLOADS_DIR) / "cv"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(content)
    _fake_virus_scan(stored_path, len(content))
    cur = conn.execute(
        "INSERT INTO job_applications (job_slug, name, email, phone, cover_note, "
        "file_path, file_name, file_size, consent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_slug,
            name,
            email_address,
            phone,
            cover_note,
            str(stored_path),
            original,
            len(content),
            1,
        ),
    )
    app_id = cur.lastrowid
    conn.commit()
    email.send_job_application_notice(
        email_address, job_slug=job_slug, name=name, locale=locale
    )
    crm.queue_outbox(
        conn,
        "job_application",
        app_id,
        {
            "application_id": app_id,
            "job_slug": job_slug,
            "name": name,
            "email": email_address,
            "phone": phone,
            "file_name": original,
            "file_size": len(content),
        },
    )
    return {"applicationId": app_id, "received": True}


@router.get("/api/newsletter/confirm")
def confirm_newsletter(
    token: str,
    conn: sqlite3.Connection = Depends(db.get_conn),
):
    """Xác nhận double opt-in (BE 17): token trong email → confirmed."""
    if not token:
        return _error(400, "TOKEN_INVALID", "Liên kết xác nhận không hợp lệ.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute(
        "SELECT * FROM newsletter_subscribers WHERE confirm_token_hash = ?",
        (token_hash,),
    ).fetchone()
    if row is None:
        return _error(400, "TOKEN_INVALID", "Liên kết xác nhận không hợp lệ.")
    if row["status"] == "confirmed":
        return {"confirmed": True, "email": row["email"]}
    created = row["confirm_token_created_at"]
    if created is not None:
        from datetime import datetime, timedelta, timezone

        try:
            created_dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            created_dt = None
        if created_dt is not None and datetime.now(timezone.utc) - created_dt > timedelta(
            days=config.NEWSLETTER_CONFIRM_TTL_DAYS
        ):
            return _error(400, "TOKEN_EXPIRED", "Liên kết đã hết hạn. Đăng ký lại để nhận link mới.")
    conn.execute(
        "UPDATE newsletter_subscribers SET status = 'confirmed', "
        "confirmed_at = datetime('now'), confirm_token_hash = NULL WHERE id = ?",
        (row["id"],),
    )
    conn.commit()
    return {"confirmed": True, "email": row["email"]}
