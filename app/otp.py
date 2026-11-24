"""OTP xác thực email (BE 12, LEAD-01).

Mã 6 số, hiệu lực OTP_TTL_MINUTES (mặc định 10 phút), tối đa
OTP_MAX_ATTEMPTS lần thử sai (mặc định 5). Mã chỉ lưu dạng SHA-256 (muối
bằng JWT_SECRET + lead_id) — không bao giờ lưu mã gốc, kể cả trong log.
Gửi lại mã sẽ vô hiệu mã cũ chưa dùng.
"""

import datetime
import hashlib
import secrets

from . import config


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat()


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(lead_id: int, code: str) -> str:
    material = f"{lead_id}:{code}:{config.JWT_SECRET}".encode()
    return hashlib.sha256(material).hexdigest()


def create_otp(conn, lead_id: int) -> str:
    """Tạo mã mới, vô hiệu mã cũ chưa dùng của lead này. Trả mã gốc (chỉ
    caller này được thấy — ghi log email giả lập xong thì quên)."""
    code = generate_code()
    expires = _now() + datetime.timedelta(minutes=config.OTP_TTL_MINUTES)
    conn.execute(
        "UPDATE lead_otps SET used = 1 WHERE lead_id = ? AND used = 0",
        (lead_id,),
    )
    conn.execute(
        "INSERT INTO lead_otps (lead_id, code_hash, expires_at) VALUES (?, ?, ?)",
        (lead_id, hash_code(lead_id, code), _iso(expires)),
    )
    conn.commit()
    return code


def verify_otp(conn, lead_id: int, code: str) -> tuple[str, int]:
    """Kiểm tra mã. Trả (trạng_thái, số_lần_thử_còn_lại).
    Trạng thái: 'ok' | 'wrong' | 'expired' | 'not_found' | 'locked'."""
    row = conn.execute(
        "SELECT * FROM lead_otps WHERE lead_id = ? AND used = 0 "
        "ORDER BY id DESC LIMIT 1",
        (lead_id,),
    ).fetchone()
    if row is None:
        return "not_found", 0
    if _now() > datetime.datetime.fromisoformat(row["expires_at"]):
        return "expired", 0
    if row["attempts"] >= config.OTP_MAX_ATTEMPTS:
        return "locked", 0
    attempts = row["attempts"] + 1
    conn.execute(
        "UPDATE lead_otps SET attempts = ? WHERE id = ?", (attempts, row["id"])
    )
    conn.commit()
    if hash_code(lead_id, code) == row["code_hash"]:
        conn.execute("UPDATE lead_otps SET used = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        return "ok", 0
    return "wrong", max(0, config.OTP_MAX_ATTEMPTS - attempts)


def last_otp_created_at(conn, lead_id: int) -> datetime.datetime | None:
    row = conn.execute(
        "SELECT created_at FROM lead_otps WHERE lead_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (lead_id,),
    ).fetchone()
    if row is None:
        return None
    # SQLite datetime('now') không có múi giờ — coi như UTC để trừ được
    # với datetime.now(timezone.utc) ở router (trừ naive - aware lỗi).
    return datetime.datetime.fromisoformat(row["created_at"]).replace(
        tzinfo=datetime.timezone.utc
    )


def otp_count_today(conn, lead_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM lead_otps WHERE lead_id = ? "
        "AND date(created_at) = date('now')",
        (lead_id,),
    ).fetchone()
    return row["n"] if row else 0
