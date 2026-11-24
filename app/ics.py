"""File .ics cho email xác nhận đăng ký sự kiện (BE 15, EVT-02).

Tạo chuỗi VCALENDAR/VEVENT tối giản theo RFC 5545 từ ngày giờ ISO mà FE
gửi kèm (sự kiện nằm ở Strapi, backend không tự tra lịch). Nếu thiếu ngày
thì trả None — email gửi không kèm lịch.
"""

import datetime
import re

_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?"
    r"(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)


def _parse_iso(value: str) -> datetime.datetime | None:
    m = _ISO_RE.match(value.strip())
    if not m:
        return None
    year, month, day, hour, minute = (int(m.group(i)) for i in range(1, 6))
    second = int(m.group(6) or 0)
    tz = m.group(7)
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        offset = datetime.timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        tzinfo = datetime.timezone(sign * offset)
    else:
        tzinfo = datetime.timezone.utc
    try:
        return datetime.datetime(year, month, day, hour, minute, second, tzinfo=tzinfo)
    except ValueError:
        return None


def _fmt(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    *,
    uid: str,
    title: str,
    start: str,
    end: str | None,
    location: str | None = None,
    description: str | None = None,
) -> str | None:
    start_dt = _parse_iso(start)
    if start_dt is None:
        return None
    end_dt = _parse_iso(end) if end else None
    if end_dt is None or end_dt <= start_dt:
        end_dt = start_dt + datetime.timedelta(hours=1)
    now = _fmt(datetime.datetime.now(datetime.timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AWING//Event Registration//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}@awing.vn",
        f"DTSTAMP:{now}",
        f"DTSTART:{_fmt(start_dt)}",
        f"DTEND:{_fmt(end_dt)}",
        f"SUMMARY:{title}",
    ]
    if location:
        lines.append(f"LOCATION:{location}")
    if description:
        lines.append(f"DESCRIPTION:{description}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
