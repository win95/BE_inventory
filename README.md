# AWING Backend — FastAPI + SQLite

Backend nghiệp vụ của dự án AWING (Plan §6), chạy trên host, ngoài Docker
Compose. Repo này là `win95/BE_inventory` — repo riêng của backend; Frontend
ở `win95/FE_inventory`, Strapi CMS + Compose ở repo Frontend theo Plan.

## Ranh giới (Plan §6 — ranh giới cứng)

- Backend này chỉ lo dữ liệu nghiệp vụ: số liệu mạng lưới, tỉnh/thành + mức
  phủ sóng, địa điểm/venue, định dạng quảng cáo, prompt + kết quả gợi ý, lead,
  tin nhắn liên hệ, người dùng cuối.
- Case study và nội dung home **không** nằm trong SQLite — đã chuyển sang
  Strapi (Postgres). Frontend lấy chúng qua Strapi REST.
- Không mock, không seed dữ liệu mẫu vào code. Database rỗng thì API trả
  rỗng, giao diện hiện trạng thái rỗng. Dữ liệu mẫu chỉ nằm trong các file
  CSV ở `scripts/data/` (xem dưới) để nhập thử — không nằm trong code.

## Chạy

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # sửa DATABASE_PATH, PORT, secret khi cần
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- OpenAPI tự sinh: http://localhost:8000/docs
- Health check: http://localhost:8000/ → `{"status": "ok"}`
- SQLite: một file duy nhất (`DATABASE_PATH`, mặc định `./awing.db`), tự tạo
  bảng rỗng khi khởi động. Thao tác trực tiếp file này trên host để kiểm tra
  dữ liệu thử nghiệm.

## Endpoints

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/api/network-stats` | Số liệu mạng lưới (F03). |
| `GET` | `/api/coverage` | Phủ sóng theo tỉnh, loại venue, thư mục địa điểm, số liệu ngành (F04, F17). Hỗ trợ `?locale=vi|en` (mặc định vi): `provinces[].province` giữ nguyên tên tiếng Anh làm khóa ổn định (Frontend khớp lưới heatmap bằng trường này), `displayName` là tên theo locale; `cities[].short` là nhãn ngắn cho trục X biểu đồ. |
| `POST` | `/api/suggest` | Gợi ý chiến dịch theo prompt, body `{ prompt, page?, pageSize?, locale? }` (F02, F06). `locale` vi/en (mặc định vi) dịch tên thành phố trong kết quả; việc khớp prompt vẫn dùng tên gốc trong DB nên prompt tiếng Anh vẫn khớp. `cities` trả tất cả 8 dòng `city_stats` (kể cả Vũng Tàu/Huế chưa có số liệu), mỗi thành phố có `monthlyEngagements` (triệu) dùng cho số trên chip + tổng Potential Engagements; `formats` trả 4 định dạng theo đúng thứ tự CSV, có `description` và nhãn metric `Engagement`. |
| `POST` | `/api/leads` | Lead form (F12). |
| `POST` | `/api/contact` | Form Contact Us (F15). |
| `GET` | `/api/events/stats` | SSE: full snapshot số liệu mỗi 30 giây (realtime, trễ tối đa 1 phút). |
| `GET` | `/api/auth/google` | Bắt đầu đăng nhập Google (F13). |
| `GET` | `/api/auth/google/callback` | Callback Google, phát JWT 24h, chuyển về Frontend. |
| `POST` | `/api/webhooks/strapi` | Nhận webhook publish từ Strapi, đẩy sự kiện `content-updated` qua SSE. |

Định dạng lỗi thống nhất: `{"error": {"code": "...", "message": "..."}}`.

Case study lấy qua Strapi REST, không qua backend này.

## Nhập dữ liệu thử nghiệm

`scripts/data/` đã có sẵn **dữ liệu mẫu** (73 dòng, 8 file): số liệu lấy
theo trang mẫu AWING trên Figma — 25,4 triệu lượt kết nối, 63 tỉnh, 195
chuỗi, 10.953 địa điểm; 32 tỉnh với mức tương tác 1-5 cho bản đồ nhiệt
Location Network (tên tỉnh dùng đúng nhãn trên bản đồ Figma), 6 loại venue,
10 địa điểm, 3 định dạng quảng cáo, 6 thành phố (kèm trung bình tháng cho
biểu đồ Reach vs Engagement), 7 chuỗi trong thư mục Location Network, 8
ngành (kèm tổng impressions cho biểu đồ Engagement by Industry). Các số
liệu nhất quán với nhau: tổng venues của `provinces` và `venue_types` đều
bằng 10.953; tổng 3 thành phố Hà Nội + TP.HCM + Đà Nẵng đúng 22,8 triệu
reach / 15,7 triệu engagement / 4,7 triệu impressions/ngày theo trang mẫu.

Nhập vào SQLite:

```bash
python scripts/import_csv.py
```

Chạy lại nhiều lần đều an toàn (ghi đè theo khóa chính; các bảng
`provinces`, `directory`, `industry_stats`, `ad_formats` được định nghĩa
trọn vẹn trong CSV nên nhập là thay toàn bộ). Database đã có từ trước được
nâng cấp tự động khi khởi động (`app/db.py` `_migrate`: level tỉnh
`low/medium/high` map sang 1/3/5, bảng `directory` cũ dựng lại rỗng, thêm
cột `industry_stats.impressions`, `city_stats.monthly_*` và
`ad_formats.description`). Muốn thay bằng dữ liệu thật thì sửa trực tiếp
các file CSV rồi chạy lại, hoặc thao tác trực tiếp bằng `sqlite3 awing.db`.

## Realtime

Vòng lặp nền trong tiến trình FastAPI: mỗi 30 giây đọc SQLite, dựng full
snapshot số liệu rồi đẩy qua SSE cho mọi client đang kết nối. Đẩy mỗi kỳ kể
cả khi dữ liệu chưa đổi; kỳ lỗi thì kỳ sau tự bù toàn bộ.
