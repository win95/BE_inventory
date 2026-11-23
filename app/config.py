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
