"""Xác minh Turnstile (BE 11, LEAD-01).

Chưa có TURNSTILE_SECRET (quyết định #4 chưa chốt) thì chạy chế độ giả
lập: chấp nhận mọi token (kể cả null) và ghi log — form không bị chặn.
Khi có secret thì gọi siteverify thật của Cloudflare; token sai/mất thì
từ chối.
"""

import json
import logging
import urllib.request

from . import config

logger = logging.getLogger("awing.turnstile")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile_token(token: str | None, remote_ip: str | None = None) -> bool:
    if not config.TURNSTILE_SECRET:
        logger.info(
            "Turnstile: chưa cấu hình secret — chế độ giả lập, chấp nhận "
            "(token có: %s)",
            bool(token),
        )
        return True
    if not token:
        return False
    body = json.dumps(
        {
            "secret": config.TURNSTILE_SECRET,
            "response": token,
            **({"remoteip": remote_ip} if remote_ip else {}),
        }
    ).encode()
    try:
        req = urllib.request.Request(
            SITEVERIFY_URL,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            result = json.loads(res.read().decode())
        return bool(result.get("success"))
    except Exception:  # noqa: BLE001 - lỗi mạng khi xác minh = từ chối
        logger.exception("Turnstile: siteverify lỗi")
        return False
