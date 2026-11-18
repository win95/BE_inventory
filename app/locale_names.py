"""Tên địa danh theo locale (vi/en) — dữ liệu hiển thị, không lưu DB.

DB lưu tên gốc: tỉnh bằng tên bản đồ tiếng Anh (theo file HTML Figma),
thành phố bằng tiếng Việt. API trả tên theo locale để Frontend không phải
tự dịch và để nút chuyển EN/VN đổi cả dữ liệu dưới backend, không chỉ
chữ cứng trên giao diện. Tên nào không có trong bảng thì trả nguyên văn
(dữ liệu mới thêm sau vẫn hiện được, chỉ chưa có bản dịch).
"""

import re

# Tỉnh: khóa là tên tiếng Anh trong DB, giá trị là tên tiếng Việt.
PROVINCE_VI: dict[str, str] = {
    "Ha Noi": "Hà Nội",
    "Ho Chi Minh": "TP. Hồ Chí Minh",
    "Da Nang": "Đà Nẵng",
    "Hai Phong": "Hải Phòng",
    "Can Tho": "Cần Thơ",
    "Bien Hoa": "Biên Hòa",
    "Binh Duong": "Bình Dương",
    "Hue": "Huế",
    "Thai Nguyen": "Thái Nguyên",
    "Quang Ninh": "Quảng Ninh",
    "Thanh Hoa": "Thanh Hóa",
    "Bac Ninh": "Bắc Ninh",
    "Nghe An": "Nghệ An",
    "Quang Nam": "Quảng Nam",
    "Lam Dong": "Lâm Đồng",
    "Khanh Hoa": "Khánh Hòa",
    "Binh Thuan": "Bình Thuận",
    "Tay Ninh": "Tây Ninh",
    "An Giang": "An Giang",
    "Nam Dinh": "Nam Định",
    "Ha Tinh": "Hà Tĩnh",
    "Quang Binh": "Quảng Bình",
    "Binh Dinh": "Bình Định",
    "Dong Thap": "Đồng Tháp",
    "Tien Giang": "Tiền Giang",
    "Vung Tau": "Vũng Tàu",
    "Kien Giang": "Kiên Giang",
    "Vinh Long": "Vĩnh Long",
    "Ben Tre": "Bến Tre",
    "Bac Lieu": "Bạc Liêu",
    "Soc Trang": "Sóc Trăng",
    "Ca Mau": "Cà Mau",
}

# Thành phố: khóa là tên tiếng Việt trong DB.
# "en": tên đầy đủ tiếng Anh; "short": nhãn ngắn cho trục X biểu đồ.
CITY_LOCALIZED: dict[str, dict[str, str]] = {
    "Hà Nội": {"en": "Ha Noi", "short_vi": "Hà Nội", "short_en": "Ha Noi"},
    "TP. Hồ Chí Minh": {"en": "Ho Chi Minh", "short_vi": "HCM", "short_en": "HCM"},
    "Đà Nẵng": {"en": "Da Nang", "short_vi": "Đà Nẵng", "short_en": "Da Nang"},
    "Hải Phòng": {"en": "Hai Phong", "short_vi": "Hải Phòng", "short_en": "Hai Phong"},
    "Cần Thơ": {"en": "Can Tho", "short_vi": "Cần Thơ", "short_en": "Can Tho"},
    "Biên Hòa": {"en": "Bien Hoa", "short_vi": "Biên Hòa", "short_en": "Bien Hoa"},
    "Bình Dương": {"en": "Binh Duong", "short_vi": "Bình Dương", "short_en": "Binh Duong"},
    "Vũng Tàu": {"en": "Vung Tau", "short_vi": "Vũng Tàu", "short_en": "Vung Tau"},
    "Huế": {"en": "Hue", "short_vi": "Huế", "short_en": "Hue"},
}

# Nhãn dữ liệu theo locale (dịch hết theo từng mode, 18/11/2026). Các bảng
# này là tập kín theo dữ liệu mẫu hiện tại; nhãn nào không có trong bảng thì
# trả nguyên văn (dữ liệu mới thêm sau vẫn hiện được, chỉ chưa có bản dịch).
VENUE_TYPE_VI: dict[str, str] = {
    "Airport": "Sân bay",
    "Coffee": "Cà phê",
    "Mall": "Trung tâm thương mại",
    "Office": "Văn phòng",
    "Retail": "Bán lẻ",
    "University": "Trường đại học",
}

DIRECTORY_CATEGORY_VI: dict[str, str] = {
    "Retail": "Bán lẻ",
    "F&B": "F&B",
    "Transit": "Giao thông",
    "Healthcare": "Y tế",
}

