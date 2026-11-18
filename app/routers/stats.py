"""Số liệu mạng lưới + phủ sóng + kênh SSE (F03, F04, F06).

Trả rỗng/null khi SQLite chưa có bản ghi — không tự sinh số liệu thay thế.
"""

import asyncio
import json
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .. import db, locale_names
from ..realtime import broadcaster
from ..schemas import (
    CityMonthlyStat,
    CoverageResponse,
    IndustryStat,
    LocationDirectoryEntry,
    NetworkStats,
    ProvinceCoverage,
    VenueTypeCount,
)

router = APIRouter()


@router.get("/api/network-stats", response_model=NetworkStats)
def get_network_stats(conn: sqlite3.Connection = Depends(db.get_conn)):
    row = conn.execute(
        "SELECT connections, provinces, chains, venues FROM network_stats WHERE id = 1"
    ).fetchone()
    if row is None:
        return NetworkStats()
    return NetworkStats(
        connections=row["connections"],
        provinces=row["provinces"],
        chains=row["chains"],
        venues=row["venues"],
    )


@router.get("/api/coverage", response_model=CoverageResponse)
def get_coverage(locale: str = "vi", conn: sqlite3.Connection = Depends(db.get_conn)):
    loc = locale_names.parse_locale(locale)
    provinces = [
        ProvinceCoverage(
            province=r["province"],
            displayName=locale_names.province_name(r["province"], loc),
            level=int(r["level"]),
            venues=r["venues"],
        )
        for r in conn.execute("SELECT province, level, venues FROM provinces ORDER BY province").fetchall()
    ]
    venue_types = [
        VenueTypeCount(type=r["type"], count=r["count"])
        for r in conn.execute("SELECT type, count FROM venue_types ORDER BY type").fetchall()
    ]
    # Thư mục địa điểm, số liệu ngành và số liệu tháng theo thành phố lấy từ
    # cùng SQLite; chưa có bảng nào thì các trường này vắng — Frontend tự ẩn
    # khối tương ứng.
    directory = None
    industry_stats = None
    cities = None
    try:
        directory_rows = conn.execute(
            "SELECT name, category, subtitle, locations, reach FROM directory ORDER BY name"
        ).fetchall()
        directory = [
            LocationDirectoryEntry(
                name=r["name"],
                category=r["category"],
                subtitle=r["subtitle"],
                locations=r["locations"],
                reach=r["reach"],
            )
            for r in directory_rows
        ]
    except sqlite3.OperationalError:
        pass
    try:
        industry_rows = conn.execute(
            "SELECT industry, engagement, reach, impressions FROM industry_stats "
            "ORDER BY impressions DESC"
        ).fetchall()
        industry_stats = [
            IndustryStat(
                industry=r["industry"],
                engagement=r["engagement"],
                reach=r["reach"],
                impressions=r["impressions"],
            )
            for r in industry_rows
        ]
    except sqlite3.OperationalError:
        pass
    try:
        city_rows = conn.execute(
            "SELECT city, monthly_reach, monthly_engagements FROM city_stats "
            "WHERE monthly_reach IS NOT NULL ORDER BY monthly_reach DESC"
        ).fetchall()
        cities = [
            CityMonthlyStat(
                city=locale_names.city_name(r["city"], loc),
                short=locale_names.city_short(r["city"], loc),
                monthlyReach=r["monthly_reach"],
                monthlyEngagements=r["monthly_engagements"],
            )
            for r in city_rows
        ]
    except sqlite3.OperationalError:
        pass
    return CoverageResponse(
        provinces=provinces,
        venueTypes=venue_types,
        directory=directory,
        industryStats=industry_stats,
        cities=cities,
    )


@router.get("/api/events/stats")
async def events_stats(request: Request):
    """SSE: full snapshot số liệu mỗi chu kỳ 30 giây + ngay khi kết nối."""
    queue = broadcaster.subscribe()
    broadcaster.broadcast_stats()

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # Nhịp giữ kết nối (comment SSE) khi không có gì mới.
                    yield ": heartbeat\n\n"
                    continue
                yield payload
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream")
