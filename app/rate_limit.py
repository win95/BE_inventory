"""Rate limit trong bộ nhớ cho các POST công khai.

Sau kiến trúc BFF, trình duyệt chỉ gọi Next.js; Next.js proxy sang backend
nên mọi request đều mang IP của FE — giới hạn theo IP ở backend thành giới
hạn chung cho toàn site. Vì vậy endpoint nào có danh tính (email trong
payload) thì giới hạn theo email đã chuẩn hóa; chỉ suggest (không danh
tính) mới giới hạn theo IP (lúc này là giới hạn chung qua proxy).
X-Forwarded-For (mục đầu tiên) được tin khi có — cho trường hợp backend
chạy sau reverse proxy/CDN thật.
"""

import time

from fastapi import Request

_buckets: dict[str, list[float]] = {}
_MAX_BUCKETS = 10_000


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def email_key(email: str) -> str:
    return "email:" + email.strip().lower()


def ip_key(request: Request) -> str:
    return "ip:" + client_ip(request)


def limited(key: str, limit: int, window_seconds: int = 60) -> bool:
    """True khi key đã vượt giới hạn trong cửa sổ; False và ghi nhận 1 lượt."""
    now = time.monotonic()
    # Dọn bucket hết hạn (lazy) để dict không tăng vô hạn theo thời gian.
    if len(_buckets) > _MAX_BUCKETS:
        cutoff = now - window_seconds
        for k in [k for k, v in _buckets.items() if not v or v[-1] < cutoff]:
            _buckets.pop(k, None)
    bucket = [t for t in _buckets.get(key, []) if now - t < window_seconds]
    if len(bucket) >= limit:
        _buckets[key] = bucket
        return True
    bucket.append(now)
    _buckets[key] = bucket
    return False
