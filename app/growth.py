"""Tăng dần số liệu theo thời gian thực (yêu cầu của tran, 18/11/2026).

Mỗi chu kỳ realtime (30 giây), backend cộng dồn một lượng nhỏ vào các số
liệu đang có trong SQLite rồi đẩy snapshot mới qua SSE — các ô số trên giao
diện (Lượt kết nối, Total Reach, Potential Engagements, Impressions/ngày,
biểu đồ theo thành phố) tăng dần thay vì đứng yên.

Cơ chế:
- Chỉ có MỘT con số cấu hình: số lượt kết nối cộng thêm mỗi chu kỳ
  (GROWTH_CONNECTIONS_PER_CYCLE, mặc định 13). Các số khác tăng theo
  cùng tỉ lệ % so với tổng hiện tại của chúng — tỉ lệ giữa các số (reach
  ≈ 95% connections, engagements ≈ 65%...) được giữ nguyên theo thời gian,
  không lệch nhau.
- Tăng trưởng chia đều theo tỉ trọng từng thành phố: thành phố nào đang
  chiếm bao nhiêu % của tổng thì nhận bấy nhiêu % của lượng tăng. Nhờ vậy
  thứ hạng thành phố không đổi chỉ vì tăng trưởng.
- Cộng dồn VÀO DATABASE (không phải tính theo thời gian): restart backend
  thì số tiếp tục tăng từ mức đã đạt, không quay về số gốc.
- Cột nào đang NULL thì giữ NULL (Vũng Tàu, Huế chưa có số liệu thì không
  tự sinh số) — đúng nguyên tắc "không có dữ liệu mẫu trong code". Database
  rỗng thì không làm gì.
- Đây là số tăng TỔNG HỢP cho giai đoạn dữ liệu mẫu. Khi có nguồn số liệu
  thật (feed từ nền tảng Wi-Fi) thì tắt bằng GROWTH_ENABLED=false và thay
  bằng ingestion thật; lúc đó vòng lặp chỉ đọc + đẩy như trước.
"""

import logging
import sqlite3

from . import config

logger = logging.getLogger("awing.growth")

# (tên cột city_stats, đơn vị) — monthly_* tính bằng triệu, còn lại là số đếm.
_CITY_COLUMNS = (
    ("reach", False),
    ("engagements", False),
    ("impressions_per_day", False),
    ("monthly_reach", True),
    ("monthly_engagements", True),
)


def apply_growth(conn: sqlite3.Connection) -> dict:
    """Cộng dồn một chu kỳ tăng trưởng vào SQLite, trong một transaction.

    Trả về dict {tên số: lượng đã cộng} để ghi log; trả {} khi tắt tăng
    trưởng hoặc không có dữ liệu để tăng. Lỗi thì rollback (caller ghi log)
    và không làm hỏng chu kỳ broadcast sau đó.
    """
    if not config.GROWTH_ENABLED:
        return {}
    row = conn.execute(
        "SELECT connections FROM network_stats WHERE id = 1"
    ).fetchone()
    if row is None or row["connections"] is None or row["connections"] <= 0:
        return {}
    connections = row["connections"]
    conn_inc = config.GROWTH_CONNECTIONS_PER_CYCLE
    if conn_inc <= 0:
        return {}

    cities = conn.execute(
        "SELECT city, reach, engagements, impressions_per_day, "
        "monthly_reach, monthly_engagements FROM city_stats"
    ).fetchall()
    # Tổng hiện tại của từng số (chỉ tính dòng khác NULL) — dùng để chia tỉ lệ.
    totals = {}
    for col, _ in _CITY_COLUMNS:
        total = sum(r[col] for r in cities if r[col] is not None)
        totals[col] = total

    grown: dict[str, float | int] = {"connections": conn_inc}
    try:
        conn.execute(
            "UPDATE network_stats SET connections = connections + ?, "
            "updated_at = datetime('now') WHERE id = 1",
            (conn_inc,),
        )
        for city_row in cities:
            updates: dict[str, float | int] = {}
            for col, in_millions in _CITY_COLUMNS:
                value = city_row[col]
                total = totals[col]
                if value is None or not total:
                    continue
                # Lượng tăng của cả nước cho số này, tính theo cùng tỉ lệ %
                # như connections: total_inc = conn_inc * total / connections.
                # total đã ở đúng đơn vị của cột (triệu với monthly_*), nên
                # kết quả cũng ở đúng đơn vị đó — không đổi đơn vị thêm.
                total_inc = conn_inc * total / connections
                share_inc = total_inc * value / total
                if share_inc:
                    updates[col] = round(share_inc) if not in_millions else share_inc
            if updates:
                assignments = ", ".join(f"{col} = {col} + ?" for col in updates)
                conn.execute(
                    f"UPDATE city_stats SET {assignments} WHERE city = ?",
                    (*updates.values(), city_row["city"]),
                )
                for col, inc in updates.items():
                    grown[col] = grown.get(col, 0) + inc  # type: ignore[operator]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return grown
