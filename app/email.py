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


def send_newsletter_confirmation(to: str, locale: str = "vi") -> bool:
    if locale == "en":
        subject = "You're on the AWING list"
        body = (
            "Thank you for subscribing to AWING updates. "
            "Double opt-in (BE 17) lands in R1-4 — for now your email is "
            "saved as pending."
        )
    else:
        subject = "Bạn đã đăng ký nhận tin AWING"
        body = (
            "Cảm ơn bạn đã đăng ký nhận tin từ AWING. "
            "Xác nhận double opt-in (BE 17) sẽ có ở R1-4 — hiện email của "
            "bạn được lưu ở trạng thái chờ xác nhận."
        )
    return _send(to, subject, body)
