"""Gợi ý chiến dịch theo prompt (F02/F06) — khớp từ khóa xác định, không bịa.

Cách khớp: gấp dấu tiếng Việt + chữ thường rồi so token của prompt với tên
thành phố, khu vực và tên địa điểm trong SQLite. Địa điểm khớp xếp trước
(theo số token khớp, rồi theo reach), phần còn lại xếp theo reach giảm dần.
Không có địa điểm nào trong SQLite thì trả danh sách rỗng (không tự sinh).

Prompt được ghi vào prompt_logs để theo dõi, không dùng để suy ra số liệu.
"""

import re
import sqlite3
import unicodedata

from . import locale_names
from .schemas import (
    AdFormat,
    CampaignOverview,
    SuggestCity,
    SuggestedLocation,
)

_STOPWORDS = {
    "cho", "va", "voi", "tai", "o", "cua", "la", "mot", "cac", "de", "co",
    "the", "and", "for", "with", "in", "at", "a", "an", "to", "launch",
    "campaign", "brand", "chien", "dich", "quang", "cao",
}


def fold(text: str) -> str:
    """Gấp dấu tiếng Việt + chữ thường để so khớp không phân biệt dấu."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d")


def tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", fold(text)))
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def suggest(
    prompt: str, conn: sqlite3.Connection, page: int, page_size: int, locale: str = "vi"
) -> dict:
    conn.execute("INSERT INTO prompt_logs (prompt) VALUES (?)", (prompt,))
    conn.commit()
    prompt_tokens = tokens(prompt)

    rows = conn.execute(
        "SELECT name, area, city, reach FROM locations ORDER BY reach DESC"
    ).fetchall()
    locations: list[dict] = []
    for row in rows:
        haystack = tokens(f"{row['name']} {row['area']} {row['city']}")
        score = len(prompt_tokens & haystack)
        locations.append(
            {
                "name": row["name"],
                "area": row["area"],
                "city": row["city"],
                "reach": row["reach"],
                "score": score,
            }
        )
    # Khớp trước (điểm cao, rồi reach), còn lại theo reach.
    locations.sort(key=lambda loc: (-loc["score"], -(loc["reach"] or 0)))
    total = len(locations)
    start = (page - 1) * page_size
    page_locations = locations[start : start + page_size]

    # Thứ tự format theo đúng file CSV (thứ tự hiển thị trên Figma
    # Advertisers: Bumper Ads, Banner/Slide, Text Matching, Video Full
    # Screen) — không sắp theo metric_value.
    formats = [
        AdFormat(
            name=row["name"],
            metricLabel=row["metric_label"],
            metricValue=row["metric_value"],
            durationSeconds=row["duration_seconds"],
            description=row["description"],
        )
        for row in conn.execute(
            "SELECT name, metric_label, metric_value, duration_seconds, "
            "description FROM ad_formats"
        ).fetchall()
    ]

    # Chip thành phố: TẤT CẢ dòng trong city_stats (kể cả dòng chỉ có số
    # liệu tháng hoặc chưa có số liệu nào như Vũng Tàu, Huế — chip đó chỉ
    # hiện tên, không có số, đúng như Figma). Xếp theo độ khớp prompt rồi
    # theo monthly_engagements giảm dần, null cuối.
    city_rows = conn.execute(
        "SELECT city, reach, engagements, impressions_per_day, "
        "monthly_engagements FROM city_stats"
    ).fetchall()
    city_rows.sort(
        key=lambda r: (
            -len(prompt_tokens & tokens(r["city"])),
            (0, -r["monthly_engagements"])
            if r["monthly_engagements"] is not None
            else (1, 0),
            r["city"],
        )
    )
    cities = (
        [
            SuggestCity(
                name=locale_names.city_name(row["city"], locale),
                reach=row["reach"],
                engagements=row["engagements"],
                impressionsPerDay=row["impressions_per_day"],
                monthlyEngagements=row["monthly_engagements"],
            )
            for row in city_rows
        ]
        if city_rows
        else None
    )

    stats = conn.execute(
        "SELECT connections, provinces, chains, venues, engagement, off_peak "
        "FROM network_stats WHERE id = 1"
    ).fetchone()
    venues_total = conn.execute("SELECT COALESCE(SUM(count), 0) FROM venue_types").fetchone()[0]
    reach_total = sum((loc["reach"] or 0) for loc in locations) or None

    overview = CampaignOverview(
        locations=total,
        venues=int(venues_total),
        reach=reach_total,
        engagement=stats["engagement"] if stats else None,
        offPeak=stats["off_peak"] if stats else None,
    )
    return {
        "overview": overview,
        "locations": [
            SuggestedLocation(
                name=loc["name"],
                area=loc["area"],
                city=locale_names.city_name(loc["city"], locale),
                reach=loc["reach"],
            )
            for loc in page_locations
        ],
        "formats": formats,
        "cities": cities,
        "page": page,
        "pageSize": page_size,
        "total": total,
    }