INDUSTRY_VI: dict[str, str] = {
    "Retail & FMCG": "Bán lẻ & FMCG",
    "F&B": "F&B",
    "Fashion": "Thời trang",
    "Finance": "Tài chính",
    "Healthcare": "Y tế",
    "Automotive": "Ô tô",
    "Education": "Giáo dục",
    "Technology": "Công nghệ",
}

# Mô tả định dạng quảng cáo: DB lưu bản tiếng Anh (theo Figma); bản vi dịch
# ở đây, key theo tên format. Nhãn metric cũng vậy.
FORMAT_DESCRIPTION_VI: dict[str, str] = {
    "Bumper Ads": "Quảng cáo ngắn trước nội dung Wi-Fi. Khán giả bị thu hút, tỉ lệ xem hết 100% — không thể bỏ qua.",
    "Banner / Slide": "Banner tương tác vuốt qua với link CTA trực tiếp và giới thiệu sản phẩm.",
    "Text Matching": "Quảng cáo chữ khớp ngữ cảnh với thói quen duyệt web của người dùng, nhắm đúng đối tượng.",
    "Video Full Screen": "Video toàn màn hình chiếm sóng trên cổng Wi-Fi. Tác động thương hiệu tối đa.",
}

METRIC_LABEL_VI: dict[str, str] = {
    "Engagement": "Tương tác",
}


def parse_locale(value: str | None) -> str:
    """Chuẩn hóa locale: chỉ nhận vi/en, còn lại (kể cả vi-VN, en-US) về vi."""
    if not value:
        return "vi"
    code = value.strip().lower().replace("_", "-").split("-")[0]
    return code if code in ("vi", "en") else "vi"


def province_name(db_name: str, locale: str) -> str:
    """Tên tỉnh theo locale (DB lưu tên tiếng Anh)."""
    if locale == "vi":
        return PROVINCE_VI.get(db_name, db_name)
    return db_name


def city_name(db_name: str, locale: str) -> str:
    """Tên thành phố theo locale (DB lưu tên tiếng Việt)."""
    if locale == "en":
        entry = CITY_LOCALIZED.get(db_name)
        return entry["en"] if entry else db_name
    return db_name


def city_short(db_name: str, locale: str) -> str:
    """Nhãn ngắn của thành phố cho trục X biểu đồ, theo locale."""
    entry = CITY_LOCALIZED.get(db_name)
    if not entry:
        return db_name
    return entry["short_en"] if locale == "en" else entry["short_vi"]


def venue_type_name(db_name: str, locale: str) -> str:
    """Loại địa điểm theo locale (DB lưu tên tiếng Anh)."""
    if locale == "vi":
        return VENUE_TYPE_VI.get(db_name, db_name)
    return db_name


def directory_category_name(db_name: str, locale: str) -> str:
    """Nhóm thư mục địa điểm theo locale (DB lưu tên tiếng Anh)."""
    if locale == "vi":
        return DIRECTORY_CATEGORY_VI.get(db_name, db_name)
    return db_name


def industry_name(db_name: str, locale: str) -> str:
    """Tên ngành theo locale (DB lưu tên tiếng Anh)."""
    if locale == "vi":
        return INDUSTRY_VI.get(db_name, db_name)
    return db_name


def format_description(name: str, db_description: str | None, locale: str) -> str | None:
    """Mô tả định dạng quảng cáo theo locale (DB lưu bản tiếng Anh)."""
    if locale == "vi":
        return FORMAT_DESCRIPTION_VI.get(name, db_description)
    return db_description


def metric_label_name(db_label: str, locale: str) -> str:
    """Nhãn chỉ số (vd. Engagement) theo locale."""
    if locale == "vi":
        return METRIC_LABEL_VI.get(db_label, db_label)
    return db_label


def directory_subtitle(subtitle: str, locale: str) -> str:
    """Ghi chú dưới tên chuỗi ('63 provinces', '24 cities', 'Ha Noi').

    Vi: dịch mẫu 'N provinces'/'N cities'; tên thành phố thì dùng tên tiếng
    Việt theo bảng thành phố. En: giữ nguyên như trong DB.
    """
    if locale != "vi":
        return subtitle
    m = re.match(r"^(\d+)\s+provinces$", subtitle)
    if m:
        return f"{m.group(1)} tỉnh thành"
    m = re.match(r"^(\d+)\s+cities$", subtitle)
    if m:
        return f"{m.group(1)} thành phố"
    for db_name, entry in CITY_LOCALIZED.items():
        if entry["en"] == subtitle:
            return db_name
    return subtitle
