"""SQLite — kho dữ liệu nghiệp vụ duy nhất của backend (Plan §6).

Chỉ chứa dữ liệu nghiệp vụ: số liệu mạng lưới, tỉnh/thành + mức phủ sóng,
địa điểm/venue, định dạng quảng cáo, prompt + kết quả gợi ý, lead, tin nhắn
liên hệ, người dùng cuối. Case study và nội dung home KHÔNG nằm ở đây —
đã chuyển sang Strapi (Postgres).

Không có dữ liệu mẫu trong code: bảng được tạo rỗng khi khởi động; muốn có
dữ liệu để xem/kiểm thử thì nhập vào SQLite (xem scripts/import_csv.py).
Kho nào rỗng thì API tương ứng trả rỗng, giao diện hiện trạng thái rỗng.
"""

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS network_stats (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    connections INTEGER,
    provinces INTEGER,
    chains INTEGER,
    venues INTEGER,
    engagement REAL,
    off_peak REAL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS provinces (
    -- Mức tương tác 1-5 theo đúng thang của trang mẫu Figma (bản đồ nhiệt
    -- Location Network): 1 Emerging, 2 Active, 3 Strong, 4 High, 5 Flagship.
    -- Tên tỉnh/thành dùng đúng nhãn trên bản đồ Figma (tiếng Anh, vd. Ha Noi,
    -- Ho Chi Minh) để Frontend khớp đúng từng ô trên lưới 10x15.
    province TEXT PRIMARY KEY,
    level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    venues INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS venue_types (
    type TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL,
    reach INTEGER,
    UNIQUE (name, city)
);

CREATE TABLE IF NOT EXISTS ad_formats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    metric_label TEXT NOT NULL DEFAULT 'Engagement',
    metric_value REAL,
    duration_seconds INTEGER,
    description TEXT
);

CREATE TABLE IF NOT EXISTS city_stats (
    city TEXT PRIMARY KEY,
    reach INTEGER,
    engagements INTEGER,
    impressions_per_day INTEGER,
    -- Trung bình tháng (triệu) cho biểu đồ Reach vs Engagement ở Location
    -- Network. Tên thành phố giữ tiếng Việt để khớp prompt gợi ý.
    monthly_reach REAL,
    monthly_engagements REAL
);

CREATE TABLE IF NOT EXISTS directory (
    -- Thư mục Location Network theo trang mẫu Figma: chuỗi/hệ thống, không
    -- phải từng điểm lẻ. reach tính bằng triệu.
    name TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    subtitle TEXT NOT NULL DEFAULT '',
    locations INTEGER NOT NULL DEFAULT 0,
    reach REAL
);

CREATE TABLE IF NOT EXISTS industry_stats (
    industry TEXT PRIMARY KEY,
    engagement REAL,
    reach INTEGER,
    -- Tổng impressions (nghìn) cho biểu đồ Engagement by Industry.
    impressions INTEGER
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    message TEXT,
    -- R1-2 (BE 11, LEAD-01): trường bắt buộc/tùy chọn + ẩn của lead form mới.
    company TEXT NOT NULL DEFAULT '',
    industry TEXT,
    brand TEXT,
    regions TEXT,  -- JSON: ["TP.HCM", "Hà Nội", ...]
    notes TEXT,
    consent_contact INTEGER NOT NULL DEFAULT 0,
    consent_marketing INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'vi',
    market TEXT NOT NULL DEFAULT 'vn',
    source TEXT,
    utm TEXT,  -- JSON: {"utm_source": ..., ...}
    turnstile_checked INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 0,
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- OTP xác thực email (BE 12): mã chỉ lưu dạng hash, không lưu mã gốc.
CREATE TABLE IF NOT EXISTS lead_otps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads (id),
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Nhật ký đồng ý theo mục đích (BE 11, Docs §6.2/§10): mỗi lần lead đồng
-- ý / rút lại đều ghi một dòng — pháp chế duyệt form trước phát hành.
CREATE TABLE IF NOT EXISTS lead_consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads (id),
    purpose TEXT NOT NULL,  -- 'contact' | 'marketing'
    granted INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Hàng đợi đẩy CRM (BE 14): tác vụ nền trong tiến trình FastAPI xử lý dần,
-- retry theo cấp số nhân, tối đa 5 lần rồi đánh failed để xem lại tay.
CREATE TABLE IF NOT EXISTS crm_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads (id),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload TEXT NOT NULL,  -- JSON: dữ liệu lead đẩy sang CRM
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Đăng ký nhận tin ở footer (FE 18). Double opt-in ở BE 17 (R1-4) — hiện
-- chỉ lưu email, trạng thái pending cho tới khi xác nhận.
CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    locale TEXT NOT NULL DEFAULT 'vi',
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed
    -- BE 17 double opt-in: token xác nhận chỉ lưu dạng hash.
    confirm_token_hash TEXT,
    confirm_token_created_at TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contact_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Đăng ký sự kiện (BE 15): sự kiện nằm ở Strapi, chỉ lưu đăng ký ở đây.
-- event_slug là slug Strapi; event_title/start/end do FE gửi kèm để làm
-- email xác nhận + file .ics (backend không tự gọi Strapi để lấy lịch).
CREATE TABLE IF NOT EXISTS event_registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_slug TEXT NOT NULL,
    event_title TEXT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    consent INTEGER NOT NULL DEFAULT 0,
    locale TEXT NOT NULL DEFAULT 'vi',
    start_date TEXT,
    end_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Nộp CV (BE 16): file lưu ở thư mục uploads (xem config.UPLOADS_DIR),
-- DB chỉ giữ đường dẫn + tên gốc. Quét virus: GIẢ LẬP ở R1 (ghi log),
-- ClamAV thật chờ hạ tầng.
CREATE TABLE IF NOT EXISTS job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_slug TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    cover_note TEXT,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    consent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Hàng đợi chung cho CRM/HR (BE 15-16): kind = 'event_registration' |
-- 'job_application'. Worker CRM xử lý cùng vòng lặp với crm_jobs (BE 14).
CREATE TABLE IF NOT EXISTS crm_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload TEXT NOT NULL,  -- JSON
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub TEXT UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    picture TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prompt_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'strapi',
    event TEXT NOT NULL,
    content_type TEXT,
    received_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload TEXT
);
"""


def connect() -> sqlite3.Connection:
    path = Path(config.DATABASE_PATH)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row[0] if row else ""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn: sqlite3.Connection) -> None:
    """Nâng cấp database đã có từ schema cũ lên schema mới (idempotent).

    Chỉ chạy khi bảng đã tồn tại với hình dạng cũ — database mới tạo thẳng
    schema mới nên các bước này không làm gì.
    """
    # provinces: level 'low'/'medium'/'high' (TEXT) -> 1-5 (INTEGER).
    if "'low'" in _table_sql(conn, "provinces"):
        conn.executescript(
            """
            CREATE TABLE provinces_new (
                province TEXT PRIMARY KEY,
                level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
                venues INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO provinces_new (province, level, venues)
            SELECT province,
                CASE level WHEN 'low' THEN 1 WHEN 'medium' THEN 3
                          WHEN 'high' THEN 5 ELSE 3 END,
                venues FROM provinces;
            DROP TABLE provinces;
            ALTER TABLE provinces_new RENAME TO provinces;
            """
        )
    # directory: từng điểm lẻ (name, category, venues) -> chuỗi/hệ thống
    # (name, category, subtitle, locations, reach). Dữ liệu cũ không map
    # được sang hình dạng mới nên bảng dựng lại rỗng — nhập lại từ CSV.
    if "subtitle" not in _columns(conn, "directory"):
        conn.executescript(
            """
            DROP TABLE directory;
            CREATE TABLE directory (
                name TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                subtitle TEXT NOT NULL DEFAULT '',
                locations INTEGER NOT NULL DEFAULT 0,
                reach REAL
            );
            """
        )
    # Thêm cột mới vào hai bảng còn lại (ADD COLUMN an toàn, không mất dữ liệu).
    if "impressions" not in _columns(conn, "industry_stats"):
        conn.execute("ALTER TABLE industry_stats ADD COLUMN impressions INTEGER")
    for col in ("monthly_reach", "monthly_engagements"):
        if col not in _columns(conn, "city_stats"):
            conn.execute(f"ALTER TABLE city_stats ADD COLUMN {col} REAL")
    # ad_formats: mô tả hiển thị trên thẻ format (Figma Advertisers).
    if "description" not in _columns(conn, "ad_formats"):
        conn.execute("ALTER TABLE ad_formats ADD COLUMN description TEXT")
    # leads: cột mới của lead form R1-2 (BE 11). Database cũ (message bắt
    # buộc) vẫn giữ message cũ; cột company có DEFAULT '' nên không vỡ.
    lead_cols = {
        "company": "TEXT NOT NULL DEFAULT ''",
        "industry": "TEXT",
        "brand": "TEXT",
        "regions": "TEXT",
        "notes": "TEXT",
        "consent_contact": "INTEGER NOT NULL DEFAULT 0",
        "consent_marketing": "INTEGER NOT NULL DEFAULT 0",
        "language": "TEXT NOT NULL DEFAULT 'vi'",
        "market": "TEXT NOT NULL DEFAULT 'vn'",
        "source": "TEXT",
        "utm": "TEXT",
        "turnstile_checked": "INTEGER NOT NULL DEFAULT 0",
        "verified": "INTEGER NOT NULL DEFAULT 0",
        "verified_at": "TEXT",
    }
    existing = _columns(conn, "leads")
    for col, ddl in lead_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {ddl}")
    if "message" in existing:
        # message ở DB cũ là NOT NULL không DEFAULT — router mới luôn INSERT
        # kèm message ("" khi không có) nên không vỡ ràng buộc này; DB mới
        # tạo thẳng message NULL được.
        pass
    # newsletter_subscribers: double opt-in (BE 17) — token xác nhận chỉ
    # lưu dạng hash, kèm thời điểm tạo token để hết hạn sau 7 ngày.
    sub_cols = {
        "confirm_token_hash": "TEXT",
        "confirm_token_created_at": "TEXT",
        "confirmed_at": "TEXT",
    }
    existing_sub = _columns(conn, "newsletter_subscribers")
    for col, ddl in sub_cols.items():
        if col not in existing_sub:
            conn.execute(
                f"ALTER TABLE newsletter_subscribers ADD COLUMN {col} {ddl}"
            )


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def get_conn():
    """FastAPI dependency: một connection SQLite cho mỗi request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
