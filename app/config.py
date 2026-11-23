"""Cấu hình backend từ biến môi trường (xem backend/.env.example)."""

import os

DATABASE_PATH = os.environ.get("DATABASE_PATH", "./awing.db")
PORT = int(os.environ.get("PORT", "8000"))

FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
    if origin.strip()
]

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

JWT_SECRET = os.environ.get("JWT_SECRET", "doi-secret-nay-khi-chay-that")
JWT_EXPIRE_HOURS = 24

STRAPI_WEBHOOK_SECRET = os.environ.get("STRAPI_WEBHOOK_SECRET", "")

# Vòng lặp realtime: chu kỳ đọc SQLite và đẩy full snapshot (giây).
# Trễ thông thường ≈ chu kỳ + vài giây xử lý, trong giới hạn 1 phút đã chốt.
REALTIME_INTERVAL_SECONDS = 30

# Tăng trưởng số liệu mẫu (tran 18/11/2026): mỗi chu kỳ realtime, backend cộng
# dồn số liệu vào SQLite rồi đẩy snapshot mới — số trên giao diện tăng dần.
# Đây là số tăng tổng hợp cho dữ liệu mẫu; khi có nguồn số liệu thật thì tắt
# (GROWTH_ENABLED=false) và thay bằng ingestion thật.
GROWTH_ENABLED = os.environ.get("GROWTH_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Số lượt kết nối cộng thêm mỗi chu kỳ (mặc định +100.000/30s ≈ +200.000/phút —
# đủ để ô 25.4M nhảy 0.1M mỗi chu kỳ ở định dạng 1 chữ số thập phân). Các số
# khác (reach, engagements, impressions/ngày, monthly) tăng theo cùng tỉ lệ %
# so với tổng hiện tại của chúng (xem app/growth.py).
GROWTH_CONNECTIONS_PER_CYCLE = int(
    os.environ.get("GROWTH_CONNECTIONS_PER_CYCLE", "13")
)

# Lead + OTP (BE 11-13, R1-2).
# Turnstile: secret key của Cloudflare. Để trống = chế độ giả lập (quyết
# định #4 chưa chốt): backend chấp nhận mọi token (kể cả null) và ghi log,
# KHÔNG gọi siteverify. Khi có secret thì token sai bị từ chối thật.
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", "")
# Email: "fake" (mặc định — chưa chốt nhà cung cấp SES/SendGrid, quyết định
# #4): chỉ ghi log nội dung email, không gửi thật. "ses"/"sendgrid" chưa
# được cài đặt — đặt tên khác fake thì gửi email trả lỗi rõ ràng.
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "fake").lower()
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@awing.vn")
OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN_SECONDS = int(
    os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", "60")
)
# Token lead cấp sau khi xác thực OTP (dùng cho PATCH /api/leads/{id}).
LEAD_TOKEN_EXPIRE_MINUTES = int(os.environ.get("LEAD_TOKEN_EXPIRE_MINUTES", "60"))
# Rate limit tạo lead: số request / phút / IP (chống spam form).
LEAD_RATE_LIMIT_PER_MINUTE = int(os.environ.get("LEAD_RATE_LIMIT_PER_MINUTE", "5"))
