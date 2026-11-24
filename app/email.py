"""Gửi email (BE 13) — hiện GIẢ LẬP theo quyết định fake API/data của tran
(23/11/2026, cho R1): chưa chốt nhà cung cấp (SES/SendGrid — quyết định
#4), nên hàm chỉ ghi log đầy đủ nội dung email và trả True, KHÔNG gửi thật.
Khi chốt provider, thay thân hàm _send bằng client thật (giữ nguyên tên
hàm + chữ ký) — Frontend và router không đổi.

KHÔNG BAO GIỜ ghi mã OTP vào log ở nơi khác ngoài hàm này (log giả lập
cần mã để kiểm thử end-to-end khi chưa có email thật — xem ghi chú trong
_send: mã chỉ xuất hiện trong log fake, provider thật không log body).
"""

import logging

from . import config

logger = logging.getLogger("awing.email")


def _send(to: str, subject: str, body: str) -> bool:
    if config.EMAIL_PROVIDER == "fake":
        logger.info(
            "[FAKE EMAIL] from=%s to=%s subject=%s\n%s",
            config.EMAIL_FROM,
            to,
            subject,
            body,
        )
        return True
    logger.error(
        "Email provider '%s' chưa được cài đặt — xem BE 13 (quyết định #4)",
        config.EMAIL_PROVIDER,
    )
    return False


def send_otp_email(to: str, code: str, locale: str = "vi") -> bool:
    if locale == "en":
        subject = "Your AWING verification code"
        body = (
            f"Your AWING verification code is: {code}\n"
            f"It expires in {config.OTP_TTL_MINUTES} minutes. "
            "If you didn't request this, ignore this email."
        )
    else:
        subject = "Mã xác thực AWING của bạn"
        body = (
            f"Mã xác thực AWING của bạn là: {code}\n"
            f"Mã có hiệu lực {config.OTP_TTL_MINUTES} phút. "
            "Nếu bạn không yêu cầu mã này, cứ bỏ qua email."
        )
    return _send(to, subject, body)


def send_newsletter_confirm(to: str, token: str, locale: str = "vi") -> bool:
    from . import config as _config

    link = (
        f"{_config.FRONTEND_URL}/{locale}/newsletter/confirm?token={token}"
    )
    if locale == "en":
        subject = "Confirm your AWING subscription"
        body = (
            "Thank you for subscribing to AWING updates.\n"
            f"Please confirm your email by opening this link (valid 7 days):\n{link}\n"
            "If you didn't request this, ignore this email."
        )
    else:
        subject = "Xác nhận đăng ký nhận tin AWING"
        body = (
            "Cảm ơn bạn đã đăng ký nhận tin từ AWING.\n"
            f"Bấm vào liên kết sau để xác nhận email (hiệu lực 7 ngày):\n{link}\n"
            "Nếu bạn không yêu cầu, cứ bỏ qua email này."
        )
    return _send(to, subject, body)


def send_event_confirmation(
    to: str,
    *,
    event_title: str,
    name: str,
    start: str | None,
    end: str | None,
    ics: str | None,
    locale: str = "vi",
) -> bool:
    if locale == "en":
        subject = f"You're registered: {event_title}"
        body = (
            f"Hi {name},\n\n"
            f"You're registered for “{event_title}”."
            + (f"\nTime: {start}" + (f" – {end}" if end else "") if start else "")
            + "\n\nSee you there — the AWING team."
        )
    else:
        subject = f"Bạn đã đăng ký: {event_title}"
        body = (
            f"Chào {name},\n\n"
            f"Bạn đã đăng ký tham gia “{event_title}”."
            + (f"\nThời gian: {start}" + (f" – {end}" if end else "") if start else "")
            + "\n\nHẹn gặp bạn — đội ngũ AWING."
        )
    if ics:
        # Chế độ giả lập: file .ics đi kèm nội dung log (provider thật sẽ
        # gửi dưới dạng attachment — xem ghi chú trong _send).
        body += "\n\n--- Lịch (.ics) ---\n" + ics
    return _send(to, subject, body)


def send_job_application_notice(
    to: str, *, job_slug: str, name: str, locale: str = "vi"
) -> bool:
    if locale == "en":
        subject = "We received your application"
        body = (
            f"Hi {name},\n\n"
            f"We received your application for the role “{job_slug}”. "
            "Our HR team will review it and get back to you.\n\n— AWING HR"
        )
    else:
        subject = "AWING đã nhận hồ sơ của bạn"
        body = (
            f"Chào {name},\n\n"
            f"AWING đã nhận hồ sơ ứng tuyển vị trí “{job_slug}” của bạn. "
            "Đội ngũ nhân sự sẽ xem xét và liên hệ lại.\n\n— HR AWING"
        )
    return _send(to, subject, body)
