"""Đồng bộ CRM (BE 14) — hàng đợi trong tiến trình FastAPI (theo kế hoạch
R1: không dùng BullMQ/Redis ở R1, thay bằng bảng crm_jobs + tác vụ nền,
cùng mẫu vòng lặp realtime đang chạy).

Hiện GIẢ LẬP (tran cho phép fake API/data, 23/11/2026 — chưa chốt CRM nào,
quyết định #1): "gửi" nghĩa là ghi log đầy đủ payload + thông báo sales,
rồi đánh sent. Khi chốt CRM thật, thay thân hàm _send_to_crm bằng client
thật (giữ nguyên tên hàm + chữ ký) — router và worker không đổi.

Worker: mỗi 30 giây lấy job pending tới hạn, gửi, thất bại thì retry theo
cấp số nhân (2^n phút), tối đa 5 lần rồi đánh failed để xem lại tay.
"""

import asyncio
import datetime
import json
import logging

from . import db

logger = logging.getLogger("awing.crm")

WORKER_INTERVAL_SECONDS = 30
MAX_ATTEMPTS = 5


def queue_lead_sync(conn, lead_id: int, payload: dict) -> int:
    """Đưa lead vào hàng đợi đẩy CRM. Trả job id."""
    cur = conn.execute(
        "INSERT INTO crm_jobs (lead_id, payload) VALUES (?, ?)",
        (lead_id, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    return cur.lastrowid


def _send_to_crm(payload: dict) -> None:
    # GIẢ LẬP: chưa có CRM thật. Ghi log = đã "đẩy" + báo sales.
    logger.info(
        "[FAKE CRM] lead #%s đã đẩy sang CRM: %s",
        payload.get("lead_id"),
        json.dumps(payload, ensure_ascii=False),
    )
    logger.info(
        "[FAKE CRM] SALES NOTIFY: lead mới #%s — %s (%s, %s)",
        payload.get("lead_id"),
        payload.get("name"),
        payload.get("email"),
        payload.get("company"),
    )


def _process_due_jobs() -> None:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM crm_jobs WHERE status = 'pending' "
            "AND next_retry_at <= datetime('now') ORDER BY id LIMIT 20"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"])
                _send_to_crm(payload)
                conn.execute(
                    "UPDATE crm_jobs SET status = 'sent', "
                    "updated_at = datetime('now') WHERE id = ?",
                    (row["id"],),
                )
            except Exception as exc:  # noqa: BLE001 - job lỗi thì retry
                attempts = row["attempts"] + 1
                if attempts >= MAX_ATTEMPTS:
                    status = "failed"
                    next_retry = row["next_retry_at"]
                else:
                    status = "pending"
                    retry_at = datetime.datetime.now(
                        datetime.timezone.utc
                    ) + datetime.timedelta(minutes=2**attempts)
                    # Lưu dạng SQLite datetime('now') (không múi giờ, không
                    # 'T') để so sánh chuỗi với datetime('now') ở WHERE
                    # còn đúng — ISO có 'T'/'+00:00' luôn lớn hơn chuỗi
                    # naive nên job retry sẽ không bao giờ tới hạn.
                    next_retry = retry_at.strftime("%Y-%m-%d %H:%M:%S")
                logger.warning(
                    "CRM job #%s lỗi (lần %s): %s", row["id"], attempts, exc
                )
                conn.execute(
                    "UPDATE crm_jobs SET status = ?, attempts = ?, "
                    "next_retry_at = ?, last_error = ?, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (status, attempts, next_retry, str(exc), row["id"]),
                )
            conn.commit()
    finally:
        conn.close()


class CrmWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def _loop(self) -> None:
        while self._running:
            try:
                _process_due_jobs()
            except Exception:  # noqa: BLE001 - kỳ lỗi thì bỏ qua, kỳ sau bù
                logger.exception("CRM worker: kỳ xử lý lỗi")
            await asyncio.sleep(WORKER_INTERVAL_SECONDS)

    def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


crm_worker = CrmWorker()
