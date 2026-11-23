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
| `POST` | `/api/leads` | Lead form R1-2 (LEAD-01): body `{ name, email, phone (E.164), company, industry?, brand?, regions?, notes?, consentContact, consentMarketing?, turnstileToken?, utm?, source?, language?, market? }` → `201 { leadId, otpSent }`. Rate limit 5/phút/IP; email chưa xác thực trong 10 phút thì dùng lại lead cũ; SĐT sai định dạng E.164 → 422. |
| `POST` | `/api/leads/{id}/verify` | Xác thực OTP 6 số (hiệu lực 10 phút, tối đa 5 lần sai) → `{ verified, leadToken }` (JWT lead 60 phút). Mã sai → 400 `OTP_WRONG` kèm `details.attemptsLeft`; hết hạn → 400 `OTP_EXPIRED`; sai quá 5 lần → 429 `OTP_LOCKED`. Chỉ lead đã xác thực mới vào hàng đợi CRM. |
| `POST` | `/api/leads/{id}/resend` | Gửi lại OTP: cooldown 60s (`429 RESEND_COOLDOWN` kèm `retryAfter`), tối đa 5 mã/ngày (`429 RESEND_LIMIT`). |
| `PATCH` | `/api/leads/{id}` | Bổ sung hồ sơ sau xác thực (FE 21): cần `Authorization: Bearer <leadToken>` khớp leadId, chỉ cập nhật trường gửi lên. |
| `POST` | `/api/newsletter` | Đăng ký nhận tin ở footer → 202; email trùng vẫn 202 (không lộ đã đăng ký). Double opt-in ở BE 17 (R1-4). |
| `POST` | `/api/contact` | Form Contact Us (F15). |
| `GET` | `/api/events/stats` | SSE: full snapshot số liệu mỗi 30 giây (realtime, trễ tối đa 1 phút). |
| `GET` | `/api/auth/google` | Bắt đầu đăng nhập Google (F13). |
| `GET` | `/api/auth/google/callback` | Callback Google, phát JWT 24h, chuyển về Frontend. |
| `POST` | `/api/webhooks/strapi` | Nhận webhook publish từ Strapi, đẩy sự kiện `content-updated` qua SSE. |

Định dạng lỗi thống nhất: `{"error": {"code": "...", "message": "..."}}` (+ `details` tùy endpoint, vd. OTP sai kèm `attemptsLeft`).

## Lead + OTP + CRM giả lập (R1-2, BE 11-14)

Theo quyết định fake API/data của tran (23/11/2026, cho R1): chưa chốt CRM
(quyết định #1), nhà cung cấp email và Turnstile (quyết định #4) nên 3
luồng chạy ở chế độ giả lập — code thật, tích hợp thật thay vào sau mà
không đổi API:

- **OTP/email** (`app/otp.py`, `app/email.py`): mã 6 số chỉ lưu dạng
  SHA-256 (không lưu mã gốc, không log mã ngoài log email giả lập);
  `EMAIL_PROVIDER=fake` (mặc định) thì "gửi" = ghi log đầy đủ nội dung
  email. Kiểm thử end-to-end thì đọc mã từ log backend.
- **Turnstile** (`app/turnstile.py`): chưa có `TURNSTILE_SECRET` thì chấp
  nhận mọi token (kể cả null) và ghi log; có secret thì gọi siteverify
  thật, token sai bị từ chối. Frontend load widget thật khi có
  `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, chưa có thì hiện "mô phỏng".
- **CRM** (`app/crm.py`, `crm_jobs`): lead đã xác thực mới vào hàng đợi;
  worker trong tiến trình chạy mỗi 30s, "đẩy" = ghi log payload + thông
  báo sales, retry cấp số nhân tối đa 5 lần rồi đánh `failed`.

Biến môi trường mới (xem `.env.example`): `TURNSTILE_SECRET`,
`EMAIL_PROVIDER` (fake), `EMAIL_FROM`, `OTP_TTL_MINUTES` (10),
`OTP_MAX_ATTEMPTS` (5), `OTP_RESEND_COOLDOWN_SECONDS` (60),
`LEAD_TOKEN_EXPIRE_MINUTES` (60), `LEAD_RATE_LIMIT_PER_MINUTE` (5).

**CORS — 2 lỗi đã sửa 23/11/2026:** (1) Chrome gửi preflight kèm
`Access-Control-Request-Private-Network` khi trang ở 127.0.0.1 gọi API ở
cổng khác — Starlette trả 400 nếu thiếu `allow_private_network=True`
(đã bật trong `app/main.py`; lỗi này làm form lead không gửi được từ
trình duyệt dù curl vẫn 200). (2) `allow_methods` thiếu `PATCH` nên
bổ sung hồ sơ bị chặn — đã thêm. `FRONTEND_ORIGIN` chấp nhận nhiều
origin, phân tách bằng dấu phẩy (vd. `http://localhost:3100,http://127.0.0.1:3100`).

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

Tăng trưởng số liệu mẫu (tran 18/11/2026, `app/growth.py`): trước khi đẩy
snapshot mỗi kỳ, backend cộng dồn số liệu vào SQLite — Lượt kết nối
(+100.000/kỳ mặc định, đổi bằng `GROWTH_CONNECTIONS_PER_CYCLE`), reach,
engagements, impressions/ngày và monthly theo cùng tỉ lệ % so với tổng hiện
tại, chia theo tỉ trọng từng thành phố. Số được lưu lại nên restart backend
vẫn tiếp tục tăng từ mức đã đạt; cột NULL giữ NULL (Vũng Tàu/Huế không tự
sinh số), DB rỗng thì không làm gì. Tắt bằng `GROWTH_ENABLED=false` khi có
nguồn số liệu thật. Frontend nhận số mới qua SSE: dải số liệu (home) cập
nhật trực tiếp từ snapshot; /advertisers và /locations gọi lại API khi có
snapshot mới (lần gọi lại gửi `logPrompt: false` nên không ghi trùng vào
`prompt_logs`).
