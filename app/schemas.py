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
    # Khóa ổn định: tên tiếng Anh trong DB — Frontend khớp với lưới heatmap
    # bằng trường này, không dùng displayName (đổi theo locale).
    province: str
    # Tên hiển thị theo locale (?locale=vi|en); vi -> "Hà Nội", en -> "Ha Noi".
    displayName: Optional[str] = None
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
    # Mô tả hiển thị trên thẻ format (theo Figma Advertisers).
    description: Optional[str] = None


class SuggestCity(BaseModel):
    name: str
    reach: Optional[int] = None
    engagements: Optional[int] = None
    impressionsPerDay: Optional[int] = None
    # Tương tác trung bình tháng, đơn vị TRIỆU (như trong DB) — số hiện trên
    # chip thành phố khi được chọn + tổng Potential Engagements (Figma).
    monthlyEngagements: Optional[float] = None


class SuggestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=50, ge=1, le=200)
    # Locale hiển thị tên địa danh trong kết quả (vi/en, mặc định vi).
    locale: str = "vi"
    # Refresh số liệu realtime (Frontend gọi lại mỗi chu kỳ SSE) thì không ghi
    # prompt vào prompt_logs — mặc định True (lần gợi ý đầu tiên của người dùng).
    logPrompt: bool = True


class SuggestResponse(BaseModel):
    overview: CampaignOverview
    locations: list[SuggestedLocation] = []
    formats: list[AdFormat] = []
    cities: Optional[list[SuggestCity]] = None
    page: int = 1
    pageSize: int = 50
    total: int = 0


class LeadPayload(BaseModel):
    # Lead form R1-2 (LEAD-01, Docs §6.2; BE 11): bắt buộc họ tên / công ty /
    # email / SĐT E.164 / đồng ý liên hệ; tùy chọn ngành / thương hiệu /
    # khu vực / ghi chú; đồng ý nhận tin; token Turnstile (null khi giả lập);
    # UTM + nguồn + ngôn ngữ + thị trường (trường ẩn).
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=200)
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$", max_length=20)
    company: str = Field(min_length=1, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=200)
    regions: Optional[list[str]] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    message: Optional[str] = Field(default=None, max_length=5000)
    consentContact: bool
    consentMarketing: bool = False
    turnstileToken: Optional[str] = None
    utm: Optional[dict[str, str]] = None
    source: Optional[str] = Field(default=None, max_length=100)
    language: str = "vi"
    market: str = "vn"


class LeadSubmitResponse(BaseModel):
    leadId: int
    otpSent: bool


class OtpVerifyPayload(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class OtpVerifyResponse(BaseModel):
    verified: bool
    leadToken: str


class LeadProfilePayload(BaseModel):
    # Bổ sung hồ sơ sau xác thực (FE 21): chỉ cập nhật trường nào gửi lên.
    industry: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=200)
    regions: Optional[list[str]] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    consentMarketing: Optional[bool] = None


class NewsletterPayload(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=200)
    locale: str = "vi"


class EventRegistrationPayload(BaseModel):
    # Đăng ký sự kiện (BE 15, EVT-02): sự kiện nằm ở Strapi nên chỉ cần
    # slug; title + start/end do FE gửi kèm (hiện trên trang chi tiết) để
    # làm email xác nhận + file .ics.
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=200)
    phone: Optional[str] = Field(default=None, max_length=20)
    eventTitle: Optional[str] = Field(default=None, max_length=300)
    startDate: Optional[str] = Field(default=None, max_length=50)
    endDate: Optional[str] = Field(default=None, max_length=50)
    locale: str = "vi"
    consent: bool = False


class EventRegistrationResponse(BaseModel):
    registrationId: int
    registered: bool
    duplicate: bool = False


class JobApplicationResponse(BaseModel):
    applicationId: int
    received: bool


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
