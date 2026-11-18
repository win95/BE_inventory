"""Schema Pydantic — nguồn sự thật cho kiểu dữ liệu (Plan §6).

FastAPI tự sinh OpenAPI từ các schema này; Frontend sinh kiểu TypeScript
từ OpenAPI đó. Mọi con số đều nullable: chưa có dữ liệu thì trả null để
Frontend hiện "—" / trạng thái rỗng, không tự điền số thay thế.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class NetworkStats(BaseModel):
    connections: Optional[int] = None
    provinces: Optional[int] = None
    chains: Optional[int] = None
    venues: Optional[int] = None


class ProvinceCoverage(BaseModel):
    province: str
    # Mức tương tác 1-5 (1 Emerging, 2 Active, 3 Strong, 4 High, 5 Flagship).
    level: int
    venues: int


class VenueTypeCount(BaseModel):
    type: str
    count: int


class LocationDirectoryEntry(BaseModel):
    name: str
    category: str
    # Ghi chú dưới tên chuỗi, vd. "63 provinces", "24 cities", "Ha Noi".
    subtitle: str = ""
    locations: int = 0
    # Reach tính bằng triệu (vd. 4.2 = 4.2M).
    reach: Optional[float] = None


class IndustryStat(BaseModel):
    industry: str
    engagement: Optional[float] = None
    reach: Optional[int] = None
    # Tổng impressions (nghìn) cho biểu đồ Engagement by Industry.
    impressions: Optional[int] = None


class CityMonthlyStat(BaseModel):
    city: str
    # Nhãn ngắn cho trục X biểu đồ (vd. HCM), theo locale của request.
    short: Optional[str] = None
    # Trung bình tháng (triệu) cho biểu đồ Reach vs Engagement by City.
    monthlyReach: Optional[float] = None
    monthlyEngagements: Optional[float] = None


class CoverageResponse(BaseModel):
    provinces: list[ProvinceCoverage] = []
    venueTypes: list[VenueTypeCount] = []
    directory: Optional[list[LocationDirectoryEntry]] = None
    industryStats: Optional[list[IndustryStat]] = None
    cities: Optional[list[CityMonthlyStat]] = None


class CampaignOverview(BaseModel):
    locations: int
    venues: int
    reach: Optional[int] = None
    engagement: Optional[float] = None
    offPeak: Optional[float] = None


class SuggestedLocation(BaseModel):
    name: str
    area: str
    city: str
    reach: Optional[int] = None


class AdFormat(BaseModel):
    name: str
    metricLabel: str
    metricValue: Optional[float] = None
    durationSeconds: Optional[int] = None


class SuggestCity(BaseModel):
    name: str
    reach: Optional[int] = None
    engagements: Optional[int] = None
    impressionsPerDay: Optional[int] = None


class SuggestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=50, ge=1, le=200)
    # Locale hiển thị tên địa danh trong kết quả (vi/en, mặc định vi).
    locale: str = "vi"


class SuggestResponse(BaseModel):
    overview: CampaignOverview
    locations: list[SuggestedLocation] = []
    formats: list[AdFormat] = []
    cities: Optional[list[SuggestCity]] = None
    page: int = 1
    pageSize: int = 50
    total: int = 0


class LeadPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=5000)


class ContactPayload(BaseModel):
    type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=5000)


class StrapiWebhookPayload(BaseModel):
    event: str
    model: Optional[str] = None
    entry: Optional[dict] = None
