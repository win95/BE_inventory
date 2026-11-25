"""Cấu hình backend từ biến môi trường (xem backend/.env.example)."""

import logging
import os

logger = logging.getLogger("awing.backend.config")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "./awing.db")
PORT = int(os.environ.get("PORT", "8000"))

FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
    if origin.strip()
]

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Secret ký JWT. Không có env thì FAIL NGAY lúc khởi động (không dùng secret
# mặc định mà ai cũng đọc được trong repo). Giá trị mặc định trong
# .env.example chỉ để chạy thử local — dùng nó thì backend vẫn chạy nhưng
# ghi cảnh báo lớn ở log.
_DEFAULT_JWT_SECRET = "doi-secret-nay-khi-chay-that"
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET chưa cấu hình — đặt giá trị ngẫu nhiên trong .env (xem .env.example)."
    )
if JWT_SECRET == _DEFAULT_JWT_SECRET:
    logger.warning(
        "JWT_SECRET đang dùng giá trị mặc định trong .env.example — "
        "đổi thành giá trị ngẫu nhiên trước khi chạy thật."
    )
JWT_EXPIRE_HOURS = 24

STRAPI_WEBHOOK_SECRET = os.environ.get("STRAPI_WEBHOOK_SECRET", "")

# BE 8 — cầu revalidate sang Next.js: FastAPI gọi POST /api/revalidate của
# Frontend với secret chung để xóa tag `strapi:<collection>` khi Strapi
# publish/unpublish/update. Để trống REVALIDATE_SECRET thì bỏ qua bước này
# (chỉ còn SSE content-updated); FRONTEND_URL là origin của Next.js.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
REVALIDATE_SECRET = os.environ.get("REVALIDATE_SECRET", "")

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
# Số lượt kết nối cộng thêm mỗi chu kỳ (mặc định +13/30s). Các số
# khác (reach, engagements, impressions/ngày, monthly) tăng theo cùng tỉ lệ %
# so với tổng hiện tại của chúng (xem app/growth.py). (.env.example đặt
# 100000 để demo nhảy số rõ — giá trị đó chỉ có khi đặt env.)
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
# Rate limit tạo lead: số request / phút / email (chống spam form).
# Sau kiến trúc BFF mọi request đều qua proxy Next.js nên giới hạn theo IP
# thành giới hạn chung toàn site — giới hạn theo email trong payload.
LEAD_RATE_LIMIT_PER_MINUTE = int(os.environ.get("LEAD_RATE_LIMIT_PER_MINUTE", "5"))
# Rate limit các POST công khai còn lại (theo email; suggest theo IP).
CONTACT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CONTACT_RATE_LIMIT_PER_MINUTE", "5"))
NEWSLETTER_RATE_LIMIT_PER_MINUTE = int(
    os.environ.get("NEWSLETTER_RATE_LIMIT_PER_MINUTE", "5")
)
EVENT_REGISTER_RATE_LIMIT_PER_MINUTE = int(
    os.environ.get("EVENT_REGISTER_RATE_LIMIT_PER_MINUTE", "5")
)
CV_APPLY_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CV_APPLY_RATE_LIMIT_PER_MINUTE", "3"))
SUGGEST_RATE_LIMIT_PER_MINUTE = int(os.environ.get("SUGGEST_RATE_LIMIT_PER_MINUTE", "30"))

# BE 18-20 — tìm kiếm trên FastAPI (không Meilisearch, theo kiến trúc đã
# chốt 23/11): URL Strapi để đọc nội dung công khai làm chỉ mục tìm kiếm.
# Để trống thì /api/search chỉ dùng chỉ mục dự phòng (6 sản phẩm +
# 26 solution, dữ liệu tĩnh trong code).
STRAPI_URL = os.environ.get("STRAPI_URL", "").rstrip("/")
# Thời gian cache chỉ mục tìm kiếm trong bộ nhớ (giây).
SEARCH_CACHE_TTL_SECONDS = int(os.environ.get("SEARCH_CACHE_TTL_SECONDS", "300"))
UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "./uploads")
# Double opt-in newsletter (BE 17): link xác nhận hết hạn sau số ngày này.
NEWSLETTER_CONFIRM_TTL_DAYS = int(
    os.environ.get("NEWSLETTER_CONFIRM_TTL_DAYS", "7")
)
